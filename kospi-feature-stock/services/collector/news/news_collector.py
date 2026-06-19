"""
다중 소스 뉴스 오케스트레이터.

우선순위:
  1. NaverNewsAPI    — 공식 Naver 검색 API (25,000건/일, NAVER_CLIENT_ID 필요)
  2. GoogleNewsRSS   — Google News RSS (무인증)
  3. NaverNewsCrawler — 기존 Naver Finance 크롤러 (HTML 파싱 기반, 최후 fallback)

각 소스에서 성공(항목 1개 이상)하면 즉시 반환.
반환 형식:
    {
        "code":         str,         # 종목 코드
        "title":        str,
        "url":          str,
        "published_at": str,         # ISO 8601
        "source":       str,         # "naver_api" | "google_rss" | "naver_finance"
        "content":      str,         # 본문 (크롤러 소스일 때만 채워짐, 나머지는 description 사용)
        "themes":       list[str],   # THEME_KEYWORDS 기반 테마 태그
    }

main.py 의 NaverNewsCrawler.crawl_stock_news() 와 동일한 인터페이스를 제공하므로
import 한 줄만 바꾸면 drop-in 교체 가능:
    from news.news_collector import MultiSourceNewsCollector as NaverNewsCrawler
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from news.naver_api_client import NaverNewsAPI
from news.google_rss_client import GoogleNewsRSS
from news.korean_financial_rss_client import KoreanFinancialRSSClient
from news.naver_crawler import NaverNewsCrawler, THEME_KEYWORDS

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def _detect_themes(text: str) -> list[str]:
    """THEME_KEYWORDS 딕셔너리 기반 테마 매칭 (naver_crawler 재활용)."""
    return [t for t, kws in THEME_KEYWORDS.items() if any(kw in text for kw in kws)]


def _normalize(
    raw: dict,
    code: str,
) -> dict:
    """각 소스의 raw 딕셔너리를 공통 형식으로 변환."""
    title   = raw.get("title", "")
    content = raw.get("content", "") or raw.get("description", "")
    themes  = raw.get("themes") or _detect_themes(title + " " + content)

    return {
        "code":         code,
        "title":        title,
        "url":          raw.get("url", ""),
        "published_at": raw.get("published_at", datetime.now(KST).isoformat()),
        "source":       raw.get("source", "unknown"),
        "content":      content,
        "themes":       themes,
    }


class MultiSourceNewsCollector:
    """NaverNewsAPI → GoogleNewsRSS → NaverNewsCrawler 순으로 뉴스 수집.

    main.py 의 self.news = NaverNewsCrawler() 를
    self.news = MultiSourceNewsCollector() 로 교체하면 동작.
    crawl_stock_news(code, name, max_items) 인터페이스를 그대로 유지.
    """

    def __init__(self) -> None:
        self._naver_api      = NaverNewsAPI()
        self._google_rss     = GoogleNewsRSS()
        self._korean_rss     = KoreanFinancialRSSClient()   # 한경/MK/연합/서울경제
        self._naver_crawler  = NaverNewsCrawler()           # 최후 fallback

    async def crawl_stock_news(
        self,
        code: str,
        name: str,
        max_items: int = 10,
    ) -> list[dict]:
        """종목 코드·종목명으로 뉴스 수집.

        Args:
            code:      6자리 종목 코드 (예: "005930")
            name:      종목명 (예: "삼성전자")
            max_items: 반환할 최대 기사 수

        Returns:
            공통 형식 dict 리스트. 소스가 모두 실패하면 빈 리스트.
        """
        # ── 1순위: Naver 공식 API ─────────────────────────────
        if self._naver_api.available:
            try:
                raw_items = await self._naver_api.search(name, display=max_items)
                if raw_items:
                    logger.debug(f"[MultiSource] {code} — naver_api 성공 ({len(raw_items)}건)")
                    return [_normalize(r, code) for r in raw_items]
            except Exception as e:
                logger.warning(f"[MultiSource] {code} naver_api 오류: {e}")
        else:
            logger.debug("[MultiSource] naver_api 자격증명 없음 — 다음 소스 시도")

        # ── 2순위: Google News RSS ────────────────────────────
        try:
            raw_items = await self._google_rss.get_news(name, max_items=max_items)
            if raw_items:
                logger.debug(f"[MultiSource] {code} — google_rss 성공 ({len(raw_items)}건)")
                return [_normalize(r, code) for r in raw_items]
        except Exception as e:
            logger.warning(f"[MultiSource] {code} google_rss 오류: {e}")

        # ── 3순위: 한국 금융 언론사 RSS (한경/MK/연합/서울경제) ─
        try:
            raw_items = await self._korean_rss.get_news(name, max_items=max_items)
            if raw_items:
                logger.debug(f"[MultiSource] {code} — korean_rss 성공 ({len(raw_items)}건)")
                return [_normalize(r, code) for r in raw_items]
        except Exception as e:
            logger.warning(f"[MultiSource] {code} korean_rss 오류: {e}")

        # ── 4순위: 기존 Naver Finance 크롤러 (최후 fallback) ──
        try:
            raw_items = await self._naver_crawler.crawl_stock_news(
                code, name, max_items=max_items
            )
            if raw_items:
                logger.debug(
                    f"[MultiSource] {code} — naver_crawler fallback 성공 ({len(raw_items)}건)"
                )
                # crawl_stock_news 는 이미 공통 형식에 가까운 dict를 반환하므로
                # code 필드만 보장하고 themes 재계산
                result = []
                for r in raw_items:
                    r.setdefault("code", code)
                    if not r.get("themes"):
                        r["themes"] = _detect_themes(r.get("title", "") + r.get("content", ""))
                    result.append(r)
                return result
        except Exception as e:
            logger.warning(f"[MultiSource] {code} naver_crawler fallback 오류: {e}")

        logger.warning(f"[MultiSource] {code} ({name}) — 모든 소스 실패, 빈 리스트 반환")
        return []

    async def close(self) -> None:
        """내부 httpx 클라이언트 정리 (NaverNewsCrawler의 persistent client 종료)."""
        await self._naver_crawler.close()
