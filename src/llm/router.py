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
_SEARCH_RE = re.compile(
    r"\[\[\s*SEARCH\s*:\s*(?P<query>.+?)\s*\]\]",
    re.IGNORECASE | re.DOTALL,
)
_EMOTION_RE = re.compile(
    r"\[\[\s*EMOTION\s*:\s*(?P<emotion>[a-zA-Z_]+)\s*\]\]",
    re.IGNORECASE,
)


@dataclass
class RouteResult:
    mode: str            # "chat" | "delegate_code" | "search"
    task: str = ""       # งานสำหรับ Claude / คำค้นสำหรับเว็บ


class Router:
    def __init__(self, code_triggers: list[str], search_triggers: list[str] | None = None):
        self.code_triggers = [t.strip().lower() for t in code_triggers if t.strip()]
        self.search_triggers = [t.strip().lower() for t in (search_triggers or []) if t.strip()]

    # ---------------------------------------------------------------- #
    @staticmethod
    def _strip_trigger(text: str, trig: str) -> str:
        out = re.sub(re.escape(trig), "", text, count=1, flags=re.IGNORECASE)
        return out.strip(" :：-—\t")

    def pre_route(self, user_text: str) -> RouteResult:
        low = user_text.lower()
        # งานเขียนโค้ดมาก่อน — คำว่า "ช่วยเขียนโค้ด" ชัดเจนกว่าคำค้นทั่วไป
        for trig in self.code_triggers:
            if trig in low:
                task = self._strip_trigger(user_text, trig)
                return RouteResult("delegate_code", task or user_text.strip())
        for trig in self.search_triggers:
            if trig in low:
                q = self._strip_trigger(user_text, trig)
                return RouteResult("search", q or user_text.strip())
        return RouteResult("chat")

    # ---------------------------------------------------------------- #
    @staticmethod
    def _extract(pattern: re.Pattern, group: str, text: str) -> tuple[str, str | None]:
        m = pattern.search(text)
        if not m:
            return text, None
        value = m.group(group).strip()
        cleaned = pattern.sub("", text).strip()
        # กันเคสโมเดลใส่ placeholder มาเฉย ๆ
        if not value or (value.startswith("<") and value.endswith(">")):
            return cleaned, None
        return cleaned, value

    @classmethod
    def extract_delegation(cls, assistant_text: str) -> tuple[str, str | None]:
        """คืน (ข้อความที่ตัดมาร์กเกอร์ออกแล้ว, task สำหรับ Claude หรือ None)."""
        return cls._extract(_MARKER_RE, "task", assistant_text)

    @classmethod
    def extract_search(cls, assistant_text: str) -> tuple[str, str | None]:
        """คืน (ข้อความที่ตัดมาร์กเกอร์ออกแล้ว, คำค้นเว็บ หรือ None)."""
        return cls._extract(_SEARCH_RE, "query", assistant_text)

    @classmethod
    def extract_emotion(cls, assistant_text: str) -> tuple[str, str | None]:
        """คืน (ข้อความที่ตัดมาร์กเกอร์ออกแล้ว, ชื่ออารมณ์ หรือ None)."""
        return cls._extract(_EMOTION_RE, "emotion", assistant_text)
