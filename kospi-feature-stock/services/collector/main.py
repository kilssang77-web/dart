import asyncio
import logging
import os
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

_KST = ZoneInfo("Asia/Seoul")

import asyncpg
import orjson
import redis.asyncio as redis_lib

from kis.auth import KISConfig, KISAuthManager
from kis.websocket_client import KISWebSocketClient
from kis.rest_client import KISRestClient
from dart.disclosure_poller import DARTPoller
from dart.kind_poller import KINDPoller
from kafka.producer import KafkaProducerWrapper
from db.writer import write_tick, write_minute_bars, write_daily_bars, write_supply_demand
from news.naver_crawler import NaverNewsCrawler
from batch_scanner import BatchScanner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("collector")

MARKET_OPEN  = dtime(9, 0)
MARKET_CLOSE = dtime(15, 35)
STATS_TIME   = dtime(16, 10)   # 장 마감 후 통계 갱신
BATCH_TIME   = dtime(16, 40)   # 배치 탐지 시작 (stats 갱신 완료 후)

NXT_ENABLED    = os.environ.get("NXT_ENABLED", "0") == "1"
NXT_AFTER_OPEN  = dtime(16, 0)
NXT_AFTER_CLOSE = dtime(20, 0)

# 환경변수로 주요 파라미터 설정
TICK_FLUSH_SEC   = int(os.environ.get("TICK_FLUSH_SEC", "5"))
MINUTE_INTERVAL  = int(os.environ.get("MINUTE_INTERVAL_SEC", "60"))
SUPPLY_INTERVAL  = int(os.environ.get("SUPPLY_INTERVAL_SEC", "1800"))
BACKFILL_DAYS    = int(os.environ.get("DAILY_BACKFILL_DAYS", "260"))
NEWS_INTERVAL    = int(os.environ.get("NEWS_INTERVAL_SEC", "1800"))

# 전 종목 인트라데이 REST 스캔 — KIS 20 TPS 기준 안전 마진 87%
INTRADAY_REQ_INTERVAL = float(os.environ.get("INTRADAY_REQ_INTERVAL", "0.09"))  # ~11 req/s
INTRADAY_VOL_RATIO    = float(os.environ.get("INTRADAY_VOL_RATIO",    "3.0"))   # 거래량 급증 배율
INTRADAY_AMT_RATIO    = float(os.environ.get("INTRADAY_AMT_RATIO",    "3.0"))   # 거래대금 급증 배율
INTRADAY_MIN_AMOUNT   = int(os.environ.get("INTRADAY_MIN_AMOUNT",     "200000000"))  # 최소 2억


def is_market_open() -> bool:
    now = datetime.now(_KST)
    return now.weekday() < 5 and MARKET_OPEN <= now.time() <= MARKET_CLOSE


def is_after_close() -> bool:
    now = datetime.now(_KST)
    return now.weekday() < 5 and now.time() >= STATS_TIME


def is_nxt_aftermarket() -> bool:
    """NXT_ENABLED=1 이고 16:00~20:00(평일) 이면 True."""
    if not NXT_ENABLED:
        return False
    now = datetime.now(_KST)
    return now.weekday() < 5 and NXT_AFTER_OPEN <= now.time() <= NXT_AFTER_CLOSE


_BASE_CODES = [
    "005930", "000660", "035420", "005380", "051910",
    "006400", "035720", "028260", "207940", "068270",
    "323410", "105560", "055550", "086790", "032830",
    "066570", "003550", "096770", "033780", "015760",
]


async def load_active_stocks(redis: redis_lib.Redis) -> list[str]:
    """실시간 모니터링 대상 (WebSocket·분봉): Redis 캐시 → 기본 20개 fallback."""
    try:
        cached = await redis.get("stocks:active_codes")
        if cached:
            try:
                codes = orjson.loads(cached)
            except Exception:
                # redis-cli 등으로 저장된 unquoted 형식 [000660,005930,...] 복구
                text = cached.decode() if isinstance(cached, bytes) else cached
                raw = text.strip().lstrip("[").rstrip("]")
                codes = [c.strip().strip('"').strip("'").zfill(6) for c in raw.split(",") if c.strip()]
            if codes and isinstance(codes, list):
                # 형식 정상화: 항상 문자열, 6자리 0패딩
                codes = [str(c).zfill(6) for c in codes if c]
                # 손상된 값이면 DB에서 재초기화 (다음 호출을 위해)
                return codes
    except Exception:
        pass
    return _BASE_CODES


