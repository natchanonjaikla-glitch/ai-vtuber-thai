"""วัดผลโมเดลที่โหลดอยู่ใน LM Studio: ความเร็ว + คุณภาพภาษาไทย + สัดส่วน reasoning token

    .venv\\Scripts\\python.exe scripts\\bench_model.py
    .venv\\Scripts\\python.exe scripts\\bench_model.py --model google/gemma-3-12b
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import OpenAI  # noqa: E402

from src.config import load_config  # noqa: E402
from src.llm.persona import build_system_prompt  # noqa: E402

PROMPTS = [
    "แนะนำตัวหน่อย",
    "วันนี้เหนื่อยมากเลย",
    "อธิบายสั้น ๆ ว่า API คืออะไร",
    "ช่วยเขียนฟังก์ชัน Python บวกเลขสองตัวให้หน่อย",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="ชื่อโมเดล (ไม่ใส่ = ใช้ตัวที่ LM Studio โหลดอยู่)")
    args = ap.parse_args()

    cfg = load_config()
    client = OpenAI(base_url=cfg.llm.base_url, api_key=cfg.llm.api_key, timeout=300)

    model = args.model
    if not model:
        ids = [m.id for m in client.models.list().data if "embed" not in m.id]
        if not ids:
            print("ไม่มีโมเดลโหลดอยู่ใน LM Studio")
            return
        model = ids[0]

    system = build_system_prompt(cfg.persona)
    print(f"โมเดล: {model}\n" + "=" * 70)

    tot_t = tot_out = tot_reason = 0.0
    for p in PROMPTS:
        t = time.time()
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": p}],
            temperature=cfg.llm.temperature,
            max_tokens=cfg.llm.max_tokens,
        )
        dt = time.time() - t
        content = (r.choices[0].message.content or "").strip()
        u = r.usage
        reason = 0
        details = getattr(u, "completion_tokens_details", None)
        if details is not None:
            reason = getattr(details, "reasoning_tokens", 0) or 0

        tot_t += dt
        tot_out += u.completion_tokens
        tot_reason += reason

        print(f"\n▸ ถาม: {p}")
        print(f"  ตอบ: {content or '(ว่าง!)'}")
        print(
            f"  [{dt:.1f}s | {u.completion_tokens} tok"
            f"{f' (reasoning {reason})' if reason else ''}"
            f" | {u.completion_tokens / dt:.1f} tok/s]"
        )

    print("\n" + "=" * 70)
    print(f"รวม {tot_t:.1f}s | {tot_out:.0f} tok | เฉลี่ย {tot_out / tot_t:.1f} tok/s")
    if tot_reason:
        print(f"เสียไปกับ reasoning: {tot_reason:.0f}/{tot_out:.0f} tok ({tot_reason / tot_out * 100:.0f}%)")


if __name__ == "__main__":
    main()
