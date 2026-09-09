"""ตัวหลัก: อ่าน input → router → (LLM | Claude Code) → TTS → ขับปากอวตาร."""
from __future__ import annotations

import asyncio

from rich.console import Console
from rich.panel import Panel

from src.avatar.player import Player
from src.avatar.vts_client import VTSClient
from src.coding.claude_code import run_claude
from src.config import AppConfig, load_config
from src.llm.client import LLMClient, LLMUnavailable
from src.llm.persona import build_system_prompt
from src.llm.router import Router
from src.tts.manager import ENGINES, TTSManager

HELP = """[bold]คำสั่ง[/]
  /say <ข้อความ>     ให้พูดข้อความนี้ทันที (ทดสอบเสียง + ปาก)
  /voice [ชื่อ]        สลับเสียง (piper/edge/mms/f5) — ไม่ใส่ชื่อ = ดูรายการ
  /project <path>    ตั้งโฟลเดอร์โปรเจกต์ให้ Claude Code
  /claude <งาน>      ส่งงานให้ Claude Code ตรง ๆ
  /reload            ล้างประวัติ + โหลดบุคลิกใหม่จาก config
  /help              แสดงคำสั่ง
  /quit              ออก
พิมพ์ข้อความปกติ = คุยกับ VTuber (คำตอบจะถูกอ่านออกเสียง)"""


