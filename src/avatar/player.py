"""เล่นไฟล์เสียง + ขับพารามิเตอร์ปากของอวตารให้ซิงก์กับเสียง."""
from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import soundfile as sf

from src.avatar.lipsync import envelope_from_audio
from src.avatar.vts_client import VTSClient


def _resample_linear(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr or audio.size == 0:
        return audio
    n_dst = int(round(len(audio) * dst_sr / src_sr))
    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_dst, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def _load_concat(paths: list[Path], gap_sec: float = 0.12) -> tuple[np.ndarray, int]:
    chunks: list[np.ndarray] = []
    target_sr: int | None = None
    for p in paths:
        audio, sr = sf.read(p, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if target_sr is None:
            target_sr = int(sr)
        elif sr != target_sr:
            audio = _resample_linear(audio, int(sr), target_sr)
        chunks.append(audio)
        chunks.append(np.zeros(int(target_sr * gap_sec), dtype=np.float32))
    if not chunks:
        return np.zeros(1, dtype=np.float32), 24000
    return np.concatenate(chunks), int(target_sr or 24000)


class Player:
    def __init__(
        self,
        vts: VTSClient | None,
        fps: int = 30,
        gain: float = 1.6,
        attack: float = 0.6,
        release: float = 0.25,
        noise_gate: float = 0.14,
    ):
        self.vts = vts
        self.fps = fps
        self.gain = gain
        self.attack = attack
        self.release = release
        self.noise_gate = noise_gate
        self._audio_ok = True

    # ------------------------------------------------------------------ #
    async def speak(self, wav_paths: list[Path]) -> None:
        if not wav_paths:
            return
        audio, sr = await asyncio.to_thread(_load_concat, wav_paths)
        env = envelope_from_audio(
            audio, sr, self.fps, self.gain, self.attack, self.release, self.noise_gate
        )

        try:
            import sounddevice as sd
        except Exception:
            self._audio_ok = False
            return

        loop = asyncio.get_running_loop()
        try:
            await asyncio.to_thread(sd.play, audio, sr)
        except Exception as e:  # noqa: BLE001 - ไม่มีอุปกรณ์เสียง ฯลฯ
            self._audio_ok = False
            print(f"  [player] เล่นเสียงไม่ได้: {e}")
            return

        t0 = loop.time()
        dur = len(audio) / sr
        try:
            while True:
                t = loop.time() - t0
                if t >= dur:
                    break
                idx = min(len(env) - 1, int(t * self.fps))
                if self.vts is not None:
                    await self.vts.set_mouth(float(env[idx]))
                await asyncio.sleep(1.0 / self.fps)
        except asyncio.CancelledError:
            await asyncio.to_thread(sd.stop)
            if self.vts is not None:
                await self.vts.set_mouth(0.0)
            raise
        finally:
            await asyncio.to_thread(sd.wait)
            if self.vts is not None:
                await self.vts.set_mouth(0.0)
