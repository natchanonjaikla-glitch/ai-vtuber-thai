"""โหลดโมเดล TTS ล่วงหน้า (ไม่ต้องรอตอนสตาร์ตแอปครั้งแรก).

  python scripts/download_models.py            # โหลด MMS
  python scripts/download_models.py --f5       # โหลด F5-TTS-THAI ด้วย
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config  # noqa: E402


def download_mms(model_id: str) -> None:
    print(f"→ MMS-TTS: {model_id}")
    from transformers import AutoTokenizer, VitsModel

    VitsModel.from_pretrained(model_id)
    AutoTokenizer.from_pretrained(model_id)
    print("  เสร็จ")


def download_f5(cfg) -> None:
    repo = cfg.tts.f5.hf_repo
    print(f"→ F5-TTS-THAI: {repo}")
    from huggingface_hub import list_repo_files, snapshot_download

    files = list_repo_files(repo)
    print("  ไฟล์ใน repo:", ", ".join(files))
    snapshot_download(repo, allow_patterns=["*.pt", "*.safetensors", "*.txt", "*.json", "*.yaml"])
    print("  เสร็จ")
    try:
        import f5_tts  # noqa: F401
    except ImportError:
        print("  [เตือน] ยังไม่ได้ติดตั้งแพ็กเกจ f5-tts → pip install -r requirements-f5.txt")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--f5", action="store_true", help="โหลด F5-TTS-THAI ด้วย")
    args = ap.parse_args()

    cfg = load_config()
    download_mms(cfg.tts.mms.model_id)
    if args.f5:
        download_f5(cfg)
    print("\nพร้อมแล้ว")


if __name__ == "__main__":
    main()