class VTuberApp:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.console = Console()
        self.llm = LLMClient(cfg.llm)
        self.router = Router(cfg.coding.trigger_phrases)
        self.tts = TTSManager(cfg)
        self.system_prompt = build_system_prompt(cfg.persona)
        self.history: list[dict[str, str]] = []
        self.project = cfg.resolve(cfg.coding.default_project)
        self.vts: VTSClient | None = None
        self.player: Player | None = None

    # ------------------------------------------------------------------ #
    async def setup(self) -> None:
        c = self.console
        c.print(f"[dim]กำลังโหลดโมเดลเสียง ({self.tts.engine_name})...[/]")
        await asyncio.to_thread(self.tts.warmup)
        c.print("[green]✓[/] โมเดลเสียงพร้อม")

        if self.cfg.avatar.enabled:
            self.vts = VTSClient(
                url=self.cfg.avatar.vts_url,
                plugin_name=self.cfg.avatar.plugin_name,
                plugin_developer=self.cfg.avatar.plugin_developer,
                token_file=self.cfg.resolve(self.cfg.avatar.token_file),
                mouth_param=self.cfg.avatar.mouth_param,
            )
            if await self.vts.connect():
                c.print("[green]✓[/] ต่อ VTube Studio แล้ว")
            else:
                c.print(f"[yellow]![/] ต่อ VTube Studio ไม่ได้ ({self.vts.last_error}) — จะทำงานแบบไม่มีอวตาร")

        self.player = Player(
            self.vts,
            fps=self.cfg.avatar.fps,
            gain=self.cfg.avatar.gain,
            attack=self.cfg.avatar.smoothing_attack,
            release=self.cfg.avatar.smoothing_release,
            noise_gate=self.cfg.avatar.noise_gate,
        )

        if self.llm.ping():
            c.print(f"[green]✓[/] LM Studio ({self.cfg.llm.model})")
        else:
            c.print("[yellow]![/] ต่อ LM Studio ไม่ได้ — เปิด Start Server ใน LM Studio ก่อนเริ่มคุย")

    # ------------------------------------------------------------------ #
    async def _speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text or self.player is None:
            return
        try:
            wavs = await asyncio.to_thread(self.tts.synthesize, text)
            await self.player.speak(wavs)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            self.console.print(f"[red]TTS ผิดพลาด:[/] {e}")

    async def _delegate(self, task: str) -> None:
        c = self.console
        c.print(Panel(task, title="[yellow]→ ส่งงานให้ Claude Code[/]", border_style="yellow"))
        await self._speak("โอเคค่ะ เดี๋ยวให้ Claude ช่วยจัดการให้")
        res = await asyncio.to_thread(
            run_claude, task, str(self.project),
            self.cfg.coding.timeout_sec, self.cfg.coding.permission_mode,
        )
        border = "green" if res.ok else "red"
        body = (res.raw or res.error or "").strip()
        c.print(Panel(body[:2000] or "(ไม่มีรายละเอียด)", title=f"[{border}]{res.summary}[/]", border_style=border))
        if res.cost_usd:
            c.print(f"[dim]ค่าใช้จ่าย ~${res.cost_usd:.4f}[/]")
        await self._speak(res.summary)

    # ------------------------------------------------------------------ #
    async def handle_line(self, line: str) -> bool:
        line = line.strip()
        if not line:
            return True
        if line.startswith("/"):
            return await self._command(line)

        pre = self.router.pre_route(line)
        if pre.mode == "delegate_code":
            await self._delegate(pre.task)
            return True

        self.history.append({"role": "user", "content": line})
        self._trim_history()
        messages = [{"role": "system", "content": self.system_prompt}, *self.history]
        try:
            reply = await asyncio.to_thread(self.llm.chat, messages)
        except LLMUnavailable as e:
            self.console.print(f"[red]{e}[/]")
            await self._speak("ตอนนี้ยังต่อสมองไม่ได้ค่ะ เปิด LM Studio ก่อนนะคะ")
            self.history.pop()
            return True

        spoken, task = self.router.extract_delegation(reply)
        self.history.append({"role": "assistant", "content": reply})
        if spoken:
            self.console.print(f"[bold magenta]{self.cfg.persona.name}›[/] {spoken}")
            await self._speak(spoken)
        if task:
            await self._delegate(task)
        return True

    def _trim_history(self) -> None:
        cap = max(2, self.cfg.llm.history_turns * 2)
        if len(self.history) > cap:
            self.history = self.history[-cap:]

    async def _command(self, line: str) -> bool:
        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        c = self.console

        if cmd in ("/quit", "/exit", "/q"):
            return False
        if cmd == "/help":
            c.print(Panel(HELP, border_style="cyan"))
        elif cmd == "/say":
            await self._speak(arg or "สวัสดีค่ะ นี่คือการทดสอบระบบเสียงและการขยับปาก")
        elif cmd == "/voice":
            if arg not in ENGINES:
                c.print("[bold]เสียงที่เลือกได้:[/]")
                for k, desc in ENGINES.items():
                    mark = "[green]●[/]" if k == self.tts.engine_name else " "
                    c.print(f"  {mark} [bold]/voice {k}[/]  — {desc}")
            else:
                try:
                    self.tts.set_engine(arg)
                    await asyncio.to_thread(self.tts.warmup)
                    c.print(f"[green]✓[/] เปลี่ยนเสียงเป็น [bold]{arg}[/] แล้วค่ะ")
                except Exception as e:  # noqa: BLE001
                    c.print(f"[red]เปลี่ยนเป็น {arg} ไม่ได้:[/] {e}")
        elif cmd == "/project":
            if arg:
                self.project = self.cfg.resolve(arg)
                self.project.mkdir(parents=True, exist_ok=True)
            c.print(f"โฟลเดอร์โปรเจกต์: [bold]{self.project}[/]")
        elif cmd == "/claude":
            if arg:
                await self._delegate(arg)
            else:
                c.print("ใช้: [bold]/claude <อธิบายงานที่จะให้ทำ>[/]")
        elif cmd == "/reload":
            self.cfg = load_config()
            self.system_prompt = build_system_prompt(self.cfg.persona)
            self.history.clear()
            c.print("[green]✓[/] โหลด config ใหม่ + ล้างประวัติแล้วค่ะ")
        else:
            c.print(f"ไม่รู้จักคำสั่ง [bold]{cmd}[/] — พิมพ์ /help")
        return True

    # ------------------------------------------------------------------ #
    async def run(self) -> None:
        await self.setup()
        self.console.print(
            Panel.fit(
                f"[bold magenta]{self.cfg.persona.name}[/] พร้อมคุยแล้วค่ะ   "
                f"[dim]/help = คำสั่ง   /quit = ออก[/]",
                border_style="cyan",
            )
        )
        while True:
            try:
                line = await asyncio.to_thread(self.console.input, "[bold cyan]คุณ›[/] ")
            except (EOFError, KeyboardInterrupt):
                break
            try:
                if not await self.handle_line(line):
                    break
            except KeyboardInterrupt:
                self.console.print("[dim](ยกเลิกงานนี้)[/]")
            except Exception as e:  # noqa: BLE001 - อย่าให้ทั้งแอปตายเพราะ turn เดียว
                self.console.print(f"[red]เกิดข้อผิดพลาด:[/] {e}")
        await self.cleanup()

    async def cleanup(self) -> None:
        if self.vts is not None:
            await self.vts.close()
        self.console.print("บ๊ายบายค่ะ 👋")


async def main() -> None:
    await VTuberApp(load_config()).run()
