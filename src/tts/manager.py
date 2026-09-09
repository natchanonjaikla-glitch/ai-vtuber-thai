"""จัดการ TTS: เลือกเอนจิน, แบ่งข้อความเป็นก้อน, cache, คืนลำดับไฟล์ wav."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from src.config import AppConfig
from src.tts.base import TTSEngine
from src.tts.mms import MMSEngine

# ชื่อเอนจินที่รองรับ → คำอธิบายสั้น ๆ (ใช้ใน /voice และข้อความ error)
ENGINES = {
    "piper": "ไทย ธรรมชาติพอควร เร็วมาก offline (แนะนำ)",
    "edge":  "ธรรมชาติที่สุด เร็วมาก แต่ต้องต่อเน็ต",
    "mms":   "เร็ว offline แต่เสียงหุ่นยนต์",
    "f5":    "โคลนเสียงได้ offline แต่ช้ามาก (~6 นาที/ประโยค)",
}

# ตัดอิโมจิ / สัญลักษณ์ที่อ่านออกเสียงไม่ได้ออกก่อนส่งเข้า TTS
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF←-⇿⌀-⏿]"
)
_MULTI_WS_RE = re.compile(r"\s+")


# เอนจินเสียงไทย (Piper/MMS) อ่านตัวอักษรละตินไม่ได้ — มันจะ "ตัดทิ้งเงียบ ๆ"
# ทำให้คำหายไปจากเสียง จึงแปลงเป็นคำอ่านไทยก่อน
_LATIN_WORDS = {
    "vtuber": "วีทูเบอร์", "ai": "เอไอ", "api": "เอพีไอ", "python": "ไพธอน",
    "javascript": "จาวาสคริปต์", "code": "โค้ด", "claude": "คล็อด", "github": "กิตฮับ",
    "server": "เซิร์ฟเวอร์", "error": "เออเรอร์", "bug": "บั๊ก", "file": "ไฟล์",
    "computer": "คอมพิวเตอร์", "internet": "อินเทอร์เน็ต", "online": "ออนไลน์",
    "live": "ไลฟ์", "stream": "สตรีม", "game": "เกม", "ok": "โอเค", "hello": "ฮัลโหล",
    "windows": "วินโดวส์", "google": "กูเกิล", "youtube": "ยูทูบ", "discord": "ดิสคอร์ด",
    # คำย่อที่คนไทยอ่านเป็นคำ ไม่ได้สะกดทีละตัว
    "ram": "แรม", "rom": "รอม", "app": "แอป", "pc": "พีซี", "tv": "ทีวี",
}
# ตัวอักษรละตินทีละตัว (ใช้กับคำย่อ เช่น CPU GPU RAM)
_LATIN_LETTERS = {
    "a": "เอ", "b": "บี", "c": "ซี", "d": "ดี", "e": "อี", "f": "เอฟ", "g": "จี",
    "h": "เอช", "i": "ไอ", "j": "เจ", "k": "เค", "l": "แอล", "m": "เอ็ม", "n": "เอ็น",
    "o": "โอ", "p": "พี", "q": "คิว", "r": "อาร์", "s": "เอส", "t": "ที", "u": "ยู",
    "v": "วี", "w": "ดับเบิลยู", "x": "เอ็กซ์", "y": "วาย", "z": "แซด",
}
_LATIN_RUN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")


def _latin_to_thai(match: re.Match) -> str:
    word = match.group(0)
    low = word.lower()
    if low in _LATIN_WORDS:
        return _LATIN_WORDS[low]
    # คำย่อตัวพิมพ์ใหญ่สั้น ๆ (CPU, GPU, RAM, HTML) → สะกดทีละตัว
    if word.isupper() and 2 <= len(word) <= 5:
        return "".join(_LATIN_LETTERS.get(c.lower(), c) for c in word)
    # คำอังกฤษอื่น ๆ สะกดทีละตัวจะฟังไม่รู้เรื่อง ปล่อยให้เอนจินตัดทิ้งเอง
    return word


def _clean(text: str) -> str:
    text = _EMOJI_RE.sub("", text)
    text = text.replace("*", "").replace("`", "").replace("#", "")
    text = _LATIN_RUN_RE.sub(_latin_to_thai, text)
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
        if name == "piper":
            from src.tts.piper_th import PiperEngine

            return PiperEngine(self.cfg.tts.piper, self.cfg.tts.cpu_threads)
        if name == "edge":
            from src.tts.edge import EdgeEngine

            return EdgeEngine(self.cfg.tts.edge)
        if name == "mms":
            return MMSEngine(self.cfg.tts.mms, self.cfg.tts.cpu_threads)
        if name == "f5":
            from src.tts.f5_thai import F5ThaiEngine

            return F5ThaiEngine(self.cfg.tts.f5, self.cfg.project_root, self.cfg.tts.cpu_threads)
        raise ValueError(f"ไม่รู้จักเอนจิน TTS: {name!r} (รองรับ: {', '.join(ENGINES)})")

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

            # ไฟล์เล็กเกินไป = ค้างจากรอบที่พัง ถือว่าไม่มี
            if out.exists() and out.stat().st_size < 128:
                out.unlink(missing_ok=True)

            if not out.exists():
                # เขียนลงไฟล์ชั่วคราวก่อนแล้วค่อย rename — ถ้า synth พังกลางคัน
                # จะไม่เหลือไฟล์เสียใน cache ให้รอบหน้าไปอ่าน
                # ต้องลงท้าย .wav เพราะ soundfile เดา format จากนามสกุล
                tmp = out.with_name(f"~{out.stem}.part.wav")
                try:
                    engine.synth(chunk, tmp)
                    if not tmp.exists() or tmp.stat().st_size < 128:
                        raise RuntimeError(
                            f"เอนจิน {engine.name} สังเคราะห์เสียงไม่ออก (ไฟล์ว่าง) สำหรับ: {chunk[:40]!r}"
                        )
                    tmp.replace(out)
                finally:
                    tmp.unlink(missing_ok=True)
            paths.append(out)
        return paths
