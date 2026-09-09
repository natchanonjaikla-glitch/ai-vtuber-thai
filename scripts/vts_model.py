"""ดู / สั่งโหลดโมเดล Live2D ใน VTube Studio ผ่าน API

    .venv\\Scripts\\python.exe -u scripts\\vts_model.py            # แสดงรายชื่อ
    .venv\\Scripts\\python.exe -u scripts\\vts_model.py hiyori     # โหลดตัวที่ชื่อขึ้นต้นด้วย hiyori
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.avatar.vts_client import VTSClient  # noqa: E402
from src.config import load_config  # noqa: E402


async def main() -> int:
    want = sys.argv[1].lower() if len(sys.argv) > 1 else None
    cfg = load_config()
    vts = VTSClient(
        url=cfg.avatar.vts_url,
        plugin_name=cfg.avatar.plugin_name,
        plugin_developer=cfg.avatar.plugin_developer,
        token_file=cfg.resolve(cfg.avatar.token_file),
        mouth_param=cfg.avatar.mouth_param,
    )
    if not await vts.connect():
        print(f"[X] ต่อ VTube Studio ไม่ได้: {vts.last_error}")
        return 1

    models = await vts.available_models()
    if not models:
        print("[X] VTS ไม่เห็นโมเดลเลย")
        await vts.close()
        return 1

    current = await vts.current_model()
    print(f"โมเดลที่โหลดอยู่ตอนนี้: {current.get('modelName') or '(ไม่มี)'}\n")
    print(f"โมเดลที่มี {len(models)} ตัว:")
    for m in models:
        mark = " <-- โหลดอยู่" if m.get("modelLoaded") else ""
        print(f"  - {m.get('modelName')}{mark}")

    if want:
        target = next((m for m in models if want in (m.get("modelName") or "").lower()), None)
        if not target:
            print(f"\n[X] ไม่เจอโมเดลที่ตรงกับ {want!r}")
            await vts.close()
            return 1
        print(f"\nกำลังโหลด: {target['modelName']} ...")
        res = await vts.load_model(target["modelID"])
        await asyncio.sleep(2.5)  # รอ VTS โหลดเสร็จ
        now = await vts.current_model()
        print(f"[OK] โหลดแล้ว: {now.get('modelName')}" if now.get("modelLoaded")
              else f"[X] โหลดไม่สำเร็จ: {res}")

    await vts.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
