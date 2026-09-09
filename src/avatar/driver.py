"""ตัวขับอวตาร — ยิงค่าพารามิเตอร์ทุกตัวให้ VTS ต่อเนื่องที่อัตราเฟรมคงที่

ทำไมต้องยิงตลอด: VTS ถือว่าค่าที่ฉีดเข้ามาเป็นค่าชั่วคราว ถ้าหยุดส่งมันจะกลับไป
ใช้ค่าจาก face tracking ทันที ตัวละครเลยต้องได้รับค่าตลอดเวลาถึงจะคงสีหน้าไว้ได้

รวมทุกอย่างไว้ที่เดียว:
  - อารมณ์ (ค่อย ๆ เปลี่ยนเข้าหาเป้าหมาย ไม่กระตุก)
  - ขยับหัว/หายใจเบา ๆ ตอนอยู่เฉย ไม่ให้ดูแข็งทื่อ
  - กะพริบตาเป็นระยะ
  - ปาก (อ้าตามความดัง + ขึ้นรูปตามสระ) ซึ่ง Player เป็นคนป้อนเข้ามา
"""
from __future__ import annotations

import asyncio
import math
import random
import time

from src.avatar.expressions import NEUTRAL, resolve_emotion
from src.avatar.vts_client import VTSClient

_MOUTH_KEYS = ("MouthOpen", "VoiceA", "VoiceI", "VoiceU", "VoiceE", "VoiceO", "MouthX")


class AvatarDriver:
    def __init__(
        self,
        vts: VTSClient | None,
        fps: int = 30,
        blend: float = 0.15,
        idle_amount: float = 1.0,
        blink_min_sec: float = 2.5,
        blink_max_sec: float = 6.0,
    ):
        self.vts = vts
        self.fps = max(5, fps)
        self.blend = min(max(blend, 0.01), 1.0)   # ยิ่งมากยิ่งเปลี่ยนอารมณ์ไว
        self.idle_amount = idle_amount
        self.blink_min = blink_min_sec
        self.blink_max = blink_max_sec

        self.emotion = "neutral"
        self._target: dict[str, float] = dict(NEUTRAL)
        self._current: dict[str, float] = dict(NEUTRAL)
        self._mouth: dict[str, float] = dict.fromkeys(_MOUTH_KEYS, 0.0)

        self._task: asyncio.Task | None = None
        self._running = False
        self._t0 = time.monotonic()
        self._next_blink = self._t0 + random.uniform(blink_min_sec, blink_max_sec)
        self._blink_until = 0.0

    # ------------------------------------------------------------------ #
    def set_emotion(self, name: str) -> None:
        self.emotion = (name or "neutral").strip().lower()
        self._target = resolve_emotion(self.emotion)

    def set_mouth(self, mouth_open: float, vowels: dict[str, float] | None = None) -> None:
        """Player เรียกทุกเฟรมระหว่างพูด."""
        self._mouth["MouthOpen"] = float(mouth_open)
        if vowels:
            for k in ("VoiceA", "VoiceI", "VoiceU", "VoiceE", "VoiceO"):
                self._mouth[k] = float(vowels.get(k, 0.0))

    def clear_mouth(self) -> None:
        for k in _MOUTH_KEYS:
            self._mouth[k] = 0.0

    # ------------------------------------------------------------------ #
    def _idle(self, t: float) -> dict[str, float]:
        """ขยับหัว/ตัวช้า ๆ ให้ดูมีชีวิต (คาบไม่ลงตัวกัน จะได้ไม่ดูเป็นลูป)."""
        a = self.idle_amount
        return {
            "FaceAngleX": 2.2 * a * math.sin(t * 0.37),
            "FaceAngleY": 1.6 * a * math.sin(t * 0.29 + 1.1),
            "FaceAngleZ": 2.8 * a * math.sin(t * 0.23 + 2.7),
            "FacePositionY": 0.25 * a * math.sin(t * 0.8),   # หายใจ
        }

    def _blink(self, now: float) -> float:
        """คืนตัวคูณการเปิดตา (1 = เปิดปกติ, 0 = หลับ)."""
        if now >= self._next_blink:
            self._blink_until = now + 0.13
            self._next_blink = now + random.uniform(self.blink_min, self.blink_max)
        if now < self._blink_until:
            # ครึ่งแรกหลับ ครึ่งหลังลืม
            p = 1.0 - (self._blink_until - now) / 0.13
            return abs(math.cos(p * math.pi))
        return 1.0

    # ------------------------------------------------------------------ #
    async def _loop(self) -> None:
        period = 1.0 / self.fps
        while self._running:
            now = time.monotonic()
            t = now - self._t0

            # ค่อย ๆ ขยับค่าปัจจุบันเข้าหาอารมณ์เป้าหมาย
            for k, target in self._target.items():
                cur = self._current.get(k, 0.0)
                self._current[k] = cur + self.blend * (target - cur)

            frame = dict(self._current)

            idle = self._idle(t)
            for k, v in idle.items():
                frame[k] = frame.get(k, 0.0) + v

            blink = self._blink(now)
            frame["EyeOpenLeft"] = frame.get("EyeOpenLeft", 0.85) * blink
            frame["EyeOpenRight"] = frame.get("EyeOpenRight", 0.85) * blink

            frame.update(self._mouth)

            # ปากยิ้มค้างไว้ตอนอ้าปากกว้างจะดูแปลก ลดลงตามการอ้า
            frame["MouthSmile"] = frame.get("MouthSmile", 0.0) * (
                1.0 - 0.5 * frame.get("MouthOpen", 0.0)
            )

            if self.vts is not None:
                await self.vts.set_params(frame)
            await asyncio.sleep(period)

    async def start(self) -> None:
        if self._task is not None or self.vts is None:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None
