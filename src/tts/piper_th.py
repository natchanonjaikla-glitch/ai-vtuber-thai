"""เอนจิน TTS: Piper (เสียงไทย th_TH-tsync2-medium).

VITS ผ่าน ONNX Runtime — offline 100%, เร็วมากบน CPU (เร็วกว่า realtime หลายเท่า),
เสียงธรรมชาติกว่า MMS พอสมควร โมเดลเล็ก (~60 MB)

โมเดลจาก rhasspy/piper-voices บน HuggingFace
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import soundfile as sf

from src.config import PiperConfig
from src.tts.base import TTSEngine

_REPO = "rhasspy/piper-voices"


class PiperEngine(TTSEngine):
    name = "piper"
    sample_rate = 22050  # ตั้งจริงอีกทีหลังโหลด config ของ voice

    def __init__(self, cfg: PiperConfig, cpu_threads: int = 8):
        self.cfg = cfg
        self.cpu_threads = cpu_threads
        self._loaded = False
        self._voice = None

    def _voice_paths(self) -> tuple[str, str]:
        """ดาวน์โหลด .onnx + .onnx.json ของเสียงที่เลือก แล้วคืน path."""
        from huggingface_hub import hf_hub_download

        v = self.cfg.voice                      # เช่น "th_TH-tsync2-medium"
        lang_full = v.split("-")[0]             # "th_TH"
        lang = lang_full.split("_")[0]          # "th"
        name = v.split("-")[1]                  # "tsync2"
        quality = v.split("-")[2]               # "medium"
        base = f"{lang}/{lang_full}/{name}/{quality}/{v}"

        onnx = hf_hub_download(_REPO, f"{base}.onnx")
        conf = hf_hub_download(_REPO, f"{base}.onnx.json")
        return onnx, conf

    def load(self) -> None:
        if self._loaded:
            return
        from piper import PiperVoice

        onnx, conf = self._voice_paths()
        self._voice = PiperVoice.load(onnx, config_path=conf, use_cuda=False)
        self.sample_rate = int(self._voice.config.sample_rate)
        self._loaded = True

    def synth(self, text: str, out_path: Path) -> None:
        if not self._loaded:
            self.load()
        from piper import SynthesisConfig

        text = text.strip()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if not text:
            sf.write(out_path, np.zeros(1, dtype=np.float32), self.sample_rate)
            return

        syn = SynthesisConfig(
            length_scale=1.0 / max(0.1, self.cfg.speed),  # >1 = ช้าลง
            noise_scale=self.cfg.noise_scale,
            noise_w_scale=self.cfg.noise_w,
        )
        # สังเคราะห์ให้ครบก่อนค่อยเขียนไฟล์ — ถ้า synthesize พัง จะได้เห็น error จริง
        # ไม่ใช่ "# channels not specified" จากตอนปิดไฟล์ wav ที่ยังว่าง
        chunks = list(self._voice.synthesize(text, syn_config=syn))
        if not chunks:
            raise RuntimeError(f"Piper สังเคราะห์เสียงไม่ออกสำหรับข้อความ: {text[:50]!r}")

        first = chunks[0]
        self.sample_rate = int(first.sample_rate)
        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(first.sample_channels)
            wf.setsampwidth(first.sample_width)
            wf.setframerate(first.sample_rate)
            for ch in chunks:
                wf.writeframes(ch.audio_int16_bytes)
