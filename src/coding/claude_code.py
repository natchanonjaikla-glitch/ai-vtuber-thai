"""ส่งงานเขียนโค้ดที่ยาก ๆ ให้ Claude Code CLI (`claude -p`) ทำในโฟลเดอร์โปรเจกต์.

ต้องติดตั้งก่อน:  npm i -g @anthropic-ai/claude-code   แล้ว login ครั้งแรก
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ClaudeResult:
    ok: bool
    summary: str                       # ข้อความสำหรับให้ VTuber พูด
    files_changed: list[str] = field(default_factory=list)
    raw: str = ""
    cost_usd: float | None = None
    error: str | None = None


def claude_available() -> str | None:
    """คืน path ของ claude ถ้าเจอใน PATH, ไม่งั้น None."""
    return shutil.which("claude")


def _git_changed(cwd: Path) -> list[str]:
    if not (cwd / ".git").exists():
        return []
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), "status", "--porcelain"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
        )
        return [ln[3:].strip() for ln in out.stdout.splitlines() if ln.strip()]
    except Exception:
        return []


def run_claude(
    task: str,
    cwd: str | Path,
    timeout_sec: int = 900,
    permission_mode: str = "acceptEdits",
) -> ClaudeResult:
    exe = claude_available()
    if not exe:
        return ClaudeResult(
            ok=False,
            summary="ยังเรียก Claude Code ไม่ได้ค่ะ ยังไม่ได้ติดตั้ง",
            error="ไม่พบคำสั่ง 'claude' ใน PATH — ติดตั้งด้วย: npm i -g @anthropic-ai/claude-code",
        )

    cwd = Path(cwd).resolve()
    cwd.mkdir(parents=True, exist_ok=True)

    cmd = [
        exe, "-p", task,
        "--output-format", "json",
        "--permission-mode", permission_mode,
        "--add-dir", str(cwd),
    ]

    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        return ClaudeResult(
            ok=False,
            summary=f"Claude ทำงานเกินเวลา {timeout_sec} วินาที เลยหยุดไว้ก่อนนะคะ",
            error="timeout",
        )
    except Exception as e:  # noqa: BLE001
        return ClaudeResult(ok=False, summary="เรียก Claude Code ไม่สำเร็จค่ะ", error=str(e))

    raw = proc.stdout.strip()
    result_text, cost = raw, None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            result_text = str(data.get("result") or data.get("text") or raw)
            cost = data.get("total_cost_usd")
            if data.get("is_error"):
                return ClaudeResult(
                    ok=False, summary="Claude เจอปัญหาระหว่างทำงานค่ะ",
                    raw=result_text, error=proc.stderr.strip() or result_text, cost_usd=cost,
                )
    except json.JSONDecodeError:
        pass

    if proc.returncode != 0:
        return ClaudeResult(
            ok=False, summary="Claude Code จบด้วย error ค่ะ",
            raw=raw, error=proc.stderr.strip() or f"exit code {proc.returncode}",
        )

    files = _git_changed(cwd)
    if files:
        head = ", ".join(files[:4]) + (f" และอีก {len(files) - 4} ไฟล์" if len(files) > 4 else "")
        summary = f"Claude ทำงานเสร็จแล้วค่ะ แก้ไป {len(files)} ไฟล์: {head}"
    else:
        summary = "Claude ทำงานเสร็จแล้วค่ะ"

    return ClaudeResult(ok=True, summary=summary, files_changed=files, raw=result_text, cost_usd=cost)
