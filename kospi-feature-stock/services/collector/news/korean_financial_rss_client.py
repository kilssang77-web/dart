"""
한국 주요 금융 언론사 RSS 클라이언트.
Naver API / Google RSS 실패 시 fallback으로 사용.
인증 불필요 — 공개 RSS 피드 사용.

지원 소스:
  - 한국경제    (hankyung.com)
  - 매일경제    (mk.co.kr)
  - 연합뉴스    (yna.co.kr)
  - 서울경제    (sedaily.com)
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote
import xml.etree.ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# RSS 소스 정의: (이름, URL 템플릿 or 고정 URL, query_param 지원 여부)
_RSS_SOURCES = [
    {
        "name": "hankyung",
        "search_url": "https://search.hankyung.com/search/news?query={query}&media=한국경제",
        "feed_urls": [
            "https://rss.hankyung.com/rss/economy_stock.xml",
            "https://rss.hankyung.com/economy/stock.xml",
        ],
        "use_feed": True,
    },
    {
        "name": "mk",
        "feed_urls": [
            "https://rss.mk.co.kr/rss/30000001.xml",   # 증권
            "https://rss.mk.co.kr/rss/40300001.xml",   # 시황
        ],
        "use_feed": True,
    },
    {
        "name": "yna",
        "feed_urls": [
            "https://www.yna.co.kr/rss/economy.xml",
            "https://www.yna.co.kr/rss/stock.xml",
        ],
        "use_feed": True,
    },
    {
        "name": "sedaily",
        "feed_urls": [
            "https://www.sedaily.com/RSS/DL.xml",   # 증권
        ],
        "use_feed": True,
    },
]

_TIMEOUT = 8.0
_MAX_CONCURRENT = 3


def _parse_date(pub_date: str) -> str:
    """RFC 2822 또는 ISO 8601 날짜 → ISO 8601 문자열."""
    if not pub_date:
        return datetime.now(KST).isoformat()
    try:
        return parsedate_to_datetime(pub_date).isoformat()
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(pub_date)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.isoformat()
    except Exception:
        return datetime.now(KST).isoformat()


def _parse_rss_items(xml_text: str, source_name: str) -> list[dict]:
    """XML RSS 텍스트 → dict 리스트."""
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        # BOM 또는 불완전 XML 처리
        try:
            clean = xml_text.lstrip("﻿").encode("utf-8", errors="replace").decode("utf-8")
            root = ET.fromstring(clean)
        except Exception:
            return []

    ns = {}
    for item_tag in root.iter("item"):
        title_el   = item_tag.find("title")
        link_el    = item_tag.find("link")
        desc_el    = item_tag.find("description")
        date_el    = item_tag.find("pubDate")

        title = (title_el.text or "").strip() if title_el is not None else ""
        link  = (link_el.text  or "").strip() if link_el  is not None else ""
        # link가 태그 내 텍스트가 아닌 경우 (CDATA)
        if not link and link_el is not None:
            link = next(link_el.itertext(), "").strip()

        desc = ""
        if desc_el is not None:
            raw_desc = desc_el.text or ""
            # CDATA strip & HTML tag remove
            import re
            desc = re.sub(r"<[^>]+>", "", raw_desc).strip()

        pub_date = (date_el.text or "").strip() if date_el is not None else ""

        if not title or not link:
            continue

        items.append({
            "title":        title,
            "url":          link,
            "description":  desc,
            "published_at": _parse_date(pub_date),
            "source":       source_name,
        })

    return items


def _filter_by_keyword(items: list[dict], keyword: str) -> list[dict]:
    """제목 또는 description에 keyword가 포함된 항목만 필터."""
    kw = keyword.lower()
    return [
        it for it in items
        if kw in it["title"].lower() or kw in it["description"].lower()
    ]


class KoreanFinancialRSSClient:
    """
    한국 주요 금융 언론사 RSS 동시 수집 클라이언트.

    crawl_for_stock(keyword, max_items) 로 사용.
    """

    async def get_news(self, keyword: str, max_items: int = 10) -> list[dict]:
        """
        여러 한국 금융 RSS에서 keyword가 포함된 기사를 수집.
        각 소스를 동시에 조회하고 결과를 병합 후 시간 순 정렬.

        Args:
            keyword:   종목명 또는 검색어
            max_items: 반환 최대 건수

        Returns:
            list of dict (title, url, description, published_at, source)
        """
        sem     = asyncio.Semaphore(_MAX_CONCURRENT)
        tasks   = []

        for src in _RSS_SOURCES:
            for feed_url in src["feed_urls"]:
                tasks.append(self._fetch_and_filter(sem, feed_url, src["name"], keyword))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        merged: list[dict] = []
        seen_titles: set[str] = set()
        for r in results:
            if isinstance(r, list):
                for item in r:
                    t = item["title"][:40]
                    if t not in seen_titles:
                        seen_titles.add(t)
                        merged.append(item)

        # 최신 순 정렬
        def _sort_key(it: dict) -> str:
            return it.get("published_at", "")

        merged.sort(key=_sort_key, reverse=True)
        return merged[:max_items]

    async def _fetch_and_filter(
        self,
        sem: asyncio.Semaphore,
        url: str,
        source_name: str,
        keyword: str,
    ) -> list[dict]:
        async with sem:
            try:
                async with httpx.AsyncClient(
                    timeout=_TIMEOUT,
                    follow_redirects=True,
                    headers=_HEADERS,
                ) as client:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        return []
                    xml_text = resp.text
            except Exception as e:
                logger.debug(f"[KoreanRSS] {source_name} fetch error: {e}")
                return []

        items = _parse_rss_items(xml_text, source_name)
        if keyword:
            items = _filter_by_keyword(items, keyword)
        return items
