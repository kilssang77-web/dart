"""
Naver Finance 종목별 뉴스 수집.
per-stock URL(/item/news_news.naver)을 사용해 HTML 구조 변경에 덜 취약함.
"""
import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

THEME_KEYWORDS = {
    # 기술·산업
    "2차전지":    ["배터리", "전기차", "리튬", "양극재", "음극재", "배터리셀", "LFP", "NCM", "전고체"],
    "반도체":     ["메모리", "HBM", "파운드리", "웨이퍼", "칩", "DRAM", "낸드", "시스템반도체", "패키징"],
    "AI":         ["인공지능", "LLM", "GPU", "데이터센터", "AI반도체", "생성형AI", "챗GPT", "온디바이스AI"],
    "바이오":     ["임상", "FDA", "신약", "바이오시밀러", "CAR-T", "mRNA", "항체", "플랫폼기술", "희귀질환"],
    "방산":       ["방위산업", "K2전차", "미사일", "무기", "폴란드", "수출계약", "K방산", "함정", "전투기"],
    "친환경":     ["태양광", "풍력", "수소", "ESS", "재생에너지", "탄소중립", "탄소배출권"],
    "로봇":       ["로봇", "자동화", "드론", "협동로봇", "물류로봇", "휴머노이드", "웨어러블로봇"],
    "원전":       ["원자력", "SMR", "핵융합", "체코원전", "원전수출", "원전해체", "우라늄"],
    # 전통 산업
    "자동차":     ["완성차", "전기차부품", "자율주행", "OTA", "모빌리티", "수소차", "하이브리드"],
    "조선":       ["조선", "LNG선", "컨테이너선", "수주", "VLCC", "선박", "해양플랜트"],
    "철강":       ["철강", "포스코", "냉연", "열연", "고로", "전기로", "슬래브"],
    "화학":       ["석유화학", "에틸렌", "납사", "PET", "폴리머", "정밀화학", "소재"],
    "건설":       ["수주잔고", "분양", "PF", "재개발", "재건축", "건설경기", "착공"],
    "금융":       ["금리인하", "NIM", "대출성장", "자산건전성", "배당", "RWA", "CET1"],
    "보험":       ["손해보험", "생명보험", "IFRS17", "CSM", "손해율", "보험료"],
    # 소비·서비스
    "게임":       ["신작", "게임출시", "MMORPG", "모바일게임", "BM", "PC게임", "라이브서비스"],
    "엔터테인먼트":["K팝", "아이돌", "공연", "앨범", "아티스트", "팬덤", "음반"],
    "의류·패션":  ["SPA", "패션", "어패럴", "브랜드", "수출", "리테일", "아웃도어"],
    "음식료":     ["식품", "음료", "HMR", "프리미엄", "수출", "원가", "가격인상"],
    "유통·물류":  ["이커머스", "물류센터", "3PL", "쿠팡", "SSG", "배송", "풀필먼트"],
    # 테마·이슈
    "정책수혜":   ["국책사업", "정부발주", "추경", "K-뉴딜", "보조금", "인허가"],
    "미국증시":   ["나스닥", "S&P", "다우존스", "연준", "FOMC", "기준금리", "파월"],
    "중국경기":   ["중국경제", "리오프닝", "부동산", "내수부양", "인민은행", "PMI"],
    "환율":       ["달러강세", "원달러", "환헤지", "외환보유고", "엔화", "위안화"],
    "공매도":     ["공매도", "숏커버링", "대차잔고", "숏셀링"],
    "지주사":     ["지주", "자회사", "배당수익", "NAV할인", "오너리스크"],
    "소부장":     ["소재", "부품", "장비", "국산화", "공급망", "탈중국"],
    "우주항공":   ["우주", "위성", "발사체", "나로호", "항공기", "MRO", "에어로스페이스"],
    "헬스케어":   ["디지털헬스", "의료기기", "의료AI", "원격진료", "CRO", "진단"],
    "플랫폼":     ["플랫폼", "구독", "MAU", "광고수익", "수수료", "슈퍼앱"],
}

