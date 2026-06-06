"""
Naver Finance 종목별 뉴스 수집.
per-stock URL(/item/news_news.naver)을 사용해 HTML 구조 변경에 덜 취약함.
"""
import asyncio
import logging
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

THEME_KEYWORDS = {
    "2차전지":   ["배터리", "전기차", "리튬", "양극재", "음극재", "배터리셀", "LFP", "NCM"],
    "반도체":    ["메모리", "HBM", "파운드리", "웨이퍼", "칩", "DRAM", "낸드", "시스템반도체"],
    "AI":        ["인공지능", "LLM", "GPU", "데이터센터", "AI반도체", "생성형AI", "챗GPT"],
    "바이오":    ["임상", "FDA", "신약", "바이오시밀러", "CAR-T", "mRNA", "항체"],
    "방산":      ["방위산업", "K2전차", "미사일", "무기", "폴란드", "수출계약"],
    "친환경":    ["태양광", "풍력", "수소", "ESS", "재생에너지", "탄소중립"],
    "로봇":      ["로봇", "자동화", "드론", "협동로봇", "물류로봇"],
    "원전":      ["원자력", "SMR", "핵융합", "체코원전", "원전수출"],
}

# KST 날짜 파싱 포맷 후보
_DATE_FMTS    = ["%Y.%m.%d %H:%M", "%Y.%m.%d"]
_BASE_URL     = "https://finance.naver.com"
_CONTENT_LIMIT = 500  # 본문 최대 저장 글자 수
_CONTENT_SEM  = asyncio.Semaphore(2)  # 본문 크롤링 동시 요청 제한


def _parse_date(text: str) -> str:
    text = text.strip()
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            pass
    return datetime.now().isoformat()


def _detect_themes(text: str) -> list[str]:
    return [t for t, kws in THEME_KEYWORDS.items() if any(kw in text for kw in kws)]


class NaverNewsCrawler:

    _STOCK_NEWS_URL = _BASE_URL + "/item/news_news.naver"

    def __init__(self):
        self._client = httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": _BASE_URL,
                "Accept-Language": "ko-KR,ko;q=0.9",
            },
        )
        self._sem = asyncio.Semaphore(3)   # 동시 요청 제한

    async def crawl_stock_news(self, code: str, name: str, max_items: int = 10) -> list[dict]:
        """종목 코드 기준 뉴스 목록 반환. 실패 시 빈 리스트."""
        async with self._sem:
            for attempt in range(3):
                try:
                    return await self._fetch_stock_page(code, name, max_items)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code in (403, 429):
                        await asyncio.sleep(2 ** attempt * 5)
                    else:
                        logger.debug(f"News HTTP error {code}: {e}")
                        break
                except (httpx.RequestError, Exception) as e:
                    logger.debug(f"News error {code} (attempt {attempt+1}): {e}")
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt * 2)
        return []

    async def _fetch_stock_page(self, code: str, name: str, max_items: int) -> list[dict]:
        resp = await self._client.get(
            self._STOCK_NEWS_URL,
            params={"code": code, "page": 1},
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # 종목 뉴스 테이블: <table class="type5"> 또는 tbody > tr
        items = []
        rows = soup.select("table.type5 tr, .realtimeNewsList li")

        for row in rows[:max_items * 2]:  # 여유 있게 파싱
            # table.type5 tr 방식
            title_el = row.select_one("td.title a, dt a, a.tit")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 5:
                continue
            href  = title_el.get("href", "")
            if not href.startswith("http"):
                href = _BASE_URL + href

            date_el = row.select_one("td.date, span.date, .date")
            pub_at  = _parse_date(date_el.get_text()) if date_el else datetime.now().isoformat()

            items.append({
                "code":         code,
                "title":        title,
                "url":          href,
                "published_at": pub_at,
                "source":       "naver_finance",
                "themes":       _detect_themes(title),
                "content":      "",
            })
            if len(items) >= max_items:
                break

        # fallback: 일반 검색 결과 파싱 (테이블 파싱 실패 시)
        if not items:
            items = await self._fallback_search(code, name, max_items)

        return await self._enrich_contents(items)

    async def _fallback_search(self, code: str, name: str, max_items: int) -> list[dict]:
        """뉴스 검색 API fallback (종목명으로 검색)"""
        try:
            resp = await self._client.get(
                _BASE_URL + "/news/news_search.naver",
                params={"q": name, "sm": "tab_tit", "sort": "1"},
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            items = []
            for a in soup.select("dl dt a, .newsTitle a, .tit a")[:max_items]:
                title = a.get_text(strip=True)
                href  = a.get("href", "")
                if not title or not href:
                    continue
                if not href.startswith("http"):
                    href = _BASE_URL + href
                items.append({
                    "code":         code,
                    "title":        title,
                    "url":          href,
                    "published_at": datetime.now().isoformat(),
                    "source":       "naver_finance",
                    "themes":       _detect_themes(title),
                    "content":      "",
                })
            return items
        except Exception as e:
            logger.debug(f"Fallback search error {code}: {e}")
            return []

    async def _fetch_article_content(self, url: str) -> str:
        """뉴스 기사 URL에서 본문 텍스트 추출 (최대 _CONTENT_LIMIT자)."""
        if not url or not url.startswith("http"):
            return ""
        try:
            async with _CONTENT_SEM:
                resp = await self._client.get(url, timeout=10)
                resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            # 네이버 뉴스 본문 셀렉터 우선순위
            for selector in ["#dic_area", "#newsct_article", ".article_body", "article", "#articeBody"]:
                el = soup.select_one(selector)
                if el:
                    text = re.sub(r"\s+", " ", el.get_text(separator=" ", strip=True))
                    return text[:_CONTENT_LIMIT]
            # fallback: <p> 태그 텍스트 수집
            paras = [
                p.get_text(strip=True)
                for p in soup.find_all("p")
                if len(p.get_text(strip=True)) > 20
            ]
            return re.sub(r"\s+", " ", " ".join(paras))[:_CONTENT_LIMIT]
        except Exception as e:
            logger.debug(f"Content fetch error {url}: {e}")
            return ""

    async def _enrich_contents(self, items: list[dict]) -> list[dict]:
        """상위 5개 기사 본문을 병렬 크롤링하여 content 필드 채움."""
        targets = items[:5]
        rest    = items[5:]
        contents = await asyncio.gather(
            *[self._fetch_article_content(it["url"]) for it in targets],
            return_exceptions=True,
        )
        for item, content in zip(targets, contents):
            item["content"] = content if isinstance(content, str) else ""
        return targets + rest

    async def close(self):
        await self._client.aclose()
