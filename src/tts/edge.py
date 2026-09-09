"""เอนจิน TTS: Edge-TTS (เสียง neural ภาษาไทยของ Microsoft).

เสียงธรรมชาติที่สุดในบรรดาตัวเลือกทั้งหมด และเร็วมาก ฟรี ไม่ต้องใช้ API key
⚠️ ต้องต่ออินเทอร์เน็ต (ไม่ใช่ offline)

เสียงไทยที่มี:
  th-TH-PremwadeeNeural  (หญิง)
  th-TH-NiwatNeural      (ชาย)
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import soundfile as sf

from src.config import EdgeConfig
from src.tts.base import TTSEngine


class EdgeEngine(TTSEngine):
    name = "edge"
    sample_rate = 24000

    def __init__(self, cfg: EdgeConfig):
        self.cfg = cfg
        self._loaded = False

    def load(self) -> None:
        import edge_tts  # noqa: F401  — แค่เช็กว่ามีแพ็กเกจ

        self._loaded = True

    # ------------------------------------------------------------------ #
    async def _save_mp3(self, text: str, mp3_path: Path) -> None:
        import edge_tts

        comm = edge_tts.Communicate(
            text,
            voice=self.cfg.voice,
            rate=self.cfg.rate,
            pitch=self.cfg.pitch,
            volume=self.cfg.volume,
        )
        await comm.save(str(mp3_path))

    def synth(self, text: str, out_path: Path) -> None:
        if not self._loaded:
            self.load()

        text = text.strip()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if not text:
            sf.write(out_path, np.zeros(1, dtype=np.float32), self.sample_rate)
            return

        mp3 = out_path.with_suffix(".mp3")
        try:
            asyncio.run(self._save_mp3(text, mp3))
        except RuntimeError:
            # ถูกเรียกจากใน event loop อยู่แล้ว → รันใน loop ใหม่บนเธรดนี้
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(self._save_mp3(text, mp3))
            finally:
                loop.close()

        audio, sr = sf.read(mp3, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        self.sample_rate = int(sr)
        sf.write(out_path, audio, self.sample_rate)
        mp3.unlink(missing_ok=True)
