#!/usr/bin/env python
"""จุดเริ่มต้นแอป AI VTuber.  รัน:  python run.py"""
from __future__ import annotations

import asyncio
import sys


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass


def _check_venv() -> None:
    """เตือนให้อ่านรู้เรื่อง ถ้ารันด้วย Python ตัวที่ไม่มีแพ็กเกจ (เช่น Python ของระบบ)."""
    try:
        import soundfile  # noqa: F401
        return
    except ImportError:
        pass

    from pathlib import Path

    venv_py = Path(__file__).resolve().parent / ".venv" / "Scripts" / "python.exe"
    print("\n[!] Python ตัวนี้ไม่มีแพ็กเกจที่ต้องใช้")
    print(f"    กำลังรันด้วย : {sys.executable}")
    if venv_py.exists():
        print(f"    ต้องรันด้วย  : {venv_py}\n")
        print("    วิธีรัน (เลือกอย่างใดอย่างหนึ่ง):")
        print("      1) ดับเบิลคลิก  start.bat")
        print("      2) .\\.venv\\Scripts\\python.exe run.py")
        print("      3) .\\.venv\\Scripts\\Activate.ps1   แล้วค่อย  python run.py\n")
    else:
        print("    ยังไม่มี .venv — สร้างก่อนด้วย:")
        print("      python -m venv .venv")
        print("      .venv\\Scripts\\python.exe -m pip install -r requirements.txt\n")
    sys.exit(1)


def main() -> None:
    _force_utf8()
    _check_venv()
    from src.app import main as app_main

    try:
        asyncio.run(app_main())
    except KeyboardInterrupt:
        print("\nออกแล้วค่ะ 👋")


if __name__ == "__main__":
    main()
