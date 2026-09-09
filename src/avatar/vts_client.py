"""ไคลเอนต์ VTube Studio Plugin API (WebSocket) — ฉีดค่าพารามิเตอร์ปาก.

โปรโตคอล: https://github.com/DenchiSoft/VTubeStudio
ครั้งแรกที่ต่อ VTS จะเด้ง popup ให้ผู้ใช้กด Allow แล้วเราเก็บ token ไว้ใช้ครั้งถัดไป.
ถ้า VTS ไม่เปิด/ต่อไม่ได้ → ไม่ throw, แค่ทำงานแบบ "ไม่มีอวตาร" (เสียงยังออกปกติ).
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import websockets

_API = {"apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0"}


class VTSClient:
    def __init__(
        self,
        url: str,
        plugin_name: str,
        plugin_developer: str,
        token_file: Path,
        mouth_param: str = "MouthOpen",
    ):
        self.url = url
        self.plugin_name = plugin_name
        self.plugin_developer = plugin_developer
        self.token_file = Path(token_file)
        self.mouth_param = mouth_param
        self._ws: websockets.WebSocketClientProtocol | None = None
        self.connected = False
        self.last_error: str | None = None

    # ------------------------------------------------------------------ #
    def _msg(self, message_type: str, data: dict | None = None) -> str:
        return json.dumps(
            {**_API, "requestID": uuid.uuid4().hex, "messageType": message_type, "data": data or {}}
        )

    async def _rpc(self, message_type: str, data: dict | None = None) -> dict:
        await self._ws.send(self._msg(message_type, data))
        return json.loads(await self._ws.recv())

    # ------------------------------------------------------------------ #
    async def connect(self) -> bool:
        try:
            self._ws = await websockets.connect(self.url, max_size=2**20, open_timeout=5)
            await self._authenticate()
            self.connected = True
            return True
        except Exception as e:  # noqa: BLE001 - อยากจับทุกอย่างเพื่อ degrade อย่างนุ่มนวล
            self.last_error = f"{type(e).__name__}: {e}"
            self.connected = False
            return False

    async def _authenticate(self) -> None:
        token = self.token_file.read_text(encoding="utf-8").strip() if self.token_file.exists() else ""

        if not token:
            resp = await self._rpc(
                "AuthenticationTokenRequest",
                {"pluginName": self.plugin_name, "pluginDeveloper": self.plugin_developer},
            )
            token = resp.get("data", {}).get("authenticationToken", "")
            if not token:
                raise RuntimeError(f"ขอ auth token ไม่สำเร็จ: {resp.get('data')}")
            self.token_file.write_text(token, encoding="utf-8")

        resp = await self._rpc(
            "AuthenticationRequest",
            {
                "pluginName": self.plugin_name,
                "pluginDeveloper": self.plugin_developer,
                "authenticationToken": token,
            },
        )
        if not resp.get("data", {}).get("authenticated"):
            # token เสีย → ลบทิ้งแล้วให้รอบหน้าขอใหม่
            self.token_file.unlink(missing_ok=True)
            raise RuntimeError(f"authenticate ไม่ผ่าน: {resp.get('data', {}).get('reason')}")

    # ------------------------------------------------------------------ #
    async def set_mouth(self, value: float) -> None:
        """ตั้งค่าปาก 0.0–1.0 (no-op ถ้ายังไม่ connected)."""
        if not self.connected or self._ws is None:
            return
        v = 0.0 if value < 0 else 1.0 if value > 1 else float(value)
        try:
            await self._ws.send(
                self._msg(
                    "InjectParameterDataRequest",
                    {
                        "faceFound": False,
                        "mode": "set",
                        "parameterValues": [{"id": self.mouth_param, "value": v}],
                    },
                )
            )
        except Exception as e:  # noqa: BLE001
            self.last_error = f"{type(e).__name__}: {e}"
            self.connected = False

    async def input_parameters(self) -> list[dict]:
        """รายชื่อพารามิเตอร์อินพุตที่ VTS ฉีดค่าได้ (ใช้เช็กว่า mouth_param ถูกไหม)."""
        if not self.connected:
            return []
        resp = await self._rpc("InputParameterListRequest")
        return resp.get("data", {}).get("defaultParameters", []) + resp.get("data", {}).get(
            "customParameters", []
        )

    async def current_model(self) -> dict:
        """ข้อมูลโมเดล Live2D ที่โหลดอยู่ตอนนี้."""
        if not self.connected:
            return {}
        resp = await self._rpc("CurrentModelRequest")
        return resp.get("data", {})

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self.set_mouth(0.0)
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
        self.connected = False
