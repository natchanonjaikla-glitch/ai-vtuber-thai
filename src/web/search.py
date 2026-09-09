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


_NUMERIC_RE = re.compile(r"\d[\d,]*\.?\d*")


def _usefulness(page: str, query: str) -> float:
    """ให้คะแนนว่าหน้านี้น่าจะมี "ข้อมูลจริง" แค่ไหน (ไม่ใช่แค่เมนู/สารบัญ).

    หน้าที่เป็นเมนูล้วนจะมีคำเยอะแต่แทบไม่มีตัวเลข ส่วนหน้าที่มีราคา/สถิติจริง
    จะมีตัวเลขหนาแน่นและมีคำจากคำค้นปรากฏอยู่
    """
    if not page or len(page) < 120:
        return 0.0
    numbers = _NUMERIC_RE.findall(page)
    # ตัวเลขที่ "มีความหมาย" (ไม่ใช่เลขตัวเดียวจากเมนู)
    meaty = [x for x in numbers if len(x.replace(",", "").replace(".", "")) >= 3]
    density = len(meaty) / (len(page) / 1000.0)      # ตัวเลขต่อ 1000 ตัวอักษร
    terms = [t for t in query.split() if len(t) > 2]
    hits = sum(page.count(t) for t in terms)
    score = density * 2.0 + min(hits, 10) * 0.5
    return score if meaty else 0.0


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
        """ดึงเนื้อความ **ทั้งหน้า** (ตัด script/style/เมนู ออก) ไม่ตัดความยาว.

        การคัดให้พอดี context ไปทำทีหลังใน condense_for_query() ซึ่งเลือกจาก
        "ส่วนที่เกี่ยวกับคำถาม" แทนการตัดหัวท้ายมั่ว ๆ
        """
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
            for bad in doc.xpath(
                "//script|//style|//nav|//footer|//header|//noscript|//aside|//form"
            ):
                parent = bad.getparent()
                if parent is not None:
                    parent.remove(bad)
            text = doc.text_content()
        except Exception:  # noqa: BLE001 - หน้าเว็บพังได้สารพัด ข้ามไปใช้ snippet แทน
            return ""
        return _WS_RE.sub(" ", text).strip()

    # ------------------------------------------------------------------ #
    @staticmethod
    def condense_for_query(page: str, query: str, budget: int) -> str:
        """อ่านทั้งหน้าแล้วคัดเฉพาะช่วงที่เกี่ยวกับคำถามให้ยาวไม่เกิน budget.

        ตัดหน้าเป็นช่วง ๆ ให้คะแนนแต่ละช่วงจาก (คำจากคำค้น + ความหนาแน่นของตัวเลข)
        แล้วหยิบช่วงที่คะแนนดีที่สุดมาเรียงตามลำดับเดิม — ดีกว่าตัดเอา N ตัวอักษรแรก
        เพราะข้อมูลจริงมักอยู่กลางหน้า หลังเมนูยาว ๆ
        """
        page = page.strip()
        if len(page) <= budget:
            return page

        seg_len = 500
        segs = [page[i : i + seg_len] for i in range(0, len(page), seg_len)]
        terms = [t for t in query.split() if len(t) > 2]

        def score(seg: str) -> float:
            nums = [x for x in _NUMERIC_RE.findall(seg)
                    if len(x.replace(",", "").replace(".", "")) >= 3]
            return len(nums) * 1.0 + sum(seg.count(t) for t in terms) * 2.0

        ranked = sorted(range(len(segs)), key=lambda i: -score(segs[i]))
        keep: set[int] = set()
        total = 0
        for i in ranked:
            if total + len(segs[i]) > budget:
                continue
            keep.add(i)
            total += len(segs[i])
            if total >= budget * 0.95:
                break
        if not keep:
            return page[:budget]
        # เรียงกลับตามลำดับในหน้า ใส่ … ตรงที่ข้ามไป
        out, prev = [], -1
        for i in sorted(keep):
            if prev >= 0 and i != prev + 1:
                out.append(" … ")
            out.append(segs[i])
            prev = i
        return "".join(out)

    # ------------------------------------------------------------------ #
    def context_for_llm(self, query: str) -> tuple[str, list[SearchResult]]:
        """คืน (ข้อความ context พร้อมใส่ prompt, ผลค้นหาดิบ).

        snippet ของ DuckDuckGo มักเป็นแค่คำโปรยเว็บ ไม่มีตัวเลข/ข้อเท็จจริงจริง ๆ
        (เช่นค้น "ราคาทองวันนี้" ได้แค่ "เช็คราคาทองล่าสุด...") ถ้าไม่ดึงหน้าเว็บมาด้วย
        โมเดลจะไม่มีข้อมูลให้อ่านแล้วไปเดาจากความจำตอนเทรนแทน → ตอบผิดแบบมั่นใจ
        """
        results = self.search(query)
        if not results:
            return "", []

        blocks: list[str] = []

        n = max(0, self.cfg.fetch_pages)
        if n:
            # ดึงหลายหน้าพร้อมกัน ไม่งั้นรอนานเกินไป
            from concurrent.futures import ThreadPoolExecutor

            targets = results[:n]
            with ThreadPoolExecutor(max_workers=min(4, len(targets))) as pool:
                pages = list(pool.map(lambda r: self.fetch_page(r.url), targets))

            # บางหน้าที่ดึงมาเป็นเมนู/สารบัญล้วน ๆ ไม่มีข้อมูลจริง ถ้าปล่อยไว้ต้น ๆ
            # โมเดลจะไปลอกหัวข้อมาตอบ → ให้คะแนนแล้วเรียงหน้าที่มีเนื้อขึ้นก่อน
            scored = [
                (_usefulness(page, query), r.url, page)
                for r, page in zip(targets, pages)
                if page
            ]
            scored.sort(key=lambda x: -x[0])
            useful = [x for x in scored if x[0] > 0]
            # แบ่งโควตาตัวอักษรให้หน้าที่คะแนนดีมากกว่า
            for rank, (_score, url, page) in enumerate(useful):
                budget = self.cfg.fetch_chars if rank == 0 else self.cfg.fetch_chars // 2
                blocks.append(
                    f"[เนื้อหาจากหน้าเว็บ {url}]\n"
                    + self.condense_for_query(page, query, budget)
                )

        # snippet ไว้ท้ายสุด เป็นแค่ข้อมูลสำรอง
        blocks.append("[สรุปย่อจากผลค้นหา]\n" + "\n".join(r.as_context() for r in results))
        return "\n\n".join(blocks), results


