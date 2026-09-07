"""จัดการ TTS: เลือกเอนจิน, แบ่งข้อความเป็นก้อน, cache, คืนลำดับไฟล์ wav."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from src.config import AppConfig
from src.tts.base import TTSEngine
from src.tts.mms import MMSEngine

# ตัดอิโมจิ / สัญลักษณ์ที่อ่านออกเสียงไม่ได้ออกก่อนส่งเข้า TTS
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF←-⇿⌀-⏿]"
)
_MULTI_WS_RE = re.compile(r"\s+")


def _clean(text: str) -> str:
    text = _EMOJI_RE.sub("", text)
    text = text.replace("*", "").replace("`", "").replace("#", "")
    return _MULTI_WS_RE.sub(" ", text).strip()


def split_sentences(text: str, max_chars: int) -> list[str]:
    """แบ่งเป็นประโยคด้วย pythainlp (ถ้ามี) แล้วรวม/ซอยให้ยาวไม่เกิน max_chars."""
    text = _clean(text)
    if not text:
        return []

    pieces: list[str]
    try:
        from pythainlp.tokenize import sent_tokenize

        pieces = [s.strip() for s in sent_tokenize(text) if s.strip()]
    except Exception:
        pieces = [s.strip() for s in re.split(r"(?<=[.!?ฯ])\s+|\n+", text) if s.strip()]

    if not pieces:
        pieces = [text]

    # รวมก้อนสั้น ๆ ต่อกัน และซอยก้อนที่ยาวเกิน
    out: list[str] = []
    buf = ""
    for p in pieces:
        if len(p) > max_chars:
            if buf:
                out.append(buf)
                buf = ""
            out.extend(_hard_wrap(p, max_chars))
            continue
        if len(buf) + len(p) + 1 <= max_chars:
            buf = f"{buf} {p}".strip()
        else:
            if buf:
                out.append(buf)
            buf = p
    if buf:
        out.append(buf)
    return out


def _hard_wrap(s: str, max_chars: int) -> list[str]:
    words = s.split(" ")
    chunks, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = f"{cur} {w}".strip()
        else:
            if cur:
                chunks.append(cur)
            cur = w
    if cur:
        chunks.append(cur)
    return chunks or [s[:max_chars]]


class TTSManager:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.cache_dir = cfg.resolve(cfg.tts.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._engines: dict[str, TTSEngine] = {}
        self.engine_name = cfg.tts.engine

    # ------------------------------------------------------------------ #
    def _build_engine(self, name: str) -> TTSEngine:
        if name == "mms":
            return MMSEngine(self.cfg.tts.mms, self.cfg.tts.cpu_threads)
        if name == "f5":
            from src.tts.f5_thai import F5ThaiEngine

            return F5ThaiEngine(self.cfg.tts.f5, self.cfg.project_root, self.cfg.tts.cpu_threads)
        raise ValueError(f"ไม่รู้จักเอนจิน TTS: {name!r} (รองรับ: mms, f5)")

    def get_engine(self, name: str | None = None) -> TTSEngine:
        name = name or self.engine_name
        if name not in self._engines:
            self._engines[name] = self._build_engine(name)
        return self._engines[name]

    def set_engine(self, name: str) -> None:
        self.get_engine(name)          # สร้าง/validate
        self.engine_name = name

    def warmup(self) -> None:
        self.get_engine().load()

    @property
    def sample_rate(self) -> int:
        return self.get_engine().sample_rate

    # ------------------------------------------------------------------ #
    def synthesize(self, text: str) -> list[Path]:
        """คืนลำดับ wav (1 ไฟล์/ประโยค) พร้อมเล่นต่อกัน."""
        engine = self.get_engine()
        if not engine.loaded:
            engine.load()

        chunks = split_sentences(text, self.cfg.tts.max_chars_per_chunk)
        paths: list[Path] = []
        for chunk in chunks:
            key = hashlib.sha1(
                f"{engine.name}|{engine.sample_rate}|{chunk}".encode()
            ).hexdigest()[:16]
            out = self.cache_dir / f"{engine.name}_{key}.wav"
            if not out.exists():
                engine.synth(chunk, out)
            paths.append(out)
        return paths
