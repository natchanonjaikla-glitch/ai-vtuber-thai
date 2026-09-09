"""ท่าทาง/สีหน้าของอวตาร + การเดาสระจากเสียงจริง

สองส่วน:
  1. EMOTIONS — ชุดค่าพารามิเตอร์สำเร็จรูปของแต่ละอารมณ์
  2. vowel_weights_from_audio — วิเคราะห์ฟอร์แมนต์ (F1/F2) เพื่อเดาว่าเสียงที่กำลัง
     พูดอยู่เป็นสระอะไร แล้วส่งเป็นน้ำหนัก VoiceA/I/U/E/O ให้ปากขึ้นรูปตามสระ
     (Piper ไม่ได้ให้จังหวะของแต่ละเสียงมา เลยต้องอ่านจากตัวเสียงเอง)
"""
from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
#  อารมณ์
# ---------------------------------------------------------------------------
# ค่าอ้างอิงช่วงของ VTS: MouthSmile/Brows/EyeOpen*/FaceAngry/CheekPuff = 0..1,
# FaceAngleX/Y = -30..30, FaceAngleZ = -90..90, EyeLeftX/Y = -1..1
NEUTRAL: dict[str, float] = {
    "MouthSmile": 0.30,
    "Brows": 0.50,
    "BrowLeftY": 0.50,
    "BrowRightY": 0.50,
    "EyeOpenLeft": 0.85,
    "EyeOpenRight": 0.85,
    "FaceAngry": 0.0,
    "CheekPuff": 0.0,
    "FaceAngleX": 0.0,
    "FaceAngleY": 0.0,
    "FaceAngleZ": 0.0,
    "EyeLeftX": 0.0,
    "EyeRightX": 0.0,
    "EyeLeftY": 0.0,
    "EyeRightY": 0.0,
}

EMOTIONS: dict[str, dict[str, float]] = {
    "neutral": {},
    "happy": {
        "MouthSmile": 0.95, "Brows": 0.70, "BrowLeftY": 0.70, "BrowRightY": 0.70,
        "EyeOpenLeft": 0.75, "EyeOpenRight": 0.75, "FaceAngleZ": 4.0,
    },
    "excited": {
        "MouthSmile": 1.0, "Brows": 0.95, "BrowLeftY": 0.95, "BrowRightY": 0.95,
        "EyeOpenLeft": 1.0, "EyeOpenRight": 1.0, "FaceAngleX": 3.0, "FaceAngleZ": -5.0,
    },
    "sad": {
        "MouthSmile": 0.05, "Brows": 0.15, "BrowLeftY": 0.15, "BrowRightY": 0.15,
        "EyeOpenLeft": 0.55, "EyeOpenRight": 0.55, "FaceAngleY": -7.0, "EyeLeftY": -0.4,
        "EyeRightY": -0.4,
    },
    "surprised": {
        "MouthSmile": 0.25, "Brows": 1.0, "BrowLeftY": 1.0, "BrowRightY": 1.0,
        "EyeOpenLeft": 1.0, "EyeOpenRight": 1.0, "FaceAngleY": 4.0,
    },
    "angry": {
        "FaceAngry": 0.9, "MouthSmile": 0.0, "Brows": 0.05,
        "BrowLeftY": 0.05, "BrowRightY": 0.05,
        "EyeOpenLeft": 0.7, "EyeOpenRight": 0.7, "FaceAngleX": -4.0,
    },
    "shy": {
        "MouthSmile": 0.45, "Brows": 0.35, "BrowLeftY": 0.35, "BrowRightY": 0.35,
        "EyeOpenLeft": 0.55, "EyeOpenRight": 0.55, "CheekPuff": 0.25,
        "FaceAngleZ": 10.0, "FaceAngleY": -5.0, "EyeLeftX": -0.45, "EyeRightX": -0.45,
    },
    "thinking": {
        "MouthSmile": 0.15, "Brows": 0.40, "BrowLeftY": 0.55, "BrowRightY": 0.30,
        "EyeOpenLeft": 0.75, "EyeOpenRight": 0.75, "FaceAngleZ": -9.0,
        "EyeLeftX": 0.55, "EyeRightX": 0.55, "EyeLeftY": 0.35, "EyeRightY": 0.35,
    },
}

