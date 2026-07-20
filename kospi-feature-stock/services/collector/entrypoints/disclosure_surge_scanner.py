"""
POST_DISCLOSURE_SURGE 배치 스캐너 (장 마감 후 GitHub Actions).

흐름:
  1. DART API → 당일 공시 목록 수집 (호재 분류 필터링)
  2. daily_bars에서 공시 종목 당일 실적 조회
  3. change_rate >= 3% AND volume >= avg_vol_20d * 2.0 → POST_DISCLOSURE_SURGE 이벤트 생성
  4. feature_events 저장 + Redis ch:feature 발행

판단 근거:
  - 공시 당일 주가 3%+ 상승 + 거래량 2배 이상 → 공시 모멘텀 확인 종목
  - favorable 공시(호재 키워드 감지)만 대상으로 거짓양성 최소화
  - signal_score: 0.55 기본 + change_rate/40 보정 (최대 0.90)
"""

import asyncio
import logging
import os
import sys
from datetime import date, datetime, timezone

import asyncpg
import orjson
import redis.asyncio as redis_lib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dart.dart_client import DARTClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("disclosure-surge-scanner")

MIN_CHANGE_RATE   = float(os.environ.get("PDS_MIN_CHANGE_RATE",  "3.0"))   # 3%+
MIN_VOL_RATIO     = float(os.environ.get("PDS_MIN_VOL_RATIO",    "2.0"))   # 평균 2배+
MIN_AMOUNT        = int(os.environ.get("PDS_MIN_AMOUNT",          "500000000"))  # 5억
MAX_DISCLOSURES   = int(os.environ.get("PDS_MAX_DISCLOSURES",     "300"))   # 하루 최대 조회
DART_PAGES        = int(os.environ.get("PDS_DART_PAGES",          "3"))     # 최대 3페이지


async def _get_today_disclosed_codes(dart: DARTClient, today: date) -> dict[str, str]:
    """DART 당일 호재 공시 종목 코드 → {stock_code: report_name} 수집."""
    date_str  = today.strftime("%Y%m%d")
    code_map: dict[str, str] = {}

    for page in range(1, DART_PAGES + 1):
        try:
            data = await dart.get_recent_disclosures(
                start_date=date_str, end_date=date_str, page=page
            )
        except Exception as e:
            logger.warning(f"[PDS] DART API 오류 page={page}: {e}")
            break

        items = data.get("list", [])
        if not items:
            break

        for item in items:
            stock_code = (item.get("stock_code") or "").strip()
            if not stock_code or len(stock_code) != 6:
                continue

            report_nm = item.get("report_nm", "")
            sentiment, score = dart.classify(report_nm)
            if sentiment != "favorable":
                continue

            code_map[stock_code] = report_nm
            if len(code_map) >= MAX_DISCLOSURES:
                return code_map

        await asyncio.sleep(0.3)

    logger.info(f"[PDS] 호재 공시 종목 {len(code_map)}개 수집 (date={date_str})")
    return code_map


async def _fetch_today_bars(
    db: asyncpg.Pool, codes: list[str], today: date
) -> dict[str, dict]:
    if not codes:
        return {}
    rows = await db.fetch(
        """
        SELECT code, close, change_rate, volume, amount
        FROM daily_bars
        WHERE code = ANY($1::varchar[])
          AND date  = $2
          AND close > 0
          AND amount >= $3
        """,
        codes, today, MIN_AMOUNT,
    )
    return {r["code"]: dict(r) for r in rows}


async def _fetch_redis_avg_vol(
    redis: redis_lib.Redis, codes: list[str]
) -> dict[str, float]:
    if not codes:
        return {}
    pipe = redis.pipeline()
    for code in codes:
        pipe.get(f"stats:{code}:avg_vol_20d")
    raw = await pipe.execute()
    result: dict[str, float] = {}
    for code, val in zip(codes, raw):
        if val is not None:
            try:
                result[code] = float(val)
            except (ValueError, TypeError):
                pass
    return result


async def _already_detected(db: asyncpg.Pool, codes: list[str], today: date) -> set[str]:
    rows = await db.fetch(
        """
        SELECT DISTINCT code FROM feature_events
        WHERE event_type = 'POST_DISCLOSURE_SURGE'
          AND detected_at::date = $1
          AND code = ANY($2::varchar[])
        """,
        today, codes,
    )
    return {r["code"] for r in rows}


