"""ทดสอบการต่อ VTube Studio + ขยับปาก ทีละขั้น

    .venv\\Scripts\\python.exe scripts\\test_avatar.py

ขั้นตอน:
  1. ต่อ + ขออนุญาต (ครั้งแรกต้องไปกด Allow ในหน้าต่าง VTube Studio)
  2. บอกว่าโหลดโมเดลอะไรอยู่ และมีพารามิเตอร์อะไรให้ฉีดค่าได้บ้าง
  3. กวาดค่าปากขึ้น-ลง 3 รอบ (ดูว่าปากขยับจริงไหม)
  4. พูดจริงพร้อมขยับปากตามเสียง
"""
from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console  # noqa: E402

from src.avatar.player import Player  # noqa: E402
from src.avatar.vts_client import VTSClient  # noqa: E402
from src.config import load_config  # noqa: E402
from src.tts.manager import TTSManager  # noqa: E402

console = Console()


async def main() -> None:
    cfg = load_config()
    c = console

    # -- 1. ต่อ ------------------------------------------------------------
    c.print(f"[bold]1) ต่อ VTube Studio[/] ที่ {cfg.avatar.vts_url}")
    vts = VTSClient(
        url=cfg.avatar.vts_url,
        plugin_name=cfg.avatar.plugin_name,
        plugin_developer=cfg.avatar.plugin_developer,
        token_file=cfg.resolve(cfg.avatar.token_file),
        mouth_param=cfg.avatar.mouth_param,
    )
    c.print("[dim]   ถ้านี่เป็นครั้งแรก ให้ไปกด Allow ในหน้าต่าง VTube Studio ตอนนี้[/]")
    if not await vts.connect():
        c.print(f"[red]   ✗ ต่อไม่ได้:[/] {vts.last_error}")
        c.print("   ตรวจ: เปิด VTube Studio แล้ว? Settings > Start API เปิดแล้ว? พอร์ต 8001?")
        return
    c.print("[green]   ✓ ต่อสำเร็จ[/]")

    # -- 2. โมเดล + พารามิเตอร์ -------------------------------------------
    model = await vts.current_model()
    c.print(f"\n[bold]2) โมเดลที่โหลดอยู่:[/] {model.get('modelName') or '(ไม่มีโมเดล!)'}")
    if not model.get("modelLoaded"):
        c.print("[yellow]   ! ยังไม่ได้โหลดโมเดล Live2D — ไปเลือกโมเดลใน VTube Studio ก่อน[/]")

    params = await vts.input_parameters()
    names = [p.get("name", "") for p in params]
    c.print(f"   พารามิเตอร์ที่ฉีดค่าได้ {len(names)} ตัว")
    mouth_like = [n for n in names if "mouth" in n.lower() or "voice" in n.lower()]
    c.print(f"   ที่เกี่ยวกับปาก/เสียง: {', '.join(mouth_like) or '(ไม่เจอ)'}")

    want = cfg.avatar.mouth_param
    if want in names:
        c.print(f"[green]   ✓ ใช้ '{want}' ได้[/]")
    else:
        c.print(f"[yellow]   ! ไม่เจอ '{want}' — ลองเปลี่ยน avatar.mouth_param ใน config.yaml "
                f"เป็นตัวใดตัวหนึ่งข้างบน[/]")

    # -- 3. กวาดค่าปาก ------------------------------------------------------
    c.print(f"\n[bold]3) ทดสอบขยับปาก[/] (ฉีดค่า '{want}' ขึ้น-ลง 3 รอบ — ดูที่อวตาร)")
    fps = cfg.avatar.fps
    for i in range(fps * 3):
        v = (math.sin(i / fps * 2 * math.pi) + 1) / 2   # 0..1 นุ่ม ๆ
        await vts.set_mouth(v)
        await asyncio.sleep(1 / fps)
    await vts.set_mouth(0.0)
    c.print("[green]   ✓ ส่งค่าครบแล้ว[/] — ถ้าปากไม่ขยับ ดูหัวข้อ 2 ว่าชื่อพารามิเตอร์ตรงไหม")

    # -- 4. พูดจริง ---------------------------------------------------------
    c.print(f"\n[bold]4) พูดจริงพร้อมขยับปาก[/] (เอนจินเสียง: {cfg.tts.engine})")
    tts = TTSManager(cfg)
    await asyncio.to_thread(tts.warmup)
    player = Player(
        vts, fps=cfg.avatar.fps, gain=cfg.avatar.gain,
        attack=cfg.avatar.smoothing_attack, release=cfg.avatar.smoothing_release,
        noise_gate=cfg.avatar.noise_gate,
    )
    text = "สวัสดีค่ะ ไอริสเองนะคะ ตอนนี้ปากของเราขยับตามเสียงพูดได้แล้ว ลองดูสิคะ"
    c.print(f"   [dim]{text}[/]")
    wavs = await asyncio.to_thread(tts.synthesize, text)
    await player.speak(wavs)
    c.print("[green]   ✓ เสร็จ[/]")

    await vts.close()
    c.print("\n[bold green]ทดสอบครบแล้ว[/]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
