"""ตัดสินใจว่าข้อความควรไป "คุยเล่น" หรือ "ส่งงานให้ Claude Code".

สองชั้น:
  1. pre_route()          — ผู้ใช้พิมพ์ trigger phrase → ส่งงานทันที (ไม่ต้องพึ่งโมเดล)
  2. extract_delegation() — โมเดลตอบมาพร้อมมาร์กเกอร์ [[DELEGATE_TO_CLAUDE: ...]]
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_MARKER_RE = re.compile(
    r"\[\[\s*DELEGATE_TO_CLAUDE\s*:\s*(?P<task>.+?)\s*\]\]",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class RouteResult:
    mode: str            # "chat" | "delegate_code"
    task: str = ""       # คำสั่งงานสำหรับ Claude (เมื่อ mode == delegate_code)


class Router:
    def __init__(self, trigger_phrases: list[str]):
        self.triggers = [t.strip().lower() for t in trigger_phrases if t.strip()]

    # ---------------------------------------------------------------- #
    def pre_route(self, user_text: str) -> RouteResult:
        low = user_text.lower()
        for trig in self.triggers:
            if trig in low:
                # ตัดคำ trigger ออก เหลือส่วนที่เป็นรายละเอียดงาน
                task = re.sub(re.escape(trig), "", user_text, count=1, flags=re.IGNORECASE)
                task = task.strip(" :：-—\t")
                return RouteResult("delegate_code", task or user_text.strip())
        return RouteResult("chat")

    # ---------------------------------------------------------------- #
    @staticmethod
    def extract_delegation(assistant_text: str) -> tuple[str, str | None]:
        """คืน (ข้อความที่ตัดมาร์กเกอร์ออกแล้ว, task หรือ None)."""
        m = _MARKER_RE.search(assistant_text)
        if not m:
            return assistant_text, None
        task = m.group("task").strip()
        cleaned = _MARKER_RE.sub("", assistant_text).strip()
        # กันเคสโมเดลใส่ placeholder มาเฉย ๆ
        if not task or task.startswith("<") and task.endswith(">"):
            return cleaned, None
        return cleaned, task
