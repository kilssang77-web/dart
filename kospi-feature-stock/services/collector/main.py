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

# 환경변수로 주요 파라미터 설정
TICK_FLUSH_SEC   = int(os.environ.get("TICK_FLUSH_SEC", "5"))
MINUTE_INTERVAL  = int(os.environ.get("MINUTE_INTERVAL_SEC", "60"))
SUPPLY_INTERVAL  = int(os.environ.get("SUPPLY_INTERVAL_SEC", "1800"))
BACKFILL_DAYS    = int(os.environ.get("DAILY_BACKFILL_DAYS", "260"))
NEWS_INTERVAL    = int(os.environ.get("NEWS_INTERVAL_SEC", "1800"))


def is_market_open() -> bool:
    now = datetime.now(_KST)
    return now.weekday() < 5 and MARKET_OPEN <= now.time() <= MARKET_CLOSE


def is_after_close() -> bool:
    now = datetime.now(_KST)
    return now.weekday() < 5 and now.time() >= STATS_TIME


async def load_active_stocks(redis: redis_lib.Redis) -> list[str]:
    """실시간 모니터링 대상 (WebSocket·분봉): Redis 캐시 → 기본 20개 fallback."""
    import orjson
    try:
        cached = await redis.get("stocks:active_codes")
        if cached:
            codes = orjson.loads(cached)
            if codes and isinstance(codes, list):
                return codes
    except Exception:
        pass
    return [
        "005930", "000660", "035420", "005380", "051910",
        "006400", "035720", "028260", "207940", "068270",
        "323410", "105560", "055550", "086790", "032830",
        "066570", "003550", "096770", "033780", "015760",
    ]


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

    async def run(self):
        await self.setup()

        # 실시간 모니터링: Redis 캐시 or 기본 20개
        active_codes = await load_active_stocks(self.redis)

        # 전체 종목: DB에서 로드 (일봉 수집 + 배치 탐지)
        all_codes = await load_all_stocks(self.db)
        if not all_codes:
            logger.warning("[Run] stocks table empty — falling back to active_codes for all ops")
            all_codes = active_codes

        logger.info(f"[Run] active={len(active_codes)} | all={len(all_codes)}")

        # 전체 종목 과거 일봉 백필 (시작 시 1회)
        asyncio.create_task(self._backfill_daily_bars(all_codes))

        await asyncio.gather(
            self._tick_loop(active_codes),
            self._tick_db_writer(),
            self._dynamic_tick_loop(),
            self._minute_bar_loop(active_codes),
            self._supply_demand_loop(active_codes),
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
        await self.kafka.send("tick-data", tick, key=tick.get("code", ""))
        code = tick.get("code")
        if code:
            try:
                payload = orjson.dumps(tick)
                pipe = self.redis.pipeline()
                pipe.set(f"quote:{code}", payload, ex=30)
                pipe.publish("channel:ticks", payload)
                await pipe.execute()
            except Exception:
                pass
        try:
            self._tick_queue.put_nowait(tick)
        except asyncio.QueueFull:
            pass

    # ── Tick 수집 (WebSocket) ────────────────────────────────
    async def _tick_loop(self, codes: list[str]):
        while True:
            if not is_market_open() or not codes:
                await asyncio.sleep(30)
                continue
            try:
                await self.ws.subscribe_tick(codes, self._on_tick)
            except Exception as e:
                logger.error(f"Tick loop error: {e}")
                await asyncio.sleep(10)

    async def _dynamic_tick_loop(self):
        """사용자가 상세 열람 중인 종목 동적 구독 (Redis watching:{code} TTL 기반)."""
        watched_tasks: dict[str, asyncio.Task] = {}

        while True:
            await asyncio.sleep(30)
            if not is_market_open():
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
            for code in codes:
                try:
                    bars = await self.rest.get_minute_bars(code)
                    if bars:
                        await self.kafka.send(
                            "minute-bar",
                            {"code": code, "bars": bars[-5:]},
                            key=code,
                        )
                        await write_minute_bars(self.db, code, bars[-5:])
                except Exception as e:
                    logger.error(f"MinBar {code}: {e}")
                await asyncio.sleep(0.15)
            await asyncio.sleep(MINUTE_INTERVAL)

    # ── 수급 수집 (REST, 30분) ───────────────────────────────
    async def _supply_demand_loop(self, codes: list[str]):
        while True:
            if not is_market_open():
                await asyncio.sleep(300)
                continue
            today = datetime.now().strftime("%Y%m%d")
            for code in codes:
                try:
                    sd = await self.rest.get_supply_demand(code, today)
                    if sd:
                        await self.kafka.send("supply-demand", sd, key=code)
                        await write_supply_demand(self.db, sd)
                except Exception as e:
                    logger.error(f"SD {code}: {e}")
                await asyncio.sleep(0.2)
            await asyncio.sleep(SUPPLY_INTERVAL)

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
            last_run_date = today

            # Redis 통계 갱신 후 배치 탐지에 신호
            await self._update_redis_stats(codes)
            self._daily_bars_done.set()
            logger.info("[DailyBar] stats updated — batch scan signal sent")

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

            # 기간별 고가 (신고가 돌파 기준)
            for days, label in [(20, "20d"), (65, "13w"), (130, "26w"), (260, "52w")]:
                if len(closes) >= days:
                    pipe.set(f"stats:{code}:high_{days}d", max(closes[:days]), ex=ex)

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
    asyncio.run(StockCollector().run())