async def refresh_active_codes_from_db(db: asyncpg.Pool, redis: redis_lib.Redis, top_n: int = 80) -> list[str]:
    """Redis에 active_codes 없을 때 DB 거래대금 상위 N개로 초기화."""
    try:
        rows = await db.fetch(
            """
            SELECT code
            FROM (
                SELECT code, AVG(amount) AS avg_amt
                FROM daily_bars
                WHERE date >= CURRENT_DATE - INTERVAL '20 days'
                  AND amount > 0
                GROUP BY code
            ) t
            ORDER BY avg_amt DESC
            LIMIT $1
            """,
            top_n,
        )
        top_codes = [r["code"] for r in rows]
        merged = list(dict.fromkeys(top_codes + _BASE_CODES))[:100]
        if merged:
            await redis.set("stocks:active_codes", orjson.dumps(merged), ex=90_000)
            logger.info(f"[ActiveCodes] Bootstrapped {len(merged)} codes from DB (top {top_n} by 20d avg amount)")
        return merged
    except Exception as e:
        logger.warning(f"[ActiveCodes] DB bootstrap failed: {e}")
        return _BASE_CODES


async def load_all_stocks(db: asyncpg.Pool) -> list[str]:
    """전체 활성 종목 코드 (일봉 수집·배치 탐지 대상): DB에서 로드."""
    try:
        rows = await db.fetch(
            "SELECT code FROM stocks WHERE is_active = TRUE ORDER BY code"
        )
        return [r["code"] for r in rows]
    except Exception as e:
        logger.warning(f"[AllStocks] DB load failed: {e}")
        return []


async def load_kospi_kosdaq(db: asyncpg.Pool) -> list[str]:
    """KOSPI + KOSDAQ 활성 종목 — 인트라데이 REST 스캔 대상 (거래량 많은 순)."""
    try:
        rows = await db.fetch(
            """
            SELECT s.code
            FROM stocks s
            LEFT JOIN (
                SELECT code, AVG(amount) AS avg_amt
                FROM daily_bars
                WHERE date >= CURRENT_DATE - INTERVAL '20 days' AND amount > 0
                GROUP BY code
            ) b ON b.code = s.code
            WHERE s.is_active = TRUE
              AND s.market IN ('KOSPI', 'KOSDAQ')
            ORDER BY COALESCE(b.avg_amt, 0) DESC
            """
        )
        return [r["code"] for r in rows]
    except Exception as e:
        logger.warning(f"[KospiKosdaq] DB load failed: {e}")
        return []


