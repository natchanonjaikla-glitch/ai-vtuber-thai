"""ขออนุญาตเชื่อมต่อ VTube Studio ครั้งเดียว แล้วเก็บ token ไว้ใช้ตลอด

    .venv\\Scripts\\python.exe -u scripts\\vts_auth.py

จะเด้ง popup ใน VTube Studio ให้กด Allow (รอได้ 5 นาที)
พอได้ token แล้วเก็บลง .vts_token — ครั้งต่อไปไม่ถามอีก
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import websockets  # noqa: E402

from src.config import load_config  # noqa: E402

_API = {"apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0"}
WAIT_SECONDS = 300


def _msg(mtype: str, data: dict) -> str:
    return json.dumps({**_API, "requestID": uuid.uuid4().hex, "messageType": mtype, "data": data})


async def main() -> int:
    cfg = load_config()
    token_file = cfg.resolve(cfg.avatar.token_file)

    if token_file.exists() and token_file.read_text(encoding="utf-8").strip():
        print(f"มี token อยู่แล้วที่ {token_file}")
        print("ถ้าอยากขอใหม่ ให้ลบไฟล์นี้ก่อน")
        return 0

    print(f"ต่อ {cfg.avatar.vts_url} ...")
    try:
        ws = await websockets.connect(cfg.avatar.vts_url, open_timeout=8)
    except Exception as e:  # noqa: BLE001
        print(f"[X] ต่อไม่ได้: {type(e).__name__}: {e}")
        print("    เช็ก: VTube Studio เปิดอยู่? Settings > Start API (allow plugins) = ON?")
        return 1

    async with ws:
        await ws.send(
            _msg(
                "AuthenticationTokenRequest",
                {
                    "pluginName": cfg.avatar.plugin_name,
                    "pluginDeveloper": cfg.avatar.plugin_developer,
                },
            )
        )
        print()
        print("=" * 62)
        print("  >>> ไปที่หน้าต่าง VTube Studio แล้วกด Allow ใน popup ตอนนี้ <<<")
        print(f"      (ปลั๊กอินชื่อ \"{cfg.avatar.plugin_name}\")")
        print(f"      รอได้ {WAIT_SECONDS // 60} นาที — อย่าปิดหน้าต่างนี้")
        print("=" * 62)
        print()

        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=WAIT_SECONDS)
        except asyncio.TimeoutError:
            print(f"[X] รอเกิน {WAIT_SECONDS} วินาที ยังไม่ได้กด Allow")
            return 1

        data = json.loads(raw).get("data", {})
        token = data.get("authenticationToken", "")
        if not token:
            print(f"[X] ไม่ได้ token: {data}")
            return 1

        token_file.write_text(token, encoding="utf-8")
        print(f"[OK] ได้ token แล้ว เก็บที่ {token_file}")

        # ยืนยันว่า token ใช้ได้จริง
        await ws.send(
            _msg(
                "AuthenticationRequest",
                {
                    "pluginName": cfg.avatar.plugin_name,
                    "pluginDeveloper": cfg.avatar.plugin_developer,
                    "authenticationToken": token,
                },
            )
        )
        ok = json.loads(await ws.recv()).get("data", {}).get("authenticated")
        print(f"[OK] ยืนยัน authenticate: {ok}" if ok else "[X] token ใช้ไม่ได้")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
