"""อินเทอร์เฟซกลางของเอนจิน TTS."""
from __future__ import annotations

import abc
from pathlib import Path


class TTSEngine(abc.ABC):
    name: str = "base"
    sample_rate: int = 24000

    @abc.abstractmethod
    def load(self) -> None:
        """โหลดโมเดลเข้าหน่วยความจำ (เรียกครั้งเดียวตอนสตาร์ต)."""

    @abc.abstractmethod
    def synth(self, text: str, out_path: Path) -> None:
        """สังเคราะห์ ``text`` เป็นไฟล์ wav ที่ ``out_path`` (mono, float/pcm16)."""

    @property
    def loaded(self) -> bool:
        return getattr(self, "_loaded", False)
