"""เอนจิน TTS: F5-TTS-THAI (โคลนเสียงภาษาไทย) ผ่านแพ็กเกจ f5-tts-th.

โมเดล: VIZINTZOR/F5-TTS-THAI — offline, โคลนเสียงจากตัวอย่างสั้น ๆ

⚠️  ช้ามากบน CPU (เครื่องนี้ไม่มี CUDA): ~6 นาที ต่อ 1 ประโยค
    → เหมาะกับงาน "อัดเสียงล่วงหน้า" ไม่เหมาะกับแชทสด
    → แชทสดให้ใช้ engine 'mms'

ถ้าไม่มี assets/voice_ref/ref.wav จะดึงเสียงตัวอย่างจาก repo มาใช้อัตโนมัติ
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from src.config import F5Config
from src.tts.base import TTSEngine

# เสียงตัวอย่างจาก repo + ข้อความที่ตรงกัน (ใช้เป็น default ถ้าผู้ใช้ไม่ใส่ ref เอง)
_SAMPLE_REF_FILE = "sample/ref_audio.wav"
_SAMPLE_REF_TEXT = "ฉันเดินทางไปเที่ยวที่จังหวัดเชียงใหม่ในช่วงฤดูหนาวเพื่อสัมผัสอากาศเย็นสบาย"


class F5ThaiEngine(TTSEngine):
    name = "f5"
    sample_rate = 24000

    def __init__(self, cfg: F5Config, project_root: Path, cpu_threads: int = 8):
        self.cfg = cfg
        self.root = project_root
        self.cpu_threads = cpu_threads
        self._loaded = False
        self._tts = None
        self._ref_wav = ""
        self._ref_text = ""

    # ------------------------------------------------------------------ #
    def _resolve_ref(self) -> tuple[str, str]:
        ref_wav = self.root / self.cfg.ref_wav
        if ref_wav.exists():
            rt_path = self.root / self.cfg.ref_text
            ref_text = (
                rt_path.read_text(encoding="utf-8").strip()
                if rt_path.exists()
                else self.cfg.ref_text.strip()
            )
            if not ref_text:
                raise ValueError(f"มี {ref_wav} แล้ว แต่ {rt_path} ว่าง/ไม่มี — ใส่ข้อความที่พูดในไฟล์เสียง")
            return str(ref_wav), ref_text

        # fallback: เสียงตัวอย่างจาก HuggingFace repo
        from huggingface_hub import hf_hub_download

        print("  [f5] ไม่พบ ref.wav ของคุณ — ใช้เสียงตัวอย่างจาก repo ไปก่อน")
        sample = hf_hub_download(self.cfg.hf_repo, _SAMPLE_REF_FILE)
        return sample, _SAMPLE_REF_TEXT

    # ------------------------------------------------------------------ #
    def load(self) -> None:
        if self._loaded:
            return
        import torch

        torch.set_num_threads(max(1, self.cpu_threads))
        self._ref_wav, self._ref_text = self._resolve_ref()

        from f5_tts_th.tts import TTS

        self._tts = TTS(model=self.cfg.model_name)  # ดาวน์โหลด ckpt+vocab เองครั้งแรก
        self._loaded = True

    # ------------------------------------------------------------------ #
    def synth(self, text: str, out_path: Path) -> None:
        if not self._loaded:
            self.load()

        text = text.strip()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if not text:
            sf.write(out_path, np.zeros(1, dtype=np.float32), self.sample_rate)
            return

        wav = self._tts.infer(
            ref_audio=self._ref_wav,
            ref_text=self._ref_text,
            gen_text=text,
            step=self.cfg.nfe_step,
            speed=self.cfg.speed,
            cfg=2.0,
        )
        wav = np.asarray(wav, dtype=np.float32).squeeze()

        peak = float(np.max(np.abs(wav))) if wav.size else 0.0
        if peak > 1.0:
            wav = 0.97 * wav / peak  # กันคลิป (F5 ชอบ overshoot)

        sf.write(out_path, wav, self.sample_rate)