# คำไทยที่บอกอารมณ์ ใช้เดาเวลาโมเดลไม่ได้ใส่มาร์กเกอร์มา
EMOTION_HINTS: dict[str, tuple[str, ...]] = {
    "happy": ("ดีใจ", "ยินดี", "สนุก", "ขอบคุณ", "เยี่ยม", "สุดยอด", "น่ารัก", "ชอบ", "สวัสดี"),
    "excited": ("ตื่นเต้น", "ว้าว", "โอ้โห", "เจ๋ง", "สุดยอดไปเลย", "อยากลอง"),
    "sad": ("เสียใจ", "เศร้า", "ขอโทษ", "เหนื่อย", "ผิดหวัง", "แย่จัง", "สงสาร"),
    "surprised": ("ตกใจ", "จริงเหรอ", "ไม่น่าเชื่อ", "หา?", "เอ๊ะ"),
    "angry": ("โกรธ", "หงุดหงิด", "ไม่พอใจ", "รำคาญ"),
    "shy": ("เขิน", "อาย", "กระดาก"),
    "thinking": ("คิดว่า", "น่าจะ", "ขอคิด", "อืม", "ไม่แน่ใจ", "สงสัย", "เดี๋ยวนะ"),
}


def resolve_emotion(name: str) -> dict[str, float]:
    """คืนค่าพารามิเตอร์เต็มชุดของอารมณ์ (ทับบน NEUTRAL)."""
    preset = EMOTIONS.get((name or "").strip().lower(), {})
    return {**NEUTRAL, **preset}


def guess_emotion(text: str) -> str:
    """เดาอารมณ์จากคำในข้อความ (ใช้เมื่อโมเดลไม่ได้บอกมา)."""
    low = (text or "").lower()
    best, score = "neutral", 0
    for emo, words in EMOTION_HINTS.items():
        hits = sum(1 for w in words if w in low)
        if hits > score:
            best, score = emo, hits
    return best


# ---------------------------------------------------------------------------
#  สระจากเสียง (formant → VoiceA/I/U/E/O)
# ---------------------------------------------------------------------------
# ค่า F1/F2 โดยประมาณของเสียงผู้หญิง (Hz)
# คีย์ตั้งชื่อตรงกับพารามิเตอร์ของ VTS เลย จะได้ส่งต่อได้ทันที
_VOWEL_FORMANTS: dict[str, tuple[float, float]] = {
    "VoiceA": (850.0, 1300.0),
    "VoiceI": (320.0, 2700.0),
    "VoiceU": (370.0, 850.0),
    "VoiceE": (520.0, 2300.0),
    "VoiceO": (520.0, 900.0),
}


def _estimate_f1_f2(frame: np.ndarray, sr: int) -> tuple[float, float]:
    """หา F1/F2 คร่าว ๆ จาก peak ของสเปกตรัมในช่วงความถี่ที่กำหนด."""
    if frame.size < 32:
        return 0.0, 0.0
    windowed = frame * np.hanning(len(frame))
    spec = np.abs(np.fft.rfft(windowed, n=max(1024, len(frame))))
    freqs = np.fft.rfftfreq(max(1024, len(frame)), 1.0 / sr)

    def peak_in(lo: float, hi: float) -> float:
        band = (freqs >= lo) & (freqs <= hi)
        if not band.any():
            return 0.0
        idx = np.argmax(spec[band])
        return float(freqs[band][idx])

    return peak_in(200, 1100), peak_in(900, 3200)


def vowel_weights_from_audio(
    audio: np.ndarray, sr: int, fps: int, energy: np.ndarray
) -> dict[str, np.ndarray]:
    """คืน dict ของ VoiceA/I/U/E/O เป็นอาร์เรย์ค่า 0..1 ต่อเฟรม.

    energy: envelope ความดัง 0..1 (ใช้หรี่น้ำหนักสระตอนเงียบ)
    """
    n = len(energy)
    keys = list(_VOWEL_FORMANTS)
    out = {k: np.zeros(n, dtype=np.float32) for k in keys}
    if audio.size == 0 or n == 0:
        return out

    win = max(256, int(sr * 0.04))          # หน้าต่าง ~40 ms
    hop = max(1, len(audio) // n)

    for i in range(n):
        if energy[i] < 0.08:                 # เงียบ ไม่ต้องขึ้นรูปปาก
            continue
        seg = audio[i * hop : i * hop + win]
        f1, f2 = _estimate_f1_f2(seg, sr)
        if f1 <= 0 or f2 <= 0:
            continue
        # ระยะห่างจากสระแต่ละตัวใน log-frequency แล้วให้น้ำหนักแบบผกผัน
        dists = []
        for k in keys:
            t1, t2 = _VOWEL_FORMANTS[k]
            d = np.hypot(np.log(f1 / t1), np.log(f2 / t2))
            dists.append(d)
        inv = 1.0 / (np.asarray(dists) + 0.15)
        w = inv / inv.sum()
        # เน้นตัวที่ชนะให้เด่นขึ้น (ไม่งั้นปากจะเบลอ ๆ ทุกสระผสมกัน)
        w = w**3
        w = w / w.sum()
        for k, val in zip(keys, w):
            out[k][i] = float(val) * float(energy[i])
    return out
