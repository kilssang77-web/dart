"""
장중 실시간 탐지 폴러 — e2-micro에서 무료 실행 가능.

WebSocket 없이 KIS REST API 5분 폴링으로 거래대금/거래량 급등 탐지.
collector-tick(256MB) + detector(128MB) 대신 단일 서비스 ~120MB.

흐름:
  1. 5분마다 (장중에만) active_codes 상위 80종목 REST 조회
  2. 당일 누적 거래대금 × 시간보정 vs 20일 평균 비교 → AMOUNT_SURGE / VOLUME_SURGE
  3. Redis dedup 확인 후 feature_events 저장 + ch:feature 발행
  4. recommender가 ch:feature 소비 → 추천 생성
"""
import asyncio
import logging
import os
import sys
import orjson
import asyncpg
import redis.asyncio as redis_lib
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kis.auth import KISConfig, KISAuthManager
from kis.rest_client import KISRestClient

_KST = ZoneInfo("Asia/Seoul")

MARKET_OPEN_MIN  = 9 * 60        # 09:00
MARKET_CLOSE_MIN = 15 * 60 + 30  # 15:30

POLL_INTERVAL      = int(os.environ.get("POLL_INTERVAL_SEC",   "300"))
CONCURRENT         = int(os.environ.get("INTRADAY_CONCURRENT", "5"))
AMOUNT_SURGE_RATIO = float(os.environ.get("AMOUNT_SURGE_RATIO","5.0"))
VOL_SURGE_RATIO    = float(os.environ.get("VOL_SURGE_RATIO",   "5.0"))
MIN_AMOUNT         = int(os.environ.get("MIN_AMOUNT",          "500000000"))  # 5억
DEDUP_TTL          = 90_000   # 25시간 TTL (당일 + 다음날 장 전까지)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("intraday-poller")


def _is_market_open() -> bool:
    now = datetime.now(_KST)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return MARKET_OPEN_MIN <= minutes <= MARKET_CLOSE_MIN


def _elapsed_ratio() -> float:
    """장 시작(09:00) 이후 경과 비율 0.0~1.0. 시간보정 급등 비교에 사용."""
    now = datetime.now(_KST)
    open_t = now.replace(hour=9, minute=0, second=0, microsecond=0)
    elapsed = max(0.0, (now - open_t).total_seconds() / 60)
    return min(1.0, elapsed / 390)   # 390분 = 6.5시간 (1거래일)


async def _get_active_codes(redis) -> list[str]:
    cached = await redis.get("stocks:active_codes")
    if cached:
        try:
            codes = orjson.loads(cached)
            return [str(c).zfill(6) for c in codes if c][:80]
        except Exception:
            pass
    return []


async def _check_dedup(redis, code: str, event_type: str) -> bool:
    today = datetime.now(_KST).strftime("%Y-%m-%d")
    return bool(await redis.exists(f"intraday_dedup:{code}:{event_type}:{today}"))


async def _mark_dedup(redis, code: str, event_type: str) -> None:
    today = datetime.now(_KST).strftime("%Y-%m-%d")
    await redis.set(f"intraday_dedup:{code}:{event_type}:{today}", "1", ex=DEDUP_TTL)


async def _save_and_publish(db, redis, event: dict) -> bool:
    """feature_events 저장 후 ch:feature 발행. 성공 시 True."""
    try:
        row = await db.fetchrow(
            """
            INSERT INTO feature_events
                (code, detected_at, event_type, price, change_rate,
                 volume, amount, signal_score, signal_data)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
            RETURNING id
            """,
            event["code"],
            event["detected_at"],
            event["event_type"],
            event.get("price", 0),
            event.get("change_rate"),          # None 허용
            event.get("volume", 0),
            event.get("amount", 0),
            event.get("signal_score", 0.5),
            orjson.dumps(event.get("signal_data", {})).decode(),
        )
        if not row:
            return False

        event_id = row["id"]
        payload = orjson.dumps({
            **{k: v for k, v in event.items() if k != "detected_at"},
            "id":          event_id,
            "detected_at": event["detected_at"].isoformat(),
        })
        await redis.publish("ch:feature", payload)
        logger.info(
            f"[intraday] {event['code']} {event['event_type']} "
            f"score={event['signal_score']} → ch:feature (id={event_id})"
        )
        return True
    except Exception as e:
        logger.warning(f"[intraday] 저장/발행 실패 [{event.get('code')}]: {e}")
        return False


