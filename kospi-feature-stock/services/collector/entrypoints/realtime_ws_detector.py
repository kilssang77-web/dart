"""
장중 실시간 WebSocket 탐지기 — e2-micro 무료 실행.

intraday_poller(REST 5분)를 대체: KIS WebSocket으로 체결 틱 수신 → 즉시 탐지.

탐지 이벤트:
  AMOUNT_SURGE  — 누적 거래대금 × 시간보정 vs 20일 평균
  VOLUME_SURGE  — 누적 거래량   × 시간보정 vs 20일 평균
  VI_TRIGGERED  — KIS VI 피드(H0STVI0/H0STCVI0) 직접 수신

흐름:
  1. active_codes 상위 80종목 WebSocket 틱 구독 (cum_volume, cum_amount 필드)
  2. VI 피드 별도 구독 (종목 지정 불필요, 거래소 전체)
  3. 틱 수신마다 elapsed_ratio 보정 후 임계값 비교 → dedup 체크 → 저장/발행
  4. active_codes는 10분마다 Redis에서 갱신 (일봉 후 갱신되는 목록 반영)
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
from kis.websocket_client import KISWebSocketClient

_KST = ZoneInfo("Asia/Seoul")

MARKET_OPEN_MIN  = 9 * 60
MARKET_CLOSE_MIN = 15 * 60 + 30

AMOUNT_SURGE_RATIO = float(os.environ.get("AMOUNT_SURGE_RATIO", "5.0"))
VOL_SURGE_RATIO    = float(os.environ.get("VOL_SURGE_RATIO",    "5.0"))
MIN_AMOUNT         = int(os.environ.get("MIN_AMOUNT",           "500000000"))
DEDUP_TTL          = 90_000   # 25h
CODES_REFRESH_SEC  = 600      # 10분마다 active_codes 갱신

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("realtime-ws-detector")


def _is_market_open() -> bool:
    now = datetime.now(_KST)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return MARKET_OPEN_MIN <= minutes <= MARKET_CLOSE_MIN


def _elapsed_ratio() -> float:
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


async def _save_and_publish(db, redis, event: dict) -> bool:
    try:
        row = await db.fetchrow(
            """
            INSERT INTO feature_events
                (code, detected_at, event_type, price, change_rate,
                 volume, amount, signal_score, signal_data)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb)
            RETURNING id
            """,
            event["code"], event["detected_at"], event["event_type"],
            event.get("price", 0), event.get("change_rate"),
            event.get("volume", 0), event.get("amount", 0),
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
            f"[ws-detector] {event['code']} {event['event_type']} "
            f"score={event['signal_score']:.3f} (id={event_id})"
        )
        return True
    except Exception as e:
        logger.warning(f"[ws-detector] 저장 실패 [{event.get('code')}]: {e}")
        return False


class RealtimeDetector:
    def __init__(self, redis, db):
        self._redis = redis
        self._db    = db
        self._codes: list[str] = []
        self._codes_updated_at = 0.0

    async def _refresh_codes(self) -> None:
        now = asyncio.get_event_loop().time()
        if now - self._codes_updated_at < CODES_REFRESH_SEC:
            return
        codes = await _get_active_codes(self._redis)
        if codes:
            self._codes = codes
            self._codes_updated_at = now
            logger.info(f"[ws-detector] active_codes 갱신: {len(self._codes)}종목")
        elif not self._codes:
            logger.warning("[ws-detector] active_codes 없음 — 재시도 대기")

    async def on_tick(self, tick: dict) -> None:
        """WebSocket 틱 콜백 — AMOUNT_SURGE / VOLUME_SURGE 탐지."""
        if not _is_market_open():
            return

        code        = tick.get("code", "")
        cum_amount  = int(tick.get("cum_amount",  0))
        cum_volume  = int(tick.get("cum_volume",  0))
        price       = int(tick.get("price",       0))

        if cum_amount < MIN_AMOUNT:
            return

        avg_amt_raw = await self._redis.get(f"stats:{code}:avg_amount_20d")
        avg_vol_raw = await self._redis.get(f"stats:{code}:avg_vol_20d")
        avg_amt = float(avg_amt_raw) if avg_amt_raw else 0.0
        avg_vol = float(avg_vol_raw) if avg_vol_raw else 0.0

        if avg_amt <= 0:
            return

        er = max(0.10, _elapsed_ratio())
        now_kst = datetime.now(_KST)

        # AMOUNT_SURGE
        adj_avg_amt = avg_amt * er
        if cum_amount / adj_avg_amt >= AMOUNT_SURGE_RATIO:
            ratio = round(cum_amount / adj_avg_amt, 2)
            if not await _check_dedup(self._redis, code, "AMOUNT_SURGE"):
                score = min(0.95, 0.50 + (ratio - AMOUNT_SURGE_RATIO) / (AMOUNT_SURGE_RATIO * 4))
                ok = await _save_and_publish(self._db, self._redis, {
                    "code": code, "detected_at": now_kst,
                    "event_type": "AMOUNT_SURGE", "price": price,
                    "change_rate": None, "volume": cum_volume, "amount": cum_amount,
                    "signal_score": round(score, 3),
                    "signal_data": {
                        "avg_amount_20d": round(avg_amt),
                        "ratio": ratio, "elapsed_ratio": round(er, 2),
                        "source": "websocket",
                    },
                })
                if ok:
                    await _mark_dedup(self._redis, code, "AMOUNT_SURGE")

        # VOLUME_SURGE
        if avg_vol > 0:
            adj_avg_vol = avg_vol * er
            if adj_avg_vol > 0 and cum_volume / adj_avg_vol >= VOL_SURGE_RATIO:
                ratio = round(cum_volume / adj_avg_vol, 2)
                if not await _check_dedup(self._redis, code, "VOLUME_SURGE"):
                    score = min(0.95, 0.50 + (ratio - VOL_SURGE_RATIO) / (VOL_SURGE_RATIO * 4))
                    ok = await _save_and_publish(self._db, self._redis, {
                        "code": code, "detected_at": now_kst,
                        "event_type": "VOLUME_SURGE", "price": price,
                        "change_rate": None, "volume": cum_volume, "amount": cum_amount,
                        "signal_score": round(score, 3),
                        "signal_data": {
                            "avg_volume_20d": round(avg_vol),
                            "ratio": ratio, "elapsed_ratio": round(er, 2),
                            "source": "websocket",
                        },
                    })
                    if ok:
                        await _mark_dedup(self._redis, code, "VOLUME_SURGE")

    async def on_vi(self, vi: dict) -> None:
        """VI 피드 콜백 — VI_TRIGGERED 탐지."""
        code  = vi.get("code", "")
        price = int(vi.get("price",     0))
        vtype = vi.get("vi_kind", "")

        if not code or not _is_market_open():
            return
        if await _check_dedup(self._redis, code, "VI_TRIGGERED"):
            return

        now_kst = datetime.now(_KST)
        ok = await _save_and_publish(self._db, self._redis, {
            "code": code, "detected_at": now_kst,
            "event_type": "VI_TRIGGERED", "price": price,
            "change_rate": None, "volume": 0, "amount": 0,
            "signal_score": 0.70,
            "signal_data": {"vi_kind": vtype, "source": "websocket"},
        })
        if ok:
            await _mark_dedup(self._redis, code, "VI_TRIGGERED")

    async def run_tick_loop(self, ws: KISWebSocketClient) -> None:
        """틱 구독 루프 — codes 변경 시 재구독."""
        while True:
            await self._refresh_codes()
            if not self._codes:
                await asyncio.sleep(60)
                continue
            try:
                await ws.subscribe_tick(self._codes, self.on_tick)
            except Exception as e:
                logger.error(f"[ws-detector] 틱 WebSocket 오류: {e}", exc_info=True)
                await asyncio.sleep(10)

    async def run_vi_loop(self, ws: KISWebSocketClient) -> None:
        """VI 피드 구독 루프."""
        while True:
            try:
                await ws.subscribe_vi_events(self.on_vi)
            except Exception as e:
                logger.error(f"[ws-detector] VI WebSocket 오류: {e}", exc_info=True)
                await asyncio.sleep(10)

    async def run(self, ws: KISWebSocketClient) -> None:
        logger.info("[ws-detector] 시작 — AMOUNT_SURGE / VOLUME_SURGE / VI_TRIGGERED")
        await asyncio.gather(
            self.run_tick_loop(ws),
            self.run_vi_loop(ws),
        )


async def main():
    redis = redis_lib.from_url(os.environ["REDIS_URL"])

    config = KISConfig(
        app_key=os.environ["KIS_APP_KEY"],
        app_secret=os.environ["KIS_APP_SECRET"],
        account_no=os.environ.get("KIS_ACCOUNT_NO", ""),
    )
    auth = KISAuthManager(config, redis)
    ws   = KISWebSocketClient(config, auth)

    dsn     = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    ssl_val = "require" if "supabase" in dsn else False
    db = await asyncpg.create_pool(
        dsn=dsn, min_size=1, max_size=3,
        ssl=ssl_val, statement_cache_size=0,
    )

    detector = RealtimeDetector(redis, db)
    await detector.run(ws)


if __name__ == "__main__":
    asyncio.run(main())