async def _write_events(db: asyncpg.Pool, redis: redis_lib.Redis, events: list[dict]) -> int:
    if not events:
        return 0

    now = datetime.now(timezone.utc)
    saved = 0
    for ev in events:
        try:
            row = await db.fetchrow(
                """
                INSERT INTO feature_events
                    (detected_at, code, event_type, price, change_rate,
                     volume, amount, signal_score, risk_score, signal_data)
                VALUES ($1,$2,'POST_DISCLOSURE_SURGE',$3,$4,$5,$6,$7,$8,$9::jsonb)
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                now, ev["code"], ev["price"], ev["change_rate"],
                ev["volume"], ev["amount"],
                ev["signal_score"], ev["risk_score"],
                orjson.dumps(ev["signal_data"]).decode(),
            )
            if row:
                payload = orjson.dumps({
                    **ev,
                    "id":          row["id"],
                    "event_type":  "POST_DISCLOSURE_SURGE",
                    "detected_at": now.isoformat(),
                })
                await redis.publish("ch:feature", payload)
                saved += 1
        except Exception as e:
            logger.warning(f"[PDS] DB 저장 실패 {ev['code']}: {e}")

    return saved


async def run():
    dart_key = os.environ.get("DART_API_KEY", "")
    if not dart_key:
        logger.warning("[PDS] DART_API_KEY 없음 — 스캔 스킵")
        return

    dsn     = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    ssl_val = "require" if "supabase" in dsn else False
    db = await asyncpg.create_pool(
        dsn=dsn, min_size=1, max_size=3,
        ssl=ssl_val, statement_cache_size=0,
    )
    redis = redis_lib.from_url(os.environ["REDIS_URL"], decode_responses=False)

    try:
        today = date.today()
        dart  = DARTClient(dart_key)

        # 1. 당일 호재 공시 종목 수집
        code_map = await _get_today_disclosed_codes(dart, today)
        if not code_map:
            logger.info("[PDS] 호재 공시 없음 — 종료")
            return

        codes = list(code_map.keys())

        # 2. 당일 일봉 조회
        bars_map = await _fetch_today_bars(db, codes, today)
        if not bars_map:
            logger.info("[PDS] 당일 일봉 없음 — 종료 (일봉 수집 후 재실행 필요)")
            return

        # 3. Redis 평균 거래량 조회
        avg_vol_map = await _fetch_redis_avg_vol(redis, list(bars_map.keys()))

        # 4. 이미 탐지된 종목 제외
        detected = await _already_detected(db, list(bars_map.keys()), today)

        # 5. 조건 판정
        events: list[dict] = []
        for code, bar in bars_map.items():
            if code in detected:
                continue

            change_rate = float(bar.get("change_rate") or 0)
            if change_rate < MIN_CHANGE_RATE:
                continue

            avg_vol = avg_vol_map.get(code, 0)
            volume  = bar.get("volume") or 0
            if avg_vol > 0 and volume < avg_vol * MIN_VOL_RATIO:
                continue

            vol_ratio = round(volume / avg_vol, 2) if avg_vol > 0 else None
            score     = min(0.90, 0.55 + change_rate / 40.0)

            events.append({
                "code":         code,
                "price":        bar.get("close", 0),
                "change_rate":  change_rate,
                "volume":       volume,
                "amount":       bar.get("amount", 0),
                "signal_score": round(score, 3),
                "risk_score":   round(max(0.15, 0.80 - score), 3),
                "signal_data":  {
                    "report_nm":    code_map[code],
                    "change_rate":  change_rate,
                    "vol_ratio":    vol_ratio,
                    "avg_vol_20d":  int(avg_vol) if avg_vol else None,
                    "source":       "dart_batch",
                },
            })

        logger.info(f"[PDS] POST_DISCLOSURE_SURGE 후보: {len(events)}개")

        # 6. 저장 + 발행
        saved = await _write_events(db, redis, events)
        logger.info(f"[PDS] 저장 완료: {saved}개")

    finally:
        await db.close()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(run())