class StockCollector:

    def __init__(self):
        self.redis = redis_lib.from_url(os.environ["REDIS_URL"])
        self.kafka = KafkaProducerWrapper(os.environ["KAFKA_BOOTSTRAP_SERVERS"])
        self.db: asyncpg.Pool | None = None

        config = KISConfig(
            app_key=os.environ["KIS_APP_KEY"],
            app_secret=os.environ["KIS_APP_SECRET"],
            account_no=os.environ.get("KIS_ACCOUNT_NO", ""),
        )
        self.auth = KISAuthManager(config, self.redis)
        self.ws   = KISWebSocketClient(config, self.auth)
        self.rest = KISRestClient(config, self.auth)
        self.dart = DARTPoller(os.environ["DART_API_KEY"], self.kafka)
        self.kind = KINDPoller(self.kafka)
        self.news = NaverNewsCrawler()

        self._tick_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self._daily_bars_done = asyncio.Event()   # 일봉+stats 완료 신호

    async def setup(self):
        dsn = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
        self.db = await asyncpg.create_pool(dsn=dsn, min_size=3, max_size=10)
        self.dart.db = self.db   # DB 풀 주입 — 공시 직접 저장 + 필터 매칭 활성화
        logger.info("DB pool created")

    async def run_tick_only(self):
        """실시간 틱 + 분봉 (WebSocket) + 전 종목 인트라데이 REST 스캔."""
        await self.setup()
        cached_active = await self.redis.get("stocks:active_codes")
        if not cached_active and self.db:
            active_codes = await refresh_active_codes_from_db(self.db, self.redis, top_n=80)
        else:
            active_codes = await load_active_stocks(self.redis)

        all_codes = await load_all_stocks(self.db) if self.db else active_codes

        logger.info(f"[tick] WS={len(active_codes)} | REST-scan={len(all_codes)} stocks")
        await asyncio.gather(
            self._tick_loop(active_codes),
            self._tick_db_writer(),
            self._dynamic_tick_loop(),
            self._minute_bar_loop(active_codes),
            self._watching_scan_loop(),
            self._intraday_rest_scan_loop(all_codes),
            return_exceptions=True,
        )

    async def run(self):
        await self.setup()

        # 전체 종목: DB에서 로드 (일봉 수집 + 배치 탐지)
        all_codes = await load_all_stocks(self.db)
        if not all_codes:
            logger.warning("[Run] stocks table empty — falling back to active_codes for all ops")

        # 실시간 모니터링: Redis 캐시 → Redis 없으면 DB 상위 80개로 초기화
        cached_active = await self.redis.get("stocks:active_codes")
        if not cached_active and self.db:
            active_codes = await refresh_active_codes_from_db(self.db, self.redis, top_n=80)
        else:
            active_codes = await load_active_stocks(self.redis)
        if not all_codes:
            all_codes = active_codes

        logger.info(f"[Run] active={len(active_codes)} | all={len(all_codes)}")

        # 전체 종목 과거 일봉 백필 (시작 시 1회)
        asyncio.create_task(self._backfill_daily_bars(all_codes))
        # 최근 5 영업일 수급 데이터 백필 (시작 시 1회)
        asyncio.create_task(self._backfill_supply_demand(active_codes))

        await asyncio.gather(
            self._tick_loop(active_codes),
            self._tick_db_writer(),
            self._dynamic_tick_loop(),
            self._minute_bar_loop(active_codes),
            self._supply_demand_loop(active_codes),
            self._supply_demand_eod_loop(all_codes),  # 장 마감 후 전체 종목 확정 수급
            self._daily_bar_loop(all_codes),          # 전체 종목 일봉
            self._batch_scan_loop(all_codes),          # 전체 종목 배치 탐지
            self._news_loop(active_codes),
            self.dart.run(),
            self.kind.run(),
            return_exceptions=True,
        )

    async def _on_tick(self, tick: dict) -> None:
        """공통 tick 처리: Kafka 전송 + Redis 최신가 캐시 + Pub/Sub 브로드캐스트 + DB 큐"""
        if not tick:
            return
        try:
            await self.kafka.send("tick-data", tick, key=tick.get("code", ""))
        except Exception as e:
            logger.warning(f"[Kafka] tick-data send failed: {e}")
        code = tick.get("code")
        if code:
            try:
                payload = orjson.dumps(tick)
                pipe = self.redis.pipeline()
                pipe.set(f"quote:{code}", payload, ex=1800)
                pipe.publish("channel:ticks", payload)
                await pipe.execute()
            except Exception:
                pass
        try:
            self._tick_queue.put_nowait(tick)
        except asyncio.QueueFull:
            pass

    # ── Tick 수집 (WebSocket) ────────────────────────────────
    async def _tick_loop(self, _codes: list[str]):
        """장중 + NXT 시간외 WebSocket 실시간 tick. 재연결마다 Redis active_codes 최신화."""
        while True:
            in_nxt = is_nxt_aftermarket()
            if not is_market_open() and not in_nxt:
                await asyncio.sleep(30)
                continue
            # 재연결 시 최신 active_codes 로드 (BatchScanner 갱신 반영)
            codes = await load_active_stocks(self.redis)
            if not codes:
                await asyncio.sleep(10)
                continue
            try:
                logger.info(
                    f"[WS] Subscribing {len(codes)} stocks "
                    f"({'NXT after-market' if in_nxt else 'regular session'})"
                )
                await self.ws.subscribe_tick(codes, self._on_tick, include_nxt=in_nxt)
            except Exception as e:
                logger.error(f"Tick loop error: {e}")
                await asyncio.sleep(10)

    async def _dynamic_tick_loop(self):
        """사용자가 상세 열람 중인 종목 동적 구독 (Redis watching:{code} TTL 기반)."""
        watched_tasks: dict[str, asyncio.Task] = {}

        while True:
            await asyncio.sleep(30)
            if not is_market_open() and not is_nxt_aftermarket():
                continue
            try:
                keys = await self.redis.keys("watching:*")
                wanted: set[str] = set()
                for k in keys:
                    key_str = k.decode() if isinstance(k, bytes) else k
                    code = key_str.split(":", 1)[-1]
                    if code:
                        wanted.add(code)

                active = set(await load_active_stocks(self.redis))
                current = set(watched_tasks.keys())
                new_codes = wanted - active - current
                expired = current - wanted

                for code in list(expired):
                    task = watched_tasks.pop(code)
                    if not task.done():
                        task.cancel()
                    logger.info(f"[Watch] Unsubscribed {code}")

                for code in new_codes:
                    task = asyncio.create_task(
                        self.ws._ws_loop([code], self._on_tick)
                    )
                    watched_tasks[code] = task
                    logger.info(f"[Watch] Subscribed {code}")

            except Exception as e:
                logger.error(f"[Watch] loop error: {e}")

    async def _tick_db_writer(self):
        """큐에서 tick을 일괄 DB 저장"""
        while True:
            await asyncio.sleep(TICK_FLUSH_SEC)
            if self._tick_queue.empty():
                continue
            batch: list[dict] = []
            while not self._tick_queue.empty() and len(batch) < 2000:
                try:
                    batch.append(self._tick_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            if batch:
                await write_tick(self.db, batch)
                logger.debug(f"Flushed {len(batch)} ticks to DB")

    # ── 분봉 수집 (REST, 60s) ────────────────────────────────
    async def _minute_bar_loop(self, codes: list[str]):
        while True:
            if not is_market_open():
                await asyncio.sleep(60)
                continue
            today = datetime.now(_KST).strftime("%Y%m%d")
            for code in codes:
                try:
                    bars = await self.rest.get_minute_bars(code)
                    # API는 최신순(내림차순) 반환 → 오늘 날짜 bars만 필터 후 최근 5개
                    today_bars = [b for b in bars if b.get("time", "")[:8] == today]
                    recent = today_bars[:5] if today_bars else bars[:5]
                    if recent:
                        await self.kafka.send(
                            "minute-bar",
                            {"code": code, "bars": recent},
                            key=code,
                        )
                        await write_minute_bars(self.db, code, recent)
                except Exception as e:
                    logger.error(f"MinBar {code}: {e}")
                await asyncio.sleep(0.15)
            await asyncio.sleep(MINUTE_INTERVAL)

    # ── Watching 종목 즉시 스캔 (10초 주기) ───────────────────
    async def _watching_scan_loop(self):
        """사용자가 열람 중인 종목(watching:*) 10초마다 즉시 스캔 → quote 캐시 갱신."""
        while True:
            await asyncio.sleep(10)
            if not is_market_open():
                continue
            try:
                keys = await self.redis.keys("watching:*")
                for k in keys:
                    code = (k.decode() if isinstance(k, bytes) else k).split(":", 1)[-1]
                    if not code:
                        continue
                    snap = await self.rest.get_current_price(code)
                    if snap and snap.get("price"):
                        snap["source"] = "intraday"
                        await self.redis.set(f"quote:{code}", orjson.dumps(snap), ex=1800)
                    await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"[WatchScan] {e}")

    # ── 전 종목 인트라데이 REST 스캔 ─────────────────────────
    async def _intraday_rest_scan_loop(self, all_codes: list[str]):
        """전 종목 장중 현재가 REST 폴링 → 신고가·거래량급증 탐지.

        사이클 시간: len(all_codes) × INTRADAY_REQ_INTERVAL
          2,000종목 × 0.09s ≈ 180s (3분) / 4,000종목 ≈ 360s (6분)
        KIS TPS: minute_bar(~7/s) + intraday(~11/s) = ~18/s  (한도 20/s)
        """
        _scan_count   = 0
        _signal_count = 0
        _cycle_count  = 0
        _last_log     = datetime.now()

        while True:
            if not is_market_open():
                await asyncio.sleep(60)
                continue

            # active_codes 우선 순위, 나머지 후순
            active_set = set(await load_active_stocks(self.redis))
            ordered = (
                [c for c in all_codes if c in active_set]
                + [c for c in all_codes if c not in active_set]
            )

            cycle_start = asyncio.get_event_loop().time()
            now_kst     = datetime.now(_KST)
            # 장 중 경과 시간 비율 (0~1) → 거래량 정규화용
            elapsed_min = (now_kst.hour * 60 + now_kst.minute) - 9 * 60
            elapsed_pct = max(0.05, min(1.0, elapsed_min / 390))

            for code in ordered:
                if not is_market_open():
                    break
                try:
                    snap = await self.rest.get_current_price(code)
                    if not snap or not snap.get("price"):
                        await asyncio.sleep(INTRADAY_REQ_INTERVAL)
                        continue

                    _scan_count += 1
                    price  = snap["price"]
                    volume = snap.get("volume", 0)
                    amount = snap.get("amount", 0)
                    cr     = snap.get("change_rate", 0.0)

                    # ── 1. tick-data 발행 → 기존 BreakoutDetector 동작 ──
                    await self.kafka.send(
                        "tick-data",
                        {"code": code, "price": price, "change_rate": cr,
                         "volume": volume, "cum_amount": amount},
                        key=code,
                    )
                    # Redis 최신가 캐시 (30분 TTL — 스캔 사이클 6분을 여러 번 커버)
                    snap["source"] = "intraday"
                    await self.redis.set(f"quote:{code}",
                                         orjson.dumps(snap), ex=1800)

                    # ── 2. 인트라데이 거래량·거래대금 급증 탐지 ─────
                    if amount >= INTRADAY_MIN_AMOUNT:
                        avg_v_raw = await self.redis.get(f"stats:{code}:avg_vol_20d")
                        avg_a_raw = await self.redis.get(f"stats:{code}:avg_amount_20d")

                        if avg_v_raw:
                            avg_v    = float(avg_v_raw)
                            exp_vol  = avg_v * elapsed_pct
                            if exp_vol > 0 and volume / exp_vol >= INTRADAY_VOL_RATIO:
                                ratio = volume / exp_vol
                                score = min(0.95, 0.50 + (ratio - INTRADAY_VOL_RATIO)
                                            / (INTRADAY_VOL_RATIO * 4))
                                await self.kafka.send("feature-detected", {
                                    "code": code, "event_type": "VOLUME_SURGE",
                                    "price": price, "change_rate": cr,
                                    "volume": volume, "volume_ratio": round(ratio, 2),
                                    "amount": amount, "signal_score": round(score, 3),
                                    "signal_data": {
                                        "avg_vol_20d": round(avg_v),
                                        "elapsed_pct": round(elapsed_pct, 3),
                                        "ratio": round(ratio, 2),
                                        "source": "intraday_rest",
                                    },
                                }, key=code)
                                _signal_count += 1

                        if avg_a_raw:
                            avg_a    = float(avg_a_raw)
                            exp_amt  = avg_a * elapsed_pct
                            if exp_amt > 0 and amount / exp_amt >= INTRADAY_AMT_RATIO:
                                ratio = amount / exp_amt
                                score = min(0.90, 0.45 + (ratio - INTRADAY_AMT_RATIO)
                                            / (INTRADAY_AMT_RATIO * 4))
                                await self.kafka.send("feature-detected", {
                                    "code": code, "event_type": "AMOUNT_SURGE",
                                    "price": price, "change_rate": cr,
                                    "volume": volume, "amount": amount,
                                    "volume_ratio": round(ratio, 2),
                                    "signal_score": round(score, 3),
                                    "signal_data": {
                                        "avg_amount_20d": round(avg_a),
                                        "elapsed_pct": round(elapsed_pct, 3),
                                        "ratio": round(ratio, 2),
                                        "source": "intraday_rest",
                                    },
                                }, key=code)
                                _signal_count += 1

                except Exception as e:
                    logger.debug(f"[IntradayScan] {code}: {e}")

                await asyncio.sleep(INTRADAY_REQ_INTERVAL)

            elapsed   = asyncio.get_event_loop().time() - cycle_start
            _cycle_count += 1
            now = datetime.now()
            if (now - _last_log).total_seconds() >= 300:
                rps = _scan_count / max((now - _last_log).total_seconds(), 1)
                logger.info(
                    f"[IntradayScan] cycles={_cycle_count} "
                    f"last_cycle={elapsed:.1f}s scanned={_scan_count} "
                    f"signals={_signal_count} rps={rps:.1f}"
                )
                _scan_count = _signal_count = _cycle_count = 0
                _last_log = now

            await asyncio.sleep(max(0, 5 - elapsed % 5))

    # ── 수급 수집 (REST, 30분, 장중) ────────────────────────
    async def _supply_demand_loop(self, codes: list[str]):
        while True:
            if not is_market_open():
                await asyncio.sleep(300)
                continue
            today = datetime.now().strftime("%Y%m%d")
            success, empty, fail = 0, 0, 0
            for code in codes:
                try:
                    sd = await self.rest.get_supply_demand(code, today)
                    if sd:
                        await self.kafka.send("supply-demand", sd, key=code)
                        await write_supply_demand(self.db, sd)
                        success += 1
                    else:
                        empty += 1
                except Exception as e:
                    logger.warning(f"[SD] {code}: {e}")
                    fail += 1
                await asyncio.sleep(0.2)
            logger.info(f"[SD] Cycle done: success={success}, empty={empty}, error={fail}")
            await asyncio.sleep(SUPPLY_INTERVAL)

    # ── 수급 수집 (EOD, 장 마감 후 전체 종목) ───────────────
    async def _supply_demand_eod_loop(self, all_codes: list[str]):
        """장 마감 후 전체 종목 확정 수급 1회 수집 (active_codes 외 종목 포함)."""
        last_run_date: str = ""
        while True:
            await asyncio.sleep(60)
            if not is_after_close():
                continue
            today = datetime.now(_KST).strftime("%Y%m%d")
            if last_run_date == today:
                continue
            # 일봉 수집 완료 후 실행 (최대 1시간 대기)
            try:
                await asyncio.wait_for(asyncio.shield(self._daily_bars_done.wait()), timeout=3600)
            except asyncio.TimeoutError:
                logger.warning("[SD-EOD] Timed out waiting for daily bars — proceeding anyway")

            last_run_date = today
            logger.info(f"[SD-EOD] Starting EOD supply_demand for {len(all_codes)} stocks")
            success, empty, fail = 0, 0, 0
            for code in all_codes:
                try:
                    sd = await self.rest.get_supply_demand(code, today)
                    if sd:
                        await write_supply_demand(self.db, sd)
                        success += 1
                    else:
                        empty += 1
                except Exception as e:
                    logger.warning(f"[SD-EOD] {code}: {e}")
                    fail += 1
                await asyncio.sleep(0.3)
            logger.info(f"[SD-EOD] Done: success={success}, empty={empty}, error={fail}")

    # ── 일봉 수집 (장 마감 후 1회, 전체 종목) ──────────────
    async def _daily_bar_loop(self, codes: list[str]):
        last_run_date: str = ""
        while True:
            await asyncio.sleep(60)
            today = datetime.now(_KST).strftime("%Y%m%d")
            if not is_after_close() or last_run_date == today:
                continue

            logger.info(f"[DailyBar] Starting daily bar collection for {len(codes)} stocks")
            total = 0
            start = (datetime.now() - timedelta(days=5)).strftime("%Y%m%d")

            for code in codes:
                try:
                    bars = await self.rest.get_daily_bars(code, start, today)
                    n = await write_daily_bars(self.db, bars)
                    total += n
                except Exception as e:
                    logger.error(f"DailyBar {code}: {e}")
                await asyncio.sleep(0.3)

            logger.info(f"[DailyBar] Written {total} rows for {len(codes)} stocks")

            # KOSPI/KOSDAQ 지수 일봉 수집
            for mkt_code in ["0001", "1001"]:
                try:
                    idx_bars = await self.rest.get_index_bars(mkt_code, start, today)
                    if idx_bars:
                        n = await write_daily_bars(self.db, idx_bars)
                        logger.info(f"[DailyBar] Index {mkt_code}: {n} rows")
                except Exception as e:
                    logger.error(f"[DailyBar] Index {mkt_code}: {e}")

            last_run_date = today

            # Redis 통계 갱신 후 배치 탐지에 신호
            await self._update_redis_stats(codes)
            self._daily_bars_done.set()
            logger.info("[DailyBar] stats updated — batch scan signal sent")

    async def _backfill_supply_demand(self, codes: list[str]):
        """시작 시 최근 5 영업일 수급 데이터 백필 (누락된 날짜만 대상)."""
        await asyncio.sleep(30)
        from datetime import date as date_cls
        today = datetime.now(_KST).date()
        # 최근 10 달력일에서 평일만 추출 → 최대 5 영업일
        biz_days: list[str] = []
        for offset in range(1, 11):
            d = today - timedelta(days=offset)
            if d.weekday() < 5:
                biz_days.append(d.strftime("%Y%m%d"))
            if len(biz_days) >= 5:
                break

        try:
            async with self.db.acquire() as conn:
                existing = await conn.fetch(
                    "SELECT DISTINCT code, date::text AS date FROM supply_demand "
                    "WHERE code = ANY($1::text[]) AND date >= $2",
                    codes, today - timedelta(days=10),
                )
            existing_set = {(r["code"], r["date"][:10].replace("-", "")) for r in existing}
        except Exception as e:
            logger.error(f"[SD-Backfill] check error: {e}")
            return

        missing = [(c, d) for c in codes for d in biz_days if (c, d) not in existing_set]
        if not missing:
            logger.info("[SD-Backfill] All recent supply_demand data present")
            return

        logger.info(f"[SD-Backfill] Backfilling {len(missing)} (code, date) combinations")
        success, empty, fail = 0, 0, 0
        for code, date_str in missing:
            try:
                sd = await self.rest.get_supply_demand(code, date_str)
                if sd:
                    await write_supply_demand(self.db, sd)
                    success += 1
                else:
                    empty += 1
            except Exception as e:
                logger.debug(f"[SD-Backfill] {code}/{date_str}: {e}")
                fail += 1
            await asyncio.sleep(0.3)

        logger.info(f"[SD-Backfill] Done: success={success}, empty={empty}, error={fail}")

    async def _backfill_daily_bars(self, codes: list[str]):
        """시작 시 과거 {BACKFILL_DAYS}일 일봉 백필.
        daily_bars 데이터가 없는 종목만 대상으로 함.
        """
        await asyncio.sleep(15)

        try:
            async with self.db.acquire() as conn:
                covered_rows = await conn.fetch(
                    "SELECT DISTINCT code FROM daily_bars WHERE code = ANY($1::varchar[])",
                    codes,
                )
            covered_set = {r["code"] for r in covered_rows}
            to_backfill = [c for c in codes if c not in covered_set]
        except Exception as e:
            logger.error(f"[Backfill] count check error: {e}")
            return

        if not to_backfill:
            logger.info(f"[Backfill] Skipped — all {len(codes)} stocks already have data")
            await self._update_redis_stats(codes)
            return

        logger.info(
            f"[Backfill] Starting {BACKFILL_DAYS}-day backfill for "
            f"{len(to_backfill)}/{len(codes)} stocks without data"
        )
        end   = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=BACKFILL_DAYS)).strftime("%Y%m%d")
        total = 0

        for i, code in enumerate(to_backfill):
            try:
                bars = await self.rest.get_daily_bars(code, start, end)
                n = await write_daily_bars(self.db, bars)
                total += n
            except Exception as e:
                logger.error(f"[Backfill] {code}: {e}")
            await asyncio.sleep(0.5)
            if (i + 1) % 100 == 0:
                logger.info(f"[Backfill] Progress {i+1}/{len(to_backfill)}, {total} rows so far")

        logger.info(f"[Backfill] Complete — {total} rows for {len(to_backfill)} stocks")

        # KOSPI/KOSDAQ 지수 백필
        for mkt_code in ["0001", "1001"]:
            try:
                idx_rows = await self.db.fetch(
                    "SELECT COUNT(*) AS cnt FROM daily_bars WHERE code=$1", mkt_code
                )
                if idx_rows and idx_rows[0]["cnt"] > 0:
                    logger.info(f"[Backfill] Index {mkt_code} already has data, skipping")
                    continue
                idx_bars = await self.rest.get_index_bars(mkt_code, start, end)
                if idx_bars:
                    n = await write_daily_bars(self.db, idx_bars)
                    logger.info(f"[Backfill] Index {mkt_code}: {n} rows")
            except Exception as e:
                logger.error(f"[Backfill] Index {mkt_code}: {e}")

        await self._update_redis_stats(codes)

    # ── 배치 탐지 루프 (전체 종목, 장 마감 후 1회) ───────────
    async def _batch_scan_loop(self, all_codes: list[str]):
        """_daily_bar_loop 완료 신호(_daily_bars_done)를 받으면 전체 종목 배치 탐지."""
        last_run_date: str = ""
        scanner = BatchScanner(self.db, self.redis, self.kafka)

        while True:
            # 일봉+stats 완료 대기 (최대 2시간 타임아웃)
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._daily_bars_done.wait()),
                    timeout=7200,
                )
            except asyncio.TimeoutError:
                await asyncio.sleep(60)
                continue

            today = datetime.now(_KST).strftime("%Y%m%d")
            if last_run_date == today:
                # 이미 오늘 실행됨 — 다음 이벤트 대기
                self._daily_bars_done.clear()
                await asyncio.sleep(60)
                continue

            self._daily_bars_done.clear()
            last_run_date = today

            try:
                events = await scanner.run(all_codes)
                logger.info(f"[BatchScan] Completed — {len(events)} signals")
            except Exception as e:
                logger.error(f"[BatchScan] Error: {e}")

            # result_5d 자동 백필 (7일+ 경과 이벤트)
            try:
                n = await self._backfill_result_5d()
                if n:
                    logger.info(f"[Result5d] Backfilled {n} events")
            except Exception as e:
                logger.error(f"[Result5d] Error: {e}")

            # ML 재학습 플래그 설정 (월요일 + 500개+ 레이블)
            await self._maybe_trigger_ml_retrain()

    # ── result_5d 자동 백필 ───────────────────────────────────
    async def _backfill_result_5d(self) -> int:
        """7일+ 경과 feature_events의 result_1d/3d/5d를 daily_bars 기준으로 계산."""
        try:
            async with self.db.acquire() as conn:
                status = await conn.execute(
                    """
                    WITH events AS (
                        SELECT id, code, price AS entry_price, detected_at::date AS det_date
                        FROM feature_events
                        WHERE result_5d IS NULL
                          AND detected_at < NOW() - INTERVAL '7 days'
                        LIMIT 500
                    ),
                    fwd AS (
                        SELECT
                            e.id,
                            e.entry_price,
                            (SELECT close FROM daily_bars WHERE code = e.code
                             AND date > e.det_date ORDER BY date LIMIT 1 OFFSET 0) AS c1,
                            (SELECT close FROM daily_bars WHERE code = e.code
                             AND date > e.det_date ORDER BY date LIMIT 1 OFFSET 2) AS c3,
                            (SELECT close FROM daily_bars WHERE code = e.code
                             AND date > e.det_date ORDER BY date LIMIT 1 OFFSET 4) AS c5
                        FROM events e
                    )
                    UPDATE feature_events fe
                    SET
                        result_1d = CASE WHEN fwd.entry_price > 0 AND fwd.c1 IS NOT NULL
                                         THEN (fwd.c1 - fwd.entry_price) / fwd.entry_price END,
                        result_3d = CASE WHEN fwd.entry_price > 0 AND fwd.c3 IS NOT NULL
                                         THEN (fwd.c3 - fwd.entry_price) / fwd.entry_price END,
                        result_5d = CASE WHEN fwd.entry_price > 0 AND fwd.c5 IS NOT NULL
                                         THEN (fwd.c5 - fwd.entry_price) / fwd.entry_price END
                    FROM fwd
                    WHERE fe.id = fwd.id
                      AND fwd.c5 IS NOT NULL
                    """
                )
            # status = "UPDATE N"
            return int(status.split()[-1])
        except Exception as e:
            logger.error(f"[Result5d] Backfill query error: {e}")
            return 0

    # ── ML 재학습 트리거 ──────────────────────────────────────
    async def _maybe_trigger_ml_retrain(self) -> None:
        """레이블 이벤트 500개+ 이고 월요일이면 Redis에 ml:retrain_needed 플래그 설정."""
        try:
            today_str = datetime.now(_KST).strftime("%Y%m%d")
            last = await self.redis.get("ml:last_retrain_date")
            if last and (last.decode() if isinstance(last, bytes) else last) == today_str:
                return
            if datetime.now(_KST).weekday() != 0:  # 월요일(0)만
                return
            async with self.db.acquire() as conn:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM feature_events WHERE result_5d IS NOT NULL"
                )
            if count and count >= 500:
                await self.redis.set("ml:retrain_needed", "1", ex=604_800)   # 7일
                await self.redis.set("ml:last_retrain_date", today_str, ex=172_800)  # 2일
                logger.info(
                    f"[ML] Retrain flag set (ml:retrain_needed=1) — {count} labeled events"
                )
        except Exception as e:
            logger.error(f"[ML] Retrain trigger error: {e}")

    # ── Redis 통계 갱신 ──────────────────────────────────────
    async def _update_redis_stats(self, codes: list[str]):
        logger.info(f"[Stats] Updating Redis stats for {len(codes)} stocks")
        updated = 0
        pipe_size = 50

        for i in range(0, len(codes), pipe_size):
            chunk = codes[i:i + pipe_size]
            await asyncio.gather(*[self._update_one_stat(c) for c in chunk])
            updated += len(chunk)

        logger.info(f"[Stats] Done — {updated} stocks updated")

    async def _update_one_stat(self, code: str):
        try:
            async with self.db.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT date, close, volume, amount, foreign_net_buy, inst_net_buy, short_sell_vol
                    FROM daily_bars
                    WHERE code = $1
                    ORDER BY date DESC
                    LIMIT 260
                    """,
                    code,
                )
            if not rows:
                return

            closes  = [r["close"]  for r in rows]
            volumes = [r["volume"] for r in rows]
            amounts = [r["amount"] or 0 for r in rows]
            ex      = 90_000   # 25시간 TTL

            pipe = self.redis.pipeline()

            # 거래량 이동평균
            for n in [5, 20, 60]:
                if len(volumes) >= n:
                    pipe.set(f"stats:{code}:avg_vol_{n}d", sum(volumes[:n]) / n, ex=ex)

            # 거래대금 20일 평균
            if len(amounts) >= 20:
                pipe.set(f"stats:{code}:avg_amount_20d", sum(amounts[:20]) / 20, ex=ex)

            # 기간별 고가 (신고가 돌파 기준 — 오늘 종가 제외, 직전 N거래일 고가)
            for days, label in [(20, "20d"), (65, "13w"), (130, "26w"), (260, "52w")]:
                if len(closes) > days:
                    pipe.set(f"stats:{code}:high_{days}d", max(closes[1:days+1]), ex=ex)

            # 수급 평균
            for field, col in [("foreign", "foreign_net_buy"), ("inst", "inst_net_buy")]:
                nets = [r[col] or 0 for r in rows[:20]]
                if nets:
                    pipe.set(f"stats:{code}:avg_{field}_20d", sum(nets) / len(nets), ex=ex)

            # 공매도 추세
            shorts = [r["short_sell_vol"] or 0 for r in rows[:10]]
            if len(shorts) >= 6:
                recent = sum(shorts[:3]) / 3
                older  = sum(shorts[3:6]) / 3 + 1
                pipe.set(f"stats:{code}:short_increasing", int(recent > older), ex=ex)

            await pipe.execute()

        except Exception as e:
            logger.debug(f"[Stats] {code}: {e}")


    # ── 뉴스 수집 (30분 간격) ────────────────────────────────
    async def _news_loop(self, codes: list[str]):
        """종목별 뉴스를 수집해 Kafka 'news' 토픽으로 전송"""
        # 종목명 조회 (Redis 또는 DB)
        stock_names: dict[str, str] = {}
        try:
            async with self.db.acquire() as conn:
                rows = await conn.fetch("SELECT code, name FROM stocks WHERE code = ANY($1::text[])", codes)
                stock_names = {r["code"]: r["name"] for r in rows}
        except Exception as e:
            logger.warning(f"[News] stock name load error: {e}")

        seen: set[str] = set()   # 중복 URL 방지 (프로세스 내)

        while True:
            await asyncio.sleep(NEWS_INTERVAL)
            collected = 0
            for code in codes:
                name = stock_names.get(code, code)
                try:
                    items = await self.news.crawl_stock_news(code, name)
                    for item in items:
                        url = item.get("url", "")
                        if url in seen:
                            continue
                        seen.add(url)
                        await self.kafka.send("news", item, key=code)
                        collected += 1
                except Exception as e:
                    logger.debug(f"[News] {code}: {e}")
                await asyncio.sleep(0.5)   # rate limit

            if collected:
                logger.info(f"[News] Collected {collected} news items")

            # seen 집합 크기 제한 (메모리 누수 방지)
            if len(seen) > 5000:
                seen.clear()


if __name__ == "__main__":
    service = os.environ.get("SERVICE_NAME", "collector")
    svc = StockCollector()
    if service == "collector-tick":
        asyncio.run(svc.run_tick_only())
    else:
        asyncio.run(svc.run())
