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


def main() -> None:
    _force_utf8()
    from src.app import main as app_main

    try:
        asyncio.run(app_main())
    except KeyboardInterrupt:
        print("\nออกแล้วค่ะ 👋")


if __name__ == "__main__":
    main()
