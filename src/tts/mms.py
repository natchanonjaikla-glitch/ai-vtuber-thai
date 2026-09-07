"""เอนจิน TTS: facebook/mms-tts-tha (VITS ผ่าน transformers).

เบา เร็ว รันบน CPU (<1 วิ/ประโยค) เสียงเดียว ไม่โคลน — ใช้เป็นค่าเริ่มต้น/สำรอง.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from src.config import MMSConfig
from src.tts.base import TTSEngine


class MMSEngine(TTSEngine):
    name = "mms"

    def __init__(self, cfg: MMSConfig, cpu_threads: int = 8):
        self.cfg = cfg
        self.cpu_threads = cpu_threads
        self._loaded = False
        self._model = None
        self._tokenizer = None

    def load(self) -> None:
        if self._loaded:
            return
        import torch
        from transformers import AutoTokenizer, VitsModel

        torch.set_num_threads(max(1, self.cpu_threads))
        self._model = VitsModel.from_pretrained(self.cfg.model_id)
        self._model.eval()
        self._tokenizer = AutoTokenizer.from_pretrained(self.cfg.model_id)
        self.sample_rate = int(self._model.config.sampling_rate)  # 16000
        self._loaded = True

    def synth(self, text: str, out_path: Path) -> None:
        if not self._loaded:
            self.load()
        import torch

        text = text.strip()
        if not text:
            sf.write(out_path, np.zeros(1, dtype=np.float32), self.sample_rate)
            return

        inputs = self._tokenizer(text, return_tensors="pt")
        with torch.no_grad():
            wav = self._model(**inputs).waveform  # (1, n)
        audio = wav.squeeze().detach().cpu().numpy().astype(np.float32)

        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if peak > 1e-4:
            audio = 0.95 * audio / peak  # normalize กันเบา/คลิป

        out_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(out_path, audio, self.sample_rate)
