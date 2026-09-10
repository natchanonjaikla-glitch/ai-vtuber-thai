"""อากาศ — ใช้ Open-Meteo (ฟรี ไม่ต้องมี API key ไม่จำกัดโควตา)

เหตุผลที่แยกจาก web search ทั่วไป: เว็บพยากรณ์อากาศไทยส่วนใหญ่ (weather.com,
accuweather, กรมอุตุ) render ตัวเลขด้วย JavaScript ทำให้ fetch_page() อ่านไม่ได้
เลย — เจอมาแล้วตอนถาม "อากาศกรุงเทพวันนี้" แล้วโมเดลตอบไม่ได้เรื่อง
Open-Meteo เป็น JSON API ตรง ๆ เร็วกว่า (< 2 วิ รวม geocode) และไม่มีทางเดาผิด
เพราะไม่ผ่าน LLM เลย — ประกอบเป็นประโยคเองจากตัวเลขที่ API ให้มา
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.config import WebConfig

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather code -> (คำอธิบายไทย, อารมณ์ที่เหมาะกับอวตาร)
_WMO: dict[int, tuple[str, str]] = {
    0: ("ท้องฟ้าแจ่มใส", "happy"),
    1: ("แจ่มใสเป็นส่วนใหญ่", "happy"),
    2: ("มีเมฆบางส่วน", "neutral"),
    3: ("มีเมฆมาก", "neutral"),
    45: ("มีหมอก", "neutral"),
    48: ("หมอกน้ำแข็ง", "neutral"),
    51: ("ฝนปรอยเบา ๆ", "neutral"),
    53: ("ฝนปรอยปานกลาง", "neutral"),
    55: ("ฝนปรอยหนัก", "sad"),
    56: ("ฝนปรอยเยือกแข็งเบา ๆ", "neutral"),
    57: ("ฝนปรอยเยือกแข็งหนัก", "sad"),
    61: ("ฝนตกเล็กน้อย", "neutral"),
    63: ("ฝนตกปานกลาง", "sad"),
    65: ("ฝนตกหนัก", "sad"),
    66: ("ฝนเยือกแข็งเล็กน้อย", "sad"),
    67: ("ฝนเยือกแข็งหนัก", "sad"),
    71: ("หิมะตกเล็กน้อย", "neutral"),
    73: ("หิมะตกปานกลาง", "neutral"),
    75: ("หิมะตกหนัก", "neutral"),
    77: ("เกล็ดหิมะ", "neutral"),
    80: ("ฝนซู่เล็กน้อย", "neutral"),
    81: ("ฝนซู่ปานกลาง", "sad"),
    82: ("ฝนซู่รุนแรง", "sad"),
    85: ("หิมะซู่เล็กน้อย", "neutral"),
    86: ("หิมะซู่หนัก", "neutral"),
    95: ("พายุฝนฟ้าคะนอง", "surprised"),
    96: ("พายุฝนฟ้าคะนองมีลูกเห็บเล็กน้อย", "surprised"),
    99: ("พายุฝนฟ้าคะนองมีลูกเห็บหนัก", "surprised"),
}


def describe_wmo(code: int) -> tuple[str, str]:
    return _WMO.get(code, ("ไม่ทราบสภาพอากาศ", "neutral"))


_FILLER_WORDS = (
    "วันนี้", "พรุ่งนี้", "ตอนนี้", "เดี๋ยวนี้", "เป็นยังไง", "เป็นอย่างไร",
    "บ้าง", "หน่อย", "ไหม", "มั้ย", "จะ", "คะ", "ค่ะ", "ครับ", "นะ", "หรอ", "เหรอ",
)


def _clean_place(text: str) -> str:
    """ตัดคำถามทั่วไปที่ไม่ใช่ชื่อสถานที่ออก เช่น "วันนี้เป็นยังไง" -> "" (ใช้ location default).

    trigger stripping ใน Router ตัดแค่คำ trigger ("อากาศ") ออก ส่วนที่เหลืออาจยัง
    มีคำถามต่อท้าย ("วันนี้เป็นยังไง") ซึ่งไม่ใช่สถานที่ ถ้าส่งเข้า geocode ตรง ๆ จะพัง
    """
    cleaned = text.strip()
    for w in _FILLER_WORDS:
        cleaned = cleaned.replace(w, "")
    # ตัดคำนำหน้า/ต่อท้ายทั้งคำ (ไม่ใช่ str.strip() ซึ่งตัดทีละตัวอักษร — จะกิน
    # วรรณยุกต์ที่บังเอิญซ้ำกับตัวอักษรท้ายชื่อสถานที่ เช่น "เชียงใหม่" ลงท้าย
    # ด้วยไม้เอกซึ่งเป็นอักษรเดียวกับใน "ที่")
    cleaned = re.sub(r"^(ที่|จังหวัด|ของ|\s)+", "", cleaned)
    cleaned = re.sub(r"(\s)+$", "", cleaned)
    return cleaned.strip()


@dataclass
class WeatherReport:
    place: str
    temp_c: float
    feels_like_c: float
    humidity: int
    condition: str
    emotion: str
    temp_max_c: float | None = None
    temp_min_c: float | None = None
    rain_chance: int | None = None

    def as_speech(self) -> str:
        parts = [
            f"ตอนนี้ที่{self.place} {self.condition} อุณหภูมิ {self.temp_c:.0f} องศา",
        ]
        if abs(self.feels_like_c - self.temp_c) >= 2:
            parts.append(f"รู้สึกเหมือน {self.feels_like_c:.0f} องศา")
        if self.temp_max_c is not None and self.temp_min_c is not None:
            parts.append(f"วันนี้สูงสุด {self.temp_max_c:.0f} ต่ำสุด {self.temp_min_c:.0f} องศา")
        if self.rain_chance is not None and self.rain_chance >= 30:
            parts.append(f"โอกาสฝนตก {self.rain_chance}%")
        return " ".join(parts) + "ค่ะ"


class WeatherError(RuntimeError):
    pass


class WeatherClient:
    def __init__(self, cfg: WebConfig):
        self.cfg = cfg

    @staticmethod
    def _geocode_query(place: str, language: str | None) -> list[dict]:
        import httpx

        params: dict = {"name": place, "count": 1}
        if language:
            params["language"] = language
        r = httpx.get(_GEOCODE_URL, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("results") or []

    def geocode(self, place: str) -> tuple[float, float, str]:
        try:
            results = self._geocode_query(place, "th")
            if not results:
                # บางเมืองไม่มีชื่อไทยในฐานข้อมูล (เช่น "นนทบุรี") ลองแบบไม่ระบุภาษา
                results = self._geocode_query(place, None)
        except Exception as e:  # noqa: BLE001
            raise WeatherError(f"หาตำแหน่ง {place!r} ไม่สำเร็จ: {e}") from e

        if not results:
            raise WeatherError(f"ไม่รู้จักสถานที่ {place!r}")
        r0 = results[0]
        name = r0.get("name", place)
        admin1 = r0.get("admin1")
        # ตัดซ้ำเวลาชื่อจังหวัด/เขตซ้ำกับชื่อเมือง เช่น "กรุงเทพมหานคร" กับ "กรุงเทพฯ"
        # (ไม่ใช่ substring ตรง ๆ กัน เพราะ "มหานคร" vs "ฯ" แต่ขึ้นต้นเหมือนกัน)
        import difflib

        similar = bool(admin1) and (
            admin1 == name
            or admin1 in name
            or name in admin1
            or difflib.SequenceMatcher(None, name[:4], admin1[:4]).ratio() > 0.7
        )
        display = name if similar else f"{name} {admin1}" if admin1 else name
        return r0["latitude"], r0["longitude"], display

    def report(self, place: str = "") -> WeatherReport:
        place = _clean_place(place) or "กรุงเทพมหานคร"
        lat, lon, display_name = self.geocode(place)

        import httpx

        try:
            r = httpx.get(
                _FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,"
                    "apparent_temperature,weather_code",
                    "daily": "temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max",
                    "timezone": "Asia/Bangkok",
                    "forecast_days": 1,
                },
                timeout=self.cfg.search_timeout_sec,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:  # noqa: BLE001
            raise WeatherError(f"ดึงข้อมูลอากาศไม่สำเร็จ: {e}") from e

        cur = data.get("current", {})
        daily = data.get("daily", {})
        condition, emotion = describe_wmo(int(cur.get("weather_code", -1)))

        def _first(key: str) -> float | None:
            vals = daily.get(key) or []
            return float(vals[0]) if vals else None

        return WeatherReport(
            place=display_name,
            temp_c=float(cur.get("temperature_2m", 0.0)),
            feels_like_c=float(cur.get("apparent_temperature", 0.0)),
            humidity=int(cur.get("relative_humidity_2m", 0)),
            condition=condition,
            emotion=emotion,
            temp_max_c=_first("temperature_2m_max"),
            temp_min_c=_first("temperature_2m_min"),
            rain_chance=(
                int(daily["precipitation_probability_max"][0])
                if daily.get("precipitation_probability_max")
                else None
            ),
        )
