"""
장중 실시간 탐지 폴러 v2 — e2-micro에서 무료 실행 가능.

흐름:
  1. 5분마다 (장중에만) active_codes 상위 80종목 REST 조회
  2. AMOUNT_SURGE / VOLUME_SURGE / BREAKOUT_20D,52W / SESSION_CANDLE_WHITE 탐지
  3. Redis dedup 확인 후 feature_events 저장 + ch:feature 발행
  4. 탐지 즉시 Telegram 알림
  5. recommender가 ch:feature 소비 → 추천 생성
"""
import asyncio
import logging
import os
import ssl
import sys
import urllib.request
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

POLL_INTERVAL       = int(os.environ.get("POLL_INTERVAL_SEC",           "300"))
CONCURRENT          = int(os.environ.get("INTRADAY_CONCURRENT",         "5"))
AMOUNT_SURGE_RATIO  = float(os.environ.get("AMOUNT_SURGE_RATIO",        "5.0"))
VOL_SURGE_RATIO     = float(os.environ.get("VOL_SURGE_RATIO",           "5.0"))
MIN_AMOUNT          = int(os.environ.get("MIN_AMOUNT",                  "500000000"))  # 5억
BREAKOUT_MIN_PCT    = float(os.environ.get("BREAKOUT_MIN_PCT",          "0.1"))
SC_MIN_CHANGE       = float(os.environ.get("SESSION_CANDLE_MIN_CHANGE", "3.0"))
SC_BODY_RATIO       = float(os.environ.get("SESSION_CANDLE_BODY_RATIO", "0.6"))
SC_HOUR_AFTER       = int(os.environ.get("SESSION_CANDLE_HOUR_AFTER",   "13"))
BREAKOUT_HOUR_AFTER = 10  # 장 시작 초반 갭 오류 방지
_TG_TOKEN           = os.environ.get("TELEGRAM_TOKEN", "")
_TG_CHAT_ID         = os.environ.get("TELEGRAM_CHAT_ID", "")
DEDUP_TTL           = 90_000   # 25시간 TTL (당일 + 다음날 장 전까지)

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
    return min(1.0, elapsed / 390)


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


