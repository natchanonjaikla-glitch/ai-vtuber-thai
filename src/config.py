"""โหลด config.yaml + .env → dataclass ที่ใช้ทั่วทั้งแอป.

ลำดับความสำคัญ:  ค่า default ในโค้ด  <  config.yaml  <  ตัวแปรใน .env / environment
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


# --------------------------------------------------------------------------- #
#  dataclasses                                                               #
# --------------------------------------------------------------------------- #
@dataclass
class LLMConfig:
    base_url: str = "http://localhost:1234/v1"
    api_key: str = "lm-studio"
    model: str = "scb10x/llama3.1-typhoon2-8b-instruct"
    temperature: float = 0.7
    max_tokens: int = 512
    timeout_sec: int = 120
    history_turns: int = 8


@dataclass
class PersonaConfig:
    name: str = "ไอริส"
    language: str = "th"
    style: str = "เป็น VTuber สาวสดใส พูดไทยเป็นธรรมชาติ ตอบสั้น 1–3 ประโยค"
    delegate_marker: str = "[[DELEGATE_TO_CLAUDE: <อธิบายงาน> ]]"
    search_marker: str = "[[SEARCH: <คำค้น> ]]"


@dataclass
class MMSConfig:
    model_id: str = "facebook/mms-tts-tha"


@dataclass
class F5Config:
    hf_repo: str = "VIZINTZOR/F5-TTS-THAI"
    model_name: str = "v1"          # f5-tts-th: "v1" = โมเดล 1,000,000 steps
    ref_wav: str = "assets/voice_ref/ref.wav"
    ref_text: str = "assets/voice_ref/ref.txt"
    nfe_step: int = 16             # ยิ่งน้อยยิ่งเร็ว (แต่บน CPU ก็ยังช้ามาก ~6 นาที/ประโยค)
    speed: float = 1.0


@dataclass
class PiperConfig:
    voice: str = "th_TH-tsync2-medium"
    speed: float = 1.0          # >1 = เร็วขึ้น
    noise_scale: float = 0.667  # ความแปรผันของน้ำเสียง
    noise_w: float = 0.8        # ความแปรผันของจังหวะ


@dataclass
class EdgeConfig:
    voice: str = "th-TH-PremwadeeNeural"   # หญิง | ชาย = th-TH-NiwatNeural
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: str = "+0%"


@dataclass
class TTSConfig:
    engine: str = "piper"
    cpu_threads: int = 8
    cache_dir: str = ".cache/tts"
    max_chars_per_chunk: int = 180
    mms: MMSConfig = field(default_factory=MMSConfig)
    f5: F5Config = field(default_factory=F5Config)
    piper: PiperConfig = field(default_factory=PiperConfig)
    edge: EdgeConfig = field(default_factory=EdgeConfig)


@dataclass
class AvatarConfig:
    enabled: bool = True
    vts_url: str = "ws://localhost:8001"
    plugin_name: str = "AI VTuber Brain"
    plugin_developer: str = "Natchanon"
    token_file: str = ".vts_token"
    mouth_param: str = "MouthOpen"
    fps: int = 30
    gain: float = 1.6
    noise_gate: float = 0.14
    smoothing_attack: float = 0.6
    smoothing_release: float = 0.25
    # --- สีหน้า/ท่าทาง ---
    expressions: bool = True        # เปิดระบบอารมณ์ + ขยับตอนอยู่เฉย + กะพริบตา
    vowel_mouth: bool = True        # ขึ้นรูปปากตามสระ (VoiceA/I/U/E/O) ไม่ใช่แค่อ้า
    emotion_blend: float = 0.15     # ความไวในการเปลี่ยนอารมณ์ (0..1)
    idle_amount: float = 1.0        # ความแรงของการขยับตอนอยู่เฉย (0 = นิ่งสนิท)
    blink_min_sec: float = 2.5
    blink_max_sec: float = 6.0
    default_emotion: str = "happy"


@dataclass
class CodingConfig:
    default_project: str = "./workspace"
    timeout_sec: int = 900
    # acceptEdits = แก้ไฟล์อัตโนมัติ (ปลอดภัยระดับหนึ่ง) | bypassPermissions = ทำได้ทุกอย่าง
    permission_mode: str = "acceptEdits"
    trigger_phrases: list[str] = field(
        default_factory=lambda: ["เรียก claude", "ให้ claude", "งานยาก", "/claude"]
    )


@dataclass
class WebConfig:
    enabled: bool = True
    region: str = "th-th"
    max_results: int = 5
    fetch_pages: int = 0        # ดึงเนื้อหาเต็มจากกี่หน้าแรก (0 = ใช้แค่ snippet, เร็วกว่า)
    fetch_chars: int = 1500
    timeout_sec: int = 20
    trigger_phrases: list[str] = field(
        default_factory=lambda: ["ค้นหา", "เสิร์ช", "หาข้อมูล", "กูเกิล", "/search"]
    )


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    persona: PersonaConfig = field(default_factory=PersonaConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    avatar: AvatarConfig = field(default_factory=AvatarConfig)
    coding: CodingConfig = field(default_factory=CodingConfig)
    web: WebConfig = field(default_factory=WebConfig)
    project_root: Path = PROJECT_ROOT

    # -- helpers -------------------------------------------------------------
    def resolve(self, path_str: str) -> Path:
        """แปลง path สัมพัทธ์ให้อิงจาก project root และ expand ~ / env vars."""
        p = Path(os.path.expandvars(os.path.expanduser(path_str)))
        return p if p.is_absolute() else (self.project_root / p)


# --------------------------------------------------------------------------- #
#  loader                                                                    #
# --------------------------------------------------------------------------- #
def _merge_into_dataclass(dc_instance: Any, data: dict | None) -> Any:
    """เขียนค่าจาก dict ทับ dataclass แบบ recursive (เฉพาะ key ที่รู้จัก)."""
    if not data:
        return dc_instance
    for f in fields(dc_instance):
        if f.name not in data:
            continue
        current = getattr(dc_instance, f.name)
        incoming = data[f.name]
        if is_dataclass(current) and isinstance(incoming, dict):
            _merge_into_dataclass(current, incoming)
        else:
            setattr(dc_instance, f.name, incoming)
    return dc_instance


_ENV_MAP = {
    # ENV_VAR : (section, attr, caster)
    "LLM_BASE_URL": ("llm", "base_url", str),
    "LLM_API_KEY": ("llm", "api_key", str),
    "LLM_MODEL": ("llm", "model", str),
    "CODING_DEFAULT_PROJECT": ("coding", "default_project", str),
}


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    load_dotenv(PROJECT_ROOT / ".env")

    cfg = AppConfig()
    path = Path(path)
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        _merge_into_dataclass(cfg, raw)

    # overlay ค่าจาก environment
    for env_var, (section, attr, cast) in _ENV_MAP.items():
        val = os.environ.get(env_var)
        if val:
            setattr(getattr(cfg, section), attr, cast(val))

    # HF_HOME: ให้ transformers / huggingface_hub ใช้ที่เก็บ cache ตามที่ตั้ง
    if os.environ.get("HF_HOME"):
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", os.environ["HF_HOME"])

    return cfg


if __name__ == "__main__":  # python -m src.config  → ดูค่าที่โหลดจริง
    import pprint

    pprint.pp(load_config())
