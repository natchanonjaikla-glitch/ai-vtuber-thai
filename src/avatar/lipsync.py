"""แปลงคลื่นเสียง → ลำดับค่า "อ้าปาก" 0..1 ที่อัตราเฟรมคงที่.

วิธี: RMS ต่อหน้าต่างสั้น ๆ → normalize → smoothing แบบ attack เร็ว / release ช้า.
เป็นฟังก์ชันล้วน (ไม่มี I/O) เพื่อให้เทสต์ง่ายและเรียกจาก player ได้ตรง ๆ.
"""
from __future__ import annotations

import numpy as np


def envelope_from_audio(
    audio: np.ndarray,
    sr: int,
    fps: int = 30,
    gain: float = 1.6,
    attack: float = 0.6,
    release: float = 0.25,
    noise_gate: float = 0.14,
) -> np.ndarray:
    """คืน np.ndarray float32 ค่า 0..1 ยาว = ceil(len(audio)/sr*fps).

    noise_gate: ระดับต่ำกว่านี้ (0..1) ถือว่า "เงียบ" → ปากปิดสนิท ทำให้ดูมีจังหวะหุบปาก.
    """
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    audio = np.asarray(audio, dtype=np.float32)
    n_frames = max(1, int(np.ceil(len(audio) / sr * fps)))
    if len(audio) == 0:
        return np.zeros(n_frames, dtype=np.float32)

    hop = max(1, len(audio) // n_frames)
    win = max(hop, int(sr / fps))

    rms = np.empty(n_frames, dtype=np.float32)
    for i in range(n_frames):
        start = i * hop
        seg = audio[start : start + win]
        rms[i] = np.sqrt(np.mean(seg**2)) if seg.size else 0.0

    # normalize ด้วย percentile 95 (กัน outlier) แล้วคูณ gain
    ref = np.percentile(rms, 95) if np.any(rms > 0) else 1.0
    level = np.clip(rms / (ref + 1e-6) * gain, 0.0, 1.0)

    # noise gate: ดันช่วงเงียบให้เป็น 0 แล้ว rescale ช่วงที่เหลือกลับเป็น 0..1
    g = min(max(noise_gate, 0.0), 0.9)
    level = np.clip((level - g) / (1.0 - g), 0.0, 1.0)

    # smoothing: ขึ้นไว ลงช้า → ปากดูมีชีวิต
    out = np.empty_like(level)
    prev = 0.0
    for i, x in enumerate(level):
        coef = attack if x > prev else release
        prev = prev + coef * (x - prev)
        out[i] = prev
    return out.astype(np.float32)
