"""
KIND(한국거래소 공시) 수집 모듈.
KIND는 공식 API가 없으므로 kind.krx.co.kr HTML 파싱 방식으로 수집.
DART와 중복 제출되는 공시를 제외하고 거래소 고유 공시만 수집.
"""
import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta

_KST = timezone(timedelta(hours=9))

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_KIND_URL  = "https://kind.krx.co.kr/disclosure/todaydisclosure.do"
_KIND_BASE = "https://kind.krx.co.kr"

# DART와 중복되지 않는 거래소 고유 공시 유형
_KRX_ONLY_TYPES = {
    "조회공시", "매매거래정지", "불성실공시", "시장경보",
    "투자주의", "투자위험", "투자경고", "거래량급등",
    "단기과열", "공매도과열",
}


_RETRY_DELAYS = (0, 5, 15)  # 초 단위 재시도 간격 (3회)


class KINDPoller:

    def __init__(self, kafka_producer, poll_interval: int = 300):
        self._kafka              = kafka_producer
        self._poll_interval      = poll_interval
        self._seen: set[str]     = set()
        self._consecutive_empty  = 0   # 연속 빈 결과 카운터 (구조 변경 감지용)
        self._client = httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": _KIND_BASE,
            },
        )

    async def run(self):
        logger.info("KIND poller started")
        while True:
            try:
                await self._poll()
            except Exception as e:
                logger.error(f"KIND poll error: {e}")
            await asyncio.sleep(self._poll_interval)

    async def _poll(self):
        today = datetime.now().strftime("%Y%m%d")
        items = await self._fetch_today(today)
        new_count = 0

        for item in items:
            uid = item.get("rcept_no", "")
            if not uid or uid in self._seen:
                continue
            self._seen.add(uid)
            await self._kafka.send("disclosure", item, key=item.get("code") or "UNKNOWN")
            new_count += 1

        if new_count:
            logger.info(f"KIND: {new_count} new disclosures")
            self._consecutive_empty = 0
        else:
            self._consecutive_empty += 1
            if self._consecutive_empty >= 6:  # 30분 연속 무신호
                logger.warning(
                    f"KIND: {self._consecutive_empty}회 연속 결과 없음 — "
                    "HTML 구조 변경 또는 연결 문제 가능성"
                )

        if len(self._seen) > 2000:
            self._seen = set(list(self._seen)[-1000:])

    async def _fetch_today(self, date_str: str) -> list[dict]:
        last_exc: Exception | None = None
        for attempt, delay in enumerate(_RETRY_DELAYS):
            if delay:
                await asyncio.sleep(delay)
            try:
                resp = await self._client.post(
                    _KIND_URL,
                    data={
                        "method":          "searchTodayDisclosureSub",
                        "currentPageSize": "100",
                        "pageIndex":       "1",
                        "orderMode":       "0",
                        "orderStat":       "D",
                        "forward":         "todaydisclosure_sub",
                        "chose":           "S",
                        "todayFlag":       "Y",
                        "repIsuSrtCd":     "",
                    },
                )
                resp.raise_for_status()
                return self._parse(resp.text)
            except Exception as e:
                last_exc = e
                logger.warning(f"KIND fetch attempt {attempt + 1} failed: {e}")

        logger.error(f"KIND fetch failed after {len(_RETRY_DELAYS)} attempts: {last_exc}")
        return []

    def _parse(self, html: str) -> list[dict]:
        soup  = BeautifulSoup(html, "lxml")
        items = []

        rows = soup.select("table.list tbody tr")
        if not rows:
            # 연시장 외 시간대에는 정상 응답 직엁, 안내 문단만 존재하면 WARN
            if "table" not in html.lower() or len(html) < 500:
                logger.warning("KIND: table.list 대 셀렉터 미일치 — HTML 구조 변경 가능")
            return items

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue

            try:
                time_text  = cols[0].get_text(strip=True)
                code_text  = cols[1].get_text(strip=True)
                title_el   = cols[2].find("a") or cols[2]  # 공시 제목(링크) in cols[2]
                title_text = title_el.get_text(strip=True)
                href       = title_el.get("href", "") if title_el.name == "a" else ""
                corp_text  = cols[3].get_text(strip=True)  # 법인명 in cols[3]
                type_text  = cols[4].get_text(strip=True) if len(cols) > 4 else ""
            except Exception:
                continue

            if not title_text or not corp_text:
                continue

            # 종목코드 정제 (6자리 숫자)
            code_match = re.search(r"\d{6}", code_text)
            code = code_match.group() if code_match else None

            # 공시 URL
            url = (_KIND_BASE + href) if href and not href.startswith("http") else href

            # 고유 ID (corp + time + title 해시)
            uid = f"kind_{corp_text}_{time_text}_{title_text[:30]}"

            disclosed_at = self._parse_time(time_text)

            items.append({
                "rcept_no":        uid,
                "code":            code,
                "corp_name":       corp_text,
                "disclosed_at":    disclosed_at,
                "report_type":     "KIND",
                "disclosure_type": type_text,
                "title":           title_text,
                "url":             url,
                "source":          "KIND",
                "category":        "neutral",
                "sentiment_score": 0.0,
            })

        return items

    @staticmethod
    def _parse_time(text: str) -> str:
        text = text.strip()
        now  = datetime.now(_KST)
        # HH:MM 형태
        m = re.match(r"^(\d{1,2}):(\d{2})$", text)
        if m:
            return now.replace(
                hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0
            ).isoformat()
        return now.isoformat()

    async def close(self):
        await self._client.aclose()
