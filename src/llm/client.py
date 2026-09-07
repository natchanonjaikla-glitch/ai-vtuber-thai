"""ไคลเอนต์คุยกับ LLM ในเครื่องผ่าน LM Studio (OpenAI-compatible API)."""
from __future__ import annotations

from collections.abc import Iterator

from openai import APIConnectionError, APIStatusError, OpenAI

from src.config import LLMConfig


class LLMUnavailable(RuntimeError):
    """ยิงเมื่อต่อ LM Studio ไม่ได้ — ข้อความอ่านรู้เรื่องสำหรับผู้ใช้."""


class LLMClient:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self._client = OpenAI(
            base_url=cfg.base_url,
            api_key=cfg.api_key or "lm-studio",
            timeout=cfg.timeout_sec,
            max_retries=1,
        )

    # ------------------------------------------------------------------ #
    def _hint(self) -> str:
        return (
            f"ต่อ LM Studio ไม่ได้ที่ {self.cfg.base_url}\n"
            "  • เปิดแอป LM Studio → แท็บ Developer → กด Start Server (พอร์ต 1234)\n"
            "  • ตรวจว่าโหลดโมเดลไว้แล้ว และชื่อใน config.yaml (llm.model) ตรงกัน"
        )

    def chat(self, messages: list[dict[str, str]]) -> str:
        try:
            resp = self._client.chat.completions.create(
                model=self.cfg.model,
                messages=messages,
                temperature=self.cfg.temperature,
                max_tokens=self.cfg.max_tokens,
            )
        except APIConnectionError as e:
            raise LLMUnavailable(self._hint()) from e
        except APIStatusError as e:
            raise LLMUnavailable(f"LM Studio ตอบ error {e.status_code}: {e.message}") from e
        return (resp.choices[0].message.content or "").strip()

    def chat_stream(self, messages: list[dict[str, str]]) -> Iterator[str]:
        """สตรีมโทเคน — เตรียมไว้สำหรับ streaming TTS ใน v2."""
        try:
            stream = self._client.chat.completions.create(
                model=self.cfg.model,
                messages=messages,
                temperature=self.cfg.temperature,
                max_tokens=self.cfg.max_tokens,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except APIConnectionError as e:
            raise LLMUnavailable(self._hint()) from e

    def ping(self) -> bool:
        """เช็กเร็ว ๆ ว่า server ตอบไหม (ใช้ใน setup_check / ตอนสตาร์ท)."""
        try:
            self._client.models.list()
            return True
        except Exception:
            return False
