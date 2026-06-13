import asyncio
import logging
import time
from datetime import datetime
from .dart_client import DARTClient

logger = logging.getLogger(__name__)


class DARTPoller:

    def __init__(self, api_key: str, kafka_producer, db=None):
        self.client = DARTClient(api_key)
        self.kafka  = kafka_producer
        self.db     = db   # collector setup() 이후 주입
        self._seen: set[str] = set()
        self._poll_interval  = 300  # 5분

        self._filters: list[dict] = []
        self._filters_loaded_at: float = 0
        self._FILTER_TTL = 300  # 5분 캐시

    async def run(self):
        logger.info("DART poller started")
        while True:
            try:
                await self._poll()
            except Exception as e:
                logger.error(f"DART poll error: {e}")
            await asyncio.sleep(self._poll_interval)

    # ── 필터 캐시 ──────────────────────────────────────────────

    async def _load_filters(self):
        if not self.db:
            return
        if time.monotonic() - self._filters_loaded_at < self._FILTER_TTL:
            return
        try:
            rows = await self.db.fetch(
                "SELECT type, value FROM disclosure_filters ORDER BY type, value"
            )
            self._filters = [dict(r) for r in rows]
            self._filters_loaded_at = time.monotonic()
            if self._filters:
                logger.debug(f"Disclosure filters loaded: {len(self._filters)}개")
        except Exception as e:
            logger.debug(f"Filter load error: {e}")

    def _check_flagged(self, parsed: dict) -> bool:
        """공시 제목·종목코드가 등록 필터와 매칭되면 True."""
        if not self._filters:
            return False
        title = (parsed.get("title") or "").lower()
        code  = parsed.get("code") or ""
        for f in self._filters:
            if f["type"] == "keyword" and f["value"].lower() in title:
                return True
            if f["type"] == "stock" and f["value"] == code:
                return True
        return False

    # ── DB 직접 저장 ────────────────────────────────────────────

    async def _write_to_db(self, parsed: dict) -> None:
        if not self.db:
            return
        # DART rcept_dt는 날짜(YYYYMMDD)만 제공 — 수집 시각을 사용해 5분 이내 오차로 기록
        disclosed_at = parsed.get("_collected_at") or datetime.now()

        try:
            async with self.db.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO disclosures
                        (rcept_no, code, corp_name, disclosed_at,
                         report_type, title, category, sentiment_score,
                         is_flagged, contract_amount)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (rcept_no) DO UPDATE SET
                        is_flagged       = EXCLUDED.is_flagged OR disclosures.is_flagged,
                        contract_amount  = COALESCE(EXCLUDED.contract_amount, disclosures.contract_amount)
                    """,
                    parsed.get("rcept_no"),
                    parsed.get("code"),
                    parsed.get("corp_name"),
                    disclosed_at,
                    parsed.get("report_type"),
                    parsed.get("title"),
                    parsed.get("category"),
                    parsed.get("sentiment_score"),
                    parsed.get("is_flagged", False),
                    parsed.get("contract_amount"),
                )
        except Exception as e:
            logger.debug(f"Disclosure DB write error [{parsed.get('rcept_no')}]: {e}")

    # ── 폴링 ───────────────────────────────────────────────────

    async def _poll(self):
        await self._load_filters()

        today = datetime.now().strftime("%Y%m%d")
        data  = await self.client.get_recent_disclosures(start_date=today, end_date=today)

        if data.get("status") != "000":
            logger.warning(f"DART API status: {data.get('status')} - {data.get('message')}")
            return

        items     = data.get("list", [])
        new_count = 0

        collected_at = datetime.now()   # 폴링 시각 — 모든 신규 공시의 disclosed_at 기준

        for item in reversed(items):
            rcept_no = item.get("rcept_no", "")
            if not rcept_no or rcept_no in self._seen:
                continue

            self._seen.add(rcept_no)
            parsed     = self._parse(item)
            parsed["_collected_at"] = collected_at
            is_flagged = self._check_flagged(parsed)
            parsed["is_flagged"] = is_flagged

            # 호재·플래그 공시: 본문 fetch로 키워드/금액 재분석
            if parsed.get("category") == "favorable" or parsed.get("category") == "unfavorable" or is_flagged:
                try:
                    body = await self.client.get_disclosure_body(rcept_no)
                    if body:
                        category, score = self.client.classify(parsed["title"], body)
                        parsed["category"]        = category
                        parsed["sentiment_score"] = score
                        parsed["body_preview"]    = body[:500]
                        # 계약 규모 추출 (수주·계약 공시)
                        amount = self.client.extract_contract_amount(parsed["title"], body)
                        if amount:
                            parsed["contract_amount"] = amount
                except Exception as e:
                    logger.debug(f"Body fetch failed {rcept_no}: {e}")

            await self.kafka.send("disclosure", parsed, key=parsed.get("code") or "UNKNOWN")
            await self._write_to_db(parsed)
            new_count += 1

        if new_count:
            logger.info(f"DART: {new_count} new disclosures (flagged={sum(1 for _ in range(new_count) if True)})")

        # 메모리 관리: 1000개 이상 쌓이면 오래된 것 제거
        if len(self._seen) > 1000:
            self._seen = set(list(self._seen)[-500:])

    def _parse(self, item: dict) -> dict:
        title    = item.get("report_nm", "")
        category, score = self.client.classify(title)
        return {
            "rcept_no":        item.get("rcept_no"),
            "code":            item.get("stock_code") or None,
            "corp_name":       item.get("corp_name"),
            "disclosed_at":    item.get("rcept_dt"),
            "report_type":     item.get("pblntf_ty"),
            "title":           title,
            "category":        category,
            "sentiment_score": score,
            "url": (
                f"https://dart.fss.or.kr/dsaf001/main.do"
                f"?rcpNo={item.get('rcept_no')}"
            ),
        }
