"""ตรวจความพร้อมของระบบก่อนรันแอป:  python scripts/setup_check.py"""
from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console  # noqa: E402
from rich.table import Table  # noqa: E402

from src.config import load_config  # noqa: E402

console = Console()


def check_imports() -> tuple[bool, str]:
    missing = []
    for mod in ("openai", "yaml", "dotenv", "numpy", "soundfile", "sounddevice",
                "websockets", "torch", "transformers", "pythainlp", "rich"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        return False, "ขาด: " + ", ".join(missing) + "  → pip install -r requirements.txt"
    return True, "ครบ"


def check_f5() -> tuple[bool, str]:
    try:
        import f5_tts  # noqa: F401
        return True, "ติดตั้งแล้ว"
    except ImportError:
        return False, "ยังไม่ติดตั้ง (ใช้ MMS ได้) → pip install -r requirements-f5.txt"


def check_ffmpeg() -> tuple[bool, str]:
    p = shutil.which("ffmpeg")
    return (bool(p), p or "ไม่พบ → winget install Gyan.FFmpeg")


def check_claude() -> tuple[bool, str]:
    p = shutil.which("claude")
    return (bool(p), p or "ไม่พบ → npm i -g @anthropic-ai/claude-code")


def check_lmstudio(base_url: str, model: str) -> tuple[bool, str]:
    import httpx

    try:
        r = httpx.get(base_url.rstrip("/") + "/models", timeout=4)
        r.raise_for_status()
        ids = [m.get("id", "") for m in r.json().get("data", [])]
        if model in ids:
            return True, f"ออนไลน์ • โหลดโมเดล {model} แล้ว"
        return True, f"ออนไลน์ • แต่ยังไม่เห็นโมเดล '{model}' (มี: {', '.join(ids) or 'ไม่มี'})"
    except Exception as e:  # noqa: BLE001
        return False, f"ต่อไม่ได้ ({e!s}) → เปิด Start Server ใน LM Studio"


def check_vts(url: str) -> tuple[bool, str]:
    async def _probe() -> tuple[bool, str]:
        import websockets

        try:
            async with websockets.connect(url, open_timeout=4) as ws:
                await ws.send(
                    '{"apiName":"VTubeStudioPublicAPI","apiVersion":"1.0",'
                    '"requestID":"probe","messageType":"APIStateRequest"}'
                )
                await ws.recv()
            return True, "พอร์ต API ตอบแล้ว"
        except Exception as e:  # noqa: BLE001
            return False, f"ต่อไม่ได้ ({e!s}) → เปิด VTube Studio + Settings > Start API"

    return asyncio.run(_probe())


def check_voice_ref(cfg) -> tuple[bool, str]:
    wav = cfg.resolve(cfg.tts.f5.ref_wav)
    txt = cfg.resolve(cfg.tts.f5.ref_text)
    if not wav.exists():
        return False, f"ไม่มี {wav} (จำเป็นเฉพาะตอนใช้ /voice f5)"
    if not txt.exists():
        return False, f"มี ref.wav แล้ว แต่ยังไม่มี {txt}"
    return True, "พร้อมสำหรับ F5 voice cloning"


def main() -> None:
    cfg = load_config()
    table = Table(title="AI VTuber — Setup Check", show_lines=False)
    table.add_column("รายการ", style="cyan", no_wrap=True)
    table.add_column("สถานะ")
    table.add_column("รายละเอียด")

    rows = [
        ("Python 3.10+", sys.version_info >= (3, 10), sys.version.split()[0]),
        ("Core packages", *check_imports()),
        ("F5-TTS (option)", *check_f5()),
        ("ffmpeg", *check_ffmpeg()),
        ("claude CLI", *check_claude()),
        ("LM Studio", *check_lmstudio(cfg.llm.base_url, cfg.llm.model)),
        ("VTube Studio", *check_vts(cfg.avatar.vts_url)),
        ("Voice ref (F5)", *check_voice_ref(cfg)),
    ]
    for name, ok, detail in rows:
        mark = "[green]✓[/]" if ok else "[yellow]—[/]"
        table.add_row(name, mark, str(detail))

    console.print(table)
    console.print(
        "\n[dim]ต้องมี: Core packages + (LM Studio ตอนคุย) + (VTube Studio ตอนอยากเห็นปากขยับ)."
        "  ffmpeg/claude/F5 ใส่เพิ่มทีหลังได้[/]"
    )


if __name__ == "__main__":
    main()
