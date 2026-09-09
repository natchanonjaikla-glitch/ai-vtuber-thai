"""ค้นข้อมูลจากเว็บด้วย DuckDuckGo (ฟรี ไม่ต้องใช้ API key).

ใช้ให้ VTuber ตอบเรื่องที่โมเดลในเครื่องไม่รู้ — ข่าว ราคา เหตุการณ์ล่าสุด ฯลฯ
โดยดึงผลค้นหามาเป็น context แล้วให้ LLM สรุปเป็นภาษาไทยสั้น ๆ
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.config import WebConfig

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass
class SearchResult:
    title: str
    body: str
    url: str

    def as_context(self, max_body: int = 400) -> str:
        body = self.body[:max_body]
        return f"- {self.title}\n  {body}\n  ที่มา: {self.url}"


class SearchError(RuntimeError):
    pass


class WebSearch:
    def __init__(self, cfg: WebConfig):
        self.cfg = cfg

    # ------------------------------------------------------------------ #
    def search(self, query: str, max_results: int | None = None) -> list[SearchResult]:
        from ddgs import DDGS

        n = max_results or self.cfg.max_results
        try:
            with DDGS(timeout=self.cfg.timeout_sec) as ddgs:
                rows = list(ddgs.text(query, region=self.cfg.region, max_results=n))
        except Exception as e:  # noqa: BLE001
            raise SearchError(f"ค้นหาไม่สำเร็จ: {type(e).__name__}: {e}") from e

        out: list[SearchResult] = []
        for r in rows:
            body = _WS_RE.sub(" ", (r.get("body") or "")).strip()
            out.append(
                SearchResult(
                    title=_WS_RE.sub(" ", (r.get("title") or "")).strip(),
                    body=body,
                    url=(r.get("href") or r.get("url") or "").strip(),
                )
            )
        return out

    # ------------------------------------------------------------------ #
    def fetch_page(self, url: str) -> str:
        """ดึงเนื้อความจากหน้าเว็บ (ตัดแท็ก script/style ออก)."""
        import httpx
        from lxml import html as lxml_html

        try:
            r = httpx.get(
                url,
                timeout=self.cfg.timeout_sec,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; AI-VTuber/1.0)"},
            )
            r.raise_for_status()
            doc = lxml_html.fromstring(r.text)
            for bad in doc.xpath("//script|//style|//nav|//footer|//header|//noscript"):
                bad.getparent().remove(bad)
            text = doc.text_content()
        except Exception:  # noqa: BLE001 - หน้าเว็บพังได้สารพัด ข้ามไปใช้ snippet แทน
            return ""
        return _WS_RE.sub(" ", text).strip()[: self.cfg.fetch_chars]

    # ------------------------------------------------------------------ #
    def context_for_llm(self, query: str) -> tuple[str, list[SearchResult]]:
        """คืน (ข้อความ context พร้อมใส่ prompt, ผลค้นหาดิบ)."""
        results = self.search(query)
        if not results:
            return "", []

        blocks = [r.as_context() for r in results]

        # ดึงเนื้อหาเต็มจาก n หน้าแรก ถ้าเปิดไว้
        for r in results[: max(0, self.cfg.fetch_pages)]:
            page = self.fetch_page(r.url)
            if page:
                blocks.append(f"- เนื้อหาจาก {r.url}:\n  {page}")

        context = "\n".join(blocks)
        return context, results


SEARCH_PROMPT = """\
นี่คือผลการค้นหาจากอินเทอร์เน็ตสำหรับคำถาม: "{query}"

{context}

ตอบคำถามข้างต้นเป็นภาษาไทยสั้น ๆ 1–3 ประโยค ด้วยน้ำเสียงปกติของคุณ
อ้างอิงเฉพาะข้อมูลที่เห็นข้างบน ถ้าข้อมูลไม่พอให้บอกตรง ๆ ว่าหาไม่เจอ
ห้ามอ่าน URL ออกเสียง และไม่ต้องบอกว่า "จากผลการค้นหา"
"""