async def _scan_code(
    rest: KISRestClient,
    redis,
    db,
    code: str,
    elapsed_ratio: float,
) -> int:
    """단일 종목 스캔. 저장된 이벤트 수 반환."""
    try:
        bars = await rest.get_minute_bars(code)
    except Exception:
        return 0
    if not bars:
        return 0

    # 최신 바 = 누적 거래대금 기준
    latest       = max(bars, key=lambda b: b.get("time", ""))
    acml_amount  = latest.get("amount", 0)
    close_price  = latest.get("close", 0)
    total_volume = sum(b.get("volume", 0) for b in bars)

    if acml_amount < MIN_AMOUNT:
        return 0

    avg_vol_raw = await redis.get(f"stats:{code}:avg_vol_20d")
    avg_amt_raw = await redis.get(f"stats:{code}:avg_amount_20d")
    avg_vol = float(avg_vol_raw) if avg_vol_raw else 0.0
    avg_amt = float(avg_amt_raw) if avg_amt_raw else 0.0

    if avg_amt <= 0:
        return 0

    # 시간 보정: 장 시작 직후 과탐지 방지 (최소 10% 기준)
    er = max(0.10, elapsed_ratio)
    now_kst = datetime.now(_KST)
    saved = 0

    # ── AMOUNT_SURGE ──────────────────────────────────────────────
    adj_avg_amt = avg_amt * er
    if acml_amount / adj_avg_amt >= AMOUNT_SURGE_RATIO:
        if not await _check_dedup(redis, code, "AMOUNT_SURGE"):
            ratio = round(acml_amount / adj_avg_amt, 2)
            score = min(0.95, 0.50 + (ratio - AMOUNT_SURGE_RATIO) / (AMOUNT_SURGE_RATIO * 4))
            ok = await _save_and_publish(db, redis, {
                "code":         code,
                "detected_at":  now_kst,
                "event_type":   "AMOUNT_SURGE",
                "price":        close_price,
                "change_rate":  None,
                "volume":       total_volume,
                "amount":       acml_amount,
                "signal_score": round(score, 3),
                "signal_data":  {
                    "avg_amount_20d": round(avg_amt),
                    "ratio":          ratio,
                    "elapsed_ratio":  round(er, 2),
                },
            })
            if ok:
                await _mark_dedup(redis, code, "AMOUNT_SURGE")
                saved += 1

    # ── VOLUME_SURGE ──────────────────────────────────────────────
    if avg_vol > 0:
        adj_avg_vol = avg_vol * er
        if adj_avg_vol > 0 and total_volume / adj_avg_vol >= VOL_SURGE_RATIO:
            if not await _check_dedup(redis, code, "VOLUME_SURGE"):
                ratio = round(total_volume / adj_avg_vol, 2)
                score = min(0.95, 0.50 + (ratio - VOL_SURGE_RATIO) / (VOL_SURGE_RATIO * 4))
                ok = await _save_and_publish(db, redis, {
                    "code":         code,
                    "detected_at":  now_kst,
                    "event_type":   "VOLUME_SURGE",
                    "price":        close_price,
                    "change_rate":  None,
                    "volume":       total_volume,
                    "amount":       acml_amount,
                    "signal_score": round(score, 3),
                    "signal_data":  {
                        "avg_volume_20d": round(avg_vol),
                        "ratio":          ratio,
                        "elapsed_ratio":  round(er, 2),
                    },
                })
                if ok:
                    await _mark_dedup(redis, code, "VOLUME_SURGE")
                    saved += 1

    return saved


async def run_scan(rest: KISRestClient, redis, db) -> int:
    codes = await _get_active_codes(redis)
    if not codes:
        logger.warning("[intraday-poller] 활성 종목 없음 — 스캔 스킵")
        return 0

    er  = _elapsed_ratio()
    sem = asyncio.Semaphore(CONCURRENT)

    async def _one(code):
        async with sem:
            return await _scan_code(rest, redis, db, code, er)

    results = await asyncio.gather(*[_one(c) for c in codes], return_exceptions=True)
    total = sum(r for r in results if isinstance(r, int))
    logger.info(f"[intraday-poller] {len(codes)}종목 스캔 완료 → {total}건 탐지")
    return total


async def main():
    redis = redis_lib.from_url(os.environ["REDIS_URL"])

    config = KISConfig(
        app_key=os.environ["KIS_APP_KEY"],
        app_secret=os.environ["KIS_APP_SECRET"],
        account_no=os.environ.get("KIS_ACCOUNT_NO", ""),
    )
    auth = KISAuthManager(config, redis)
    rest = KISRestClient(config, auth)

    dsn = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    ssl_val = "require" if "supabase" in dsn else False
    db = await asyncpg.create_pool(
        dsn=dsn, min_size=1, max_size=5,
        ssl=ssl_val, statement_cache_size=0,
    )

    logger.info(f"[intraday-poller] 시작 — 폴링 {POLL_INTERVAL}s / 동시 {CONCURRENT}종목")

    while True:
        if _is_market_open():
            try:
                await run_scan(rest, redis, db)
            except Exception as e:
                logger.error(f"[intraday-poller] 스캔 오류: {e}", exc_info=True)
        else:
            logger.debug("[intraday-poller] 장외 시간 — 대기")

        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
