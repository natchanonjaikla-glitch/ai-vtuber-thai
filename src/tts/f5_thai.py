"""เอนจิน TTS หลัก: F5-TTS-THAI (โคลนเสียงภาษาไทยจากตัวอย่างสั้น ๆ).

โมเดล: VIZINTZOR/F5-TTS-THAI บน HuggingFace — offline, รันบน CPU (ช้ากว่า MMS).
ต้องมีไฟล์เสียงอ้างอิง assets/voice_ref/ref.wav + ข้อความตรงกันใน ref.txt
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from src.config import F5Config
from src.tts.base import TTSEngine


class F5ThaiEngine(TTSEngine):
    name = "f5"
    sample_rate = 24000

    def __init__(self, cfg: F5Config, project_root: Path, cpu_threads: int = 8):
        self.cfg = cfg
        self.root = project_root
        self.cpu_threads = cpu_threads
        self._loaded = False
        self._api = None
        self._ref_wav: str = ""
        self._ref_text: str = ""

    # ------------------------------------------------------------------ #
    def _resolve_ref(self) -> tuple[str, str]:
        ref_wav = self.root / self.cfg.ref_wav
        if not ref_wav.exists():
            raise FileNotFoundError(
                f"ไม่พบไฟล์เสียงอ้างอิง: {ref_wav}\n"
                "  ใส่ไฟล์ .wav พูดไทยชัด ๆ ~8–12 วินาที (mono) แล้วเขียนข้อความที่พูดลง ref.txt"
            )
        rt = self.cfg.ref_text
        rt_path = self.root / rt
        ref_text = rt_path.read_text(encoding="utf-8").strip() if rt_path.exists() else rt.strip()
        return str(ref_wav), ref_text

    def _download_checkpoint(self) -> tuple[str, str]:
        from huggingface_hub import hf_hub_download, list_repo_files

        repo = self.cfg.hf_repo
        files = list_repo_files(repo)

        ckpt_name = self.cfg.ckpt_file
        if ckpt_name not in files:
            cands = [f for f in files if f.endswith((".pt", ".safetensors")) and "vocab" not in f]
            if not cands:
                raise RuntimeError(f"ไม่พบไฟล์ checkpoint ใน repo {repo}")
            ckpt_name = sorted(cands)[-1]  # เดาไฟล์ล่าสุด

        vocab_name = self.cfg.vocab_file
        if vocab_name not in files:
            vcands = [f for f in files if f.endswith(".txt") and "vocab" in f.lower()]
            vocab_name = vcands[0] if vcands else "vocab.txt"

        ckpt = hf_hub_download(repo, ckpt_name)
        vocab = hf_hub_download(repo, vocab_name)
        return ckpt, vocab

    # ------------------------------------------------------------------ #
    def load(self) -> None:
        if self._loaded:
            return
        import torch

        torch.set_num_threads(max(1, self.cpu_threads))

        self._ref_wav, self._ref_text = self._resolve_ref()
        ckpt, vocab = self._download_checkpoint()

        from f5_tts.api import F5TTS

        kwargs = dict(ckpt_file=ckpt, vocab_file=vocab, device="cpu")
        try:                                   # f5-tts >= 1.1
            self._api = F5TTS(model=self.cfg.model_name, **kwargs)
        except TypeError:                      # f5-tts รุ่นเก่าใช้ model_type
            self._api = F5TTS(model_type=self.cfg.model_name, **kwargs)

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

        wav, sr, _ = self._api.infer(
            ref_file=self._ref_wav,
            ref_text=self._ref_text,
            gen_text=text,
            nfe_step=self.cfg.nfe_step,
            speed=self.cfg.speed,
            remove_silence=self.cfg.remove_silence,
            file_wave=str(out_path),
        )
        # infer() เขียนไฟล์ให้แล้วผ่าน file_wave; เผื่อบางรุ่นไม่เขียน ก็ save เอง
        if not out_path.exists() and wav is not None:
            sf.write(out_path, np.asarray(wav, dtype=np.float32), int(sr or self.sample_rate))
