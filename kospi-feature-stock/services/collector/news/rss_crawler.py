"""
RSS 기반 뉴스 보조 수집기.
Naver 크롤링 실패/차단 시 fallback으로 사용.
지원: 한국경제, 연합인포맥스, 뉴스핌 RSS
"""
import asyncio
import logging
import re
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

_RSS_FEEDS = [
    {
        "url":    "https://www.hankyung.com/feed/finance",
        "source": "hankyung_rss",
    },
    {
        "url":    "https://biz.chosun.com/arc/outboundfeeds/rss/category/stock/?outputType=xml",
        "source": "chosunbiz_rss",
    },
    {
        "url":    "https://www.newsis.com/RSS/economy.xml",
        "source": "newsis_rss",
    },
]

_CONTENT_LIMIT = 800
_CACHE_TTL     = 1800   # 30분


def _parse_rss_date(text: str) -> str:
    if not text:
        return datetime.now(KST).isoformat()
    try:
        dt = parsedate_to_datetime(text.strip())
        return dt.astimezone(KST).isoformat()
    except Exception:
        return datetime.now(KST).isoformat()


class RssNewsCrawler:
    """한국경제·연합인포맥스·뉴스핌 RSS를 종목명 기준으로 필터링 후 반환."""

    def __init__(self):
        self._session:   aiohttp.ClientSession | None = None
        self._cache:     list[dict] = []
        self._cache_at:  float = 0
        self._sem = asyncio.Semaphore(2)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; StockNewsBot/1.0)",
                    "Accept":     "application/rss+xml, application/xml, text/xml",
                },
            )
        return self._session

    async def _fetch_rss(self, url: str, source: str) -> list[dict]:
        try:
            async with self._sem:
                session = await self._get_session()
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.debug(f"[RSS] {source} HTTP {resp.status}")
                        return []
                    text = await resp.text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.debug(f"[RSS] {source} fetch error: {e}")
            return []

        items = []
        try:
            soup = BeautifulSoup(text, "lxml-xml")
            for item in soup.find_all("item"):
                title_el = item.find("title")
                link_el  = item.find("link")
                date_el  = item.find("pubDate")
                desc_el  = item.find("description")

                title = title_el.get_text(strip=True) if title_el else ""
                link  = link_el.get_text(strip=True)  if link_el  else ""
                if not title or not link:
                    continue

                content = ""
                if desc_el:
                    raw     = desc_el.get_text(separator=" ", strip=True)
                    content = re.sub(r"\s+", " ", raw)[:_CONTENT_LIMIT]

                items.append({
                    "title":        title,
                    "url":          link,
                    "published_at": _parse_rss_date(date_el.get_text() if date_el else ""),
                    "source":       source,
                    "content":      content,
                })
        except Exception as e:
            logger.debug(f"[RSS] {source} parse error: {e}")

        return items

    async def _refresh_cache(self):
        now = time.monotonic()
        if now - self._cache_at < _CACHE_TTL and self._cache:
            return
        results = await asyncio.gather(
            *[self._fetch_rss(f["url"], f["source"]) for f in _RSS_FEEDS],
            return_exceptions=True,
        )
        fresh = [article for r in results if isinstance(r, list) for article in r]
        self._cache    = fresh
        self._cache_at = now
        logger.debug(f"[RSS] cache refreshed: {len(fresh)}건 ({len(_RSS_FEEDS)} 소스)")

    async def crawl_stock_news(self, code: str, name: str, max_items: int = 5) -> list[dict]:
        """종목명이 포함된 RSS 기사를 반환 (최대 max_items건)."""
        await self._refresh_cache()
        # 2글자 이상 토큰으로 분리 (조사/단음절 제거)
        tokens = [t for t in re.split(r"[\s\(\)\[\]]+", name) if len(t) >= 2]
        matched = []
        for article in self._cache:
            haystack = article["title"] + " " + article.get("content", "")
            if any(tok in haystack for tok in tokens):
                matched.append({**article, "code": code, "themes": []})
            if len(matched) >= max_items:
                break
        return matched

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