def _send_telegram_sync(token: str, chat_id: str, text: str) -> None:
    """urllib.request로 텔레그램 메시지 발송 (동기, 추가 의존성 없음)."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = orjson.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
            resp.read()
    except Exception as e:
        logger.warning(f"[telegram] 전송 실패: {e}")


async def _notify_signal(event_type: str, code: str, price: int,
                          score: float, detail: str = "") -> None:
    """이벤트 발생 즉시 Telegram 알림 (비동기 래퍼, 실패 무시)."""
    if not _TG_TOKEN or not _TG_CHAT_ID:
        return
    lines = [
        f"🔍 <b>[장중탐지] {event_type}</b>",
        f"종목: {code} | 현재가: {price:,}원",
        f"신호강도: {score:.2f}",
    ]
    if detail:
        lines.append(detail)
    text = "\n".join(lines)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _send_telegram_sync, _TG_TOKEN, _TG_CHAT_ID, text)


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
            event.get("change_rate"),
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


async def _detect_breakout(
    redis, code: str, price: int, now_kst: datetime
) -> list[dict]:
    """52주/20일 신고가 돌파 탐지. 10:00 KST 이후만 유효."""
    if now_kst.hour < BREAKOUT_HOUR_AFTER:
        return []
    if price <= 0:
        return []

    checks = [
        ("20d", "BREAKOUT_20D", 0.50),
        ("52w", "BREAKOUT_52W", 0.75),
    ]
    events = []
    for period, etype, base_score in checks:
        raw = await redis.get(f"stats:{code}:high_{period}")
        if not raw:
            continue
        prev_high = float(raw)
        if prev_high <= 0:
            continue
        excess_pct = (price - prev_high) / prev_high * 100
        if excess_pct >= BREAKOUT_MIN_PCT:
            score = min(0.95, base_score + excess_pct / 20.0)
            events.append({
                "event_type":   etype,
                "signal_score": round(score, 3),
                "signal_data":  {
                    "prev_high":  int(prev_high),
                    "excess_pct": round(excess_pct, 2),
                    "period":     period,
                },
                "detail": f"이전고점: {int(prev_high):,}원 | 초과: +{excess_pct:.2f}%",
            })
    return events


def _detect_session_candle(bars: list[dict], now_kst: datetime) -> dict | None:
    """장중 세션 장대양봉 탐지. 13:00 KST 이후만 유효."""
    if now_kst.hour < SC_HOUR_AFTER:
        return None
    if not bars:
        return None

    sorted_bars  = sorted(bars, key=lambda b: b.get("time", ""))
    session_open  = sorted_bars[0].get("open", 0)
    session_close = sorted_bars[-1].get("close", 0)
    session_high  = max(b.get("high", 0) for b in sorted_bars)
    lows          = [b.get("low", 0) for b in sorted_bars if b.get("low", 0) > 0]
    session_low   = min(lows) if lows else 0

    if session_open <= 0 or session_close <= 0 or session_high <= session_low:
        return None

    change_rate = (session_close - session_open) / session_open * 100
    body        = session_close - session_open
    wick        = session_high - session_low
    body_ratio  = body / wick if wick > 0 else 0.0

    if change_rate >= SC_MIN_CHANGE and body_ratio >= SC_BODY_RATIO:
        score = min(0.92, 0.50 + change_rate / 20.0 + body_ratio * 0.1)
        return {
            "event_type":   "SESSION_CANDLE_WHITE",
            "signal_score": round(score, 3),
            "signal_data":  {
                "session_open":  session_open,
                "session_close": session_close,
                "change_rate":   round(change_rate, 2),
                "body_ratio":    round(body_ratio, 2),
            },
            "detail": f"변화율: +{change_rate:.2f}% | 몸통비율: {body_ratio:.2f}",
        }
    return None


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

    latest       = max(bars, key=lambda b: b.get("time", ""))
    acml_amount  = latest.get("amount", 0)
    close_price  = latest.get("close", 0)
    total_volume = sum(b.get("volume", 0) for b in bars)

    if acml_amount < MIN_AMOUNT:
        return 0

    avg_vol_raw = await redis.get(f"stats:{code}:avg_vol_20d")
    avg_amt_raw = await redis.get(f"stats:{code}:avg_amt_20d")
    avg_vol = float(avg_vol_raw) if avg_vol_raw else 0.0
    avg_amt = float(avg_amt_raw) if avg_amt_raw else 0.0

    if avg_amt <= 0:
        return 0

    er      = max(0.10, elapsed_ratio)
    now_kst = datetime.now(_KST)
    saved   = 0

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
                    "avg_amt_20d":  round(avg_amt),
                    "ratio":        ratio,
                    "elapsed_ratio": round(er, 2),
                },
            })
            if ok:
                await _mark_dedup(redis, code, "AMOUNT_SURGE")
                await _notify_signal("AMOUNT_SURGE", code, close_price, score,
                                     f"거래대금 {ratio}배 (20일 평균 대비)")
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
                        "avg_vol_20d":   round(avg_vol),
                        "ratio":         ratio,
                        "elapsed_ratio": round(er, 2),
                    },
                })
                if ok:
                    await _mark_dedup(redis, code, "VOLUME_SURGE")
                    await _notify_signal("VOLUME_SURGE", code, close_price, score,
                                         f"거래량 {ratio}배 (20일 평균 대비)")
                    saved += 1

    # ── BREAKOUT_20D / BREAKOUT_52W (10:00 KST 이후) ──────────────
    bo_events = await _detect_breakout(redis, code, close_price, now_kst)
    for bo in bo_events:
        etype = bo["event_type"]
        if not await _check_dedup(redis, code, etype):
            ok = await _save_and_publish(db, redis, {
                "code":         code,
                "detected_at":  now_kst,
                "event_type":   etype,
                "price":        close_price,
                "change_rate":  None,
                "volume":       total_volume,
                "amount":       acml_amount,
                "signal_score": bo["signal_score"],
                "signal_data":  bo["signal_data"],
            })
            if ok:
                await _mark_dedup(redis, code, etype)
                await _notify_signal(etype, code, close_price,
                                     bo["signal_score"], bo["detail"])
                saved += 1

    # ── SESSION_CANDLE_WHITE (13:00 KST 이후) ─────────────────────
    sc = _detect_session_candle(bars, now_kst)
    if sc and not await _check_dedup(redis, code, "SESSION_CANDLE_WHITE"):
        ok = await _save_and_publish(db, redis, {
            "code":         code,
            "detected_at":  now_kst,
            "event_type":   "SESSION_CANDLE_WHITE",
            "price":        close_price,
            "change_rate":  sc["signal_data"]["change_rate"],
            "volume":       total_volume,
            "amount":       acml_amount,
            "signal_score": sc["signal_score"],
            "signal_data":  sc["signal_data"],
        })
        if ok:
            await _mark_dedup(redis, code, "SESSION_CANDLE_WHITE")
            await _notify_signal("SESSION_CANDLE_WHITE", code, close_price,
                                  sc["signal_score"], sc["detail"])
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

    logger.info(
        f"[intraday-poller v2] 시작 — 폴링 {POLL_INTERVAL}s / 동시 {CONCURRENT}종목 "
        f"/ 탐지: AMOUNT_SURGE, VOLUME_SURGE, BREAKOUT_20D/52W, SESSION_CANDLE_WHITE"
    )

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