# KST 날짜 파싱 포맷 후보
_DATE_FMTS    = ["%Y.%m.%d %H:%M", "%Y.%m.%d"]
_BASE_URL     = "https://finance.naver.com"
_CONTENT_LIMIT = 800  # 본문 최대 저장 글자 수
_CONTENT_SEM  = asyncio.Semaphore(3)  # 본문 크롤링 동시 요청 제한

# 도메인별 본문 CSS 셀렉터 (우선순위 순)
_DOMAIN_SELECTORS: dict[str, list[str]] = {
    "n.news.naver.com":   ["#dic_area", "#newsct_article"],
    "news.naver.com":     ["#dic_area", "#articleBodyContents"],
    "www.yna.co.kr":      [".article-txt", "#articleWrap", ".content"],
    "www.hankyung.com":   ["#articleBody", ".article-body", "#article-content"],
    "www.edaily.co.kr":   ["#articleText", ".news_body", ".article_txt"],
    "www.mk.co.kr":       ["#article_body", ".art_body", "#art_body"],
    "biz.chosun.com":     [".article-body", "#news_body_id"],
    "www.chosun.com":     [".article-body", "#news_body_id"],
    "www.sedaily.com":    ["#v-article", ".article_view"],
    "www.etnews.com":     ["#articleBody", ".article_txt", "#article_body"],
    "www.dt.co.kr":       ["#articleBody", ".article-body"],
    "www.newsis.com":     [".view_text", "#textBody"],
    "news.mt.co.kr":      [".article_view", "#textBody"],
    "www.businesspost.co.kr": [".article-view-content-div", ".article_content"],
    "www.inews24.com":    ["#articleBody", ".view-article"],
    "finance.yahoo.com":  [".caas-body", "article"],
}


KST = timezone(timedelta(hours=9))

def _parse_date(text: str) -> str:
    text = text.strip()
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=KST).isoformat()
        except ValueError:
            pass
    return datetime.now(KST).isoformat()


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

    @staticmethod
    def _resolve_news_url(url: str) -> str:
        """finance.naver.com/item/news_read.naver → n.news.naver.com/mnews/article/{oid}/{aid}"""
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        if "finance.naver.com" in parsed.netloc and "news_read" in parsed.path:
            qs  = parse_qs(parsed.query)
            aid = qs.get("article_id", [""])[0]
            oid = qs.get("office_id",  [""])[0]
            if aid and oid:
                return f"https://n.news.naver.com/mnews/article/{oid}/{aid}"
        return url

    async def _fetch_article_content(self, url: str) -> str:
        """뉴스 기사 URL에서 본문 텍스트 추출 (최대 _CONTENT_LIMIT자)."""
        if not url or not url.startswith("http"):
            return ""
        try:
            fetch_url = self._resolve_news_url(url)
            async with _CONTENT_SEM:
                resp = await self._client.get(fetch_url, timeout=10)
                resp.raise_for_status()
            final_url = str(resp.url)
            soup = BeautifulSoup(resp.text, "lxml")

            from urllib.parse import urlparse
            domain = urlparse(final_url).netloc.lower()
            selectors = _DOMAIN_SELECTORS.get(domain, [])
            selectors = selectors + [
                "#dic_area", "#newsct_article", "#articleBody",
                ".article_body", ".article-body", ".article_view",
                "article", "#articeBody",
            ]

            for selector in selectors:
                el = soup.select_one(selector)
                if el:
                    text = re.sub(r"\s+", " ", el.get_text(separator=" ", strip=True))
                    if len(text) > 30:
                        return text[:_CONTENT_LIMIT]

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
        """상위 8개 기사 본문을 병렬 크롤링하여 content 필드 채움."""
        targets = items[:8]
        rest    = items[8:]
        contents = await asyncio.gather(
            *[self._fetch_article_content(it["url"]) for it in targets],
            return_exceptions=True,
        )
        for item, content in zip(targets, contents):
            item["content"] = content if isinstance(content, str) else ""
        return targets + rest

    async def close(self):
        await self._client.aclose()