SEARCH_PROMPT = """\
วันเวลาปัจจุบัน: {now}

ข้อมูลที่ค้นมาจากอินเทอร์เน็ตสำหรับคำถาม "{query}":

{context}

--- จบข้อมูลที่ค้นมา ---

กติกาการตอบ (สำคัญมาก):
1. ใช้ได้เฉพาะตัวเลขและข้อเท็จจริงที่ปรากฏในข้อมูลข้างบนเท่านั้น
2. ห้ามใช้ความรู้เดิมที่คุณจำมาโดยเด็ดขาด โดยเฉพาะตัวเลข ราคา วันที่ สถิติ
   ความจำของคุณเป็นข้อมูลเก่าและผิดแน่นอน
3. ถ้าข้อมูลข้างบนไม่มีคำตอบ ให้บอกตรง ๆ ว่า "หาข้อมูลที่ชัดเจนไม่เจอค่ะ"
   ห้ามเดาตัวเลขขึ้นมาเองเป็นอันขาด
4. ถ้าตัวเลขขึ้นกับยี่ห้อ/ร้าน/ประเภท (เช่น ราคาน้ำมันของแต่ละปั๊ม
   ราคาทองแบบแท่งกับรูปพรรณ ราคารับซื้อกับขายออก) ต้องบอกด้วยว่าเลขนั้นของอะไร
   อย่าตอบเป็นตัวเลขลอย ๆ
5. ถ้าแหล่งข้อมูลให้ตัวเลขไม่ตรงกัน ให้บอกว่าแต่ละแหล่งว่าอย่างไร
   หรือเลือกใช้แหล่งแรกแล้วระบุว่ามาจากไหน
6. ตอบเป็นภาษาไทย 1–3 ประโยค ด้วยน้ำเสียงปกติของคุณ
7. ห้ามอ่าน URL ออกเสียง และไม่ต้องขึ้นต้นว่า "จากผลการค้นหา"
"""
