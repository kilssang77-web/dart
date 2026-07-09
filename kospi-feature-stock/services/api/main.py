from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter, Gauge
import asyncpg
import redis.asyncio as redis_lib
import orjson
import os
import logging
from datetime import datetime, timezone, timedelta, time as _time

# 비즈니스 메트릭
FEATURE_EVENTS_TOTAL  = Counter("fstock_feature_events_total",  "특징주 탐지 누적수")
RECOMMEND_TOTAL       = Counter("fstock_recommendations_total", "추천 신호 누적수")
WS_CONNECTIONS        = Gauge("fstock_ws_connections",           "WebSocket 현재 연결 수")

_KST = timezone(timedelta(hours=9))


def _is_market_open() -> bool:
    now = datetime.now(_KST)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return _time(9, 0) <= t <= _time(15, 35)

from routers import stocks, features, recommendations, disclosures, backtest, themes, market, disclosure_filters, ml, news, watchlist, settings, notifications, tracking, admin, ranking, screener, trader
from middleware.auth import APIKeyMiddleware
from perf_tracker import tracker_loop

logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    dsn = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    app.state.db = await asyncpg.create_pool(
        dsn=dsn, min_size=10, max_size=50,
        command_timeout=20,
    )
    app.state.redis = redis_lib.from_url(
        os.environ["REDIS_URL"], decode_responses=False
    )
    # 성능 인덱스 — 누락 인덱스 보강 (idempotent)
    for _idx in [
        "CREATE INDEX IF NOT EXISTS idx_rec_perf_rec_id      ON recommendation_performance(rec_id)",
        "CREATE INDEX IF NOT EXISTS idx_rec_perf_signal_time ON recommendation_performance(signal_time DESC)",
        "CREATE INDEX IF NOT EXISTS idx_rec_perf_tracking    ON recommendation_performance(tracking_complete, signal_time DESC)",
        "CREATE INDEX IF NOT EXISTS idx_nsl_code             ON news_stock_links(code, news_id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_rec_feat_event_id    ON recommendations(feature_event_id)",
        "CREATE INDEX IF NOT EXISTS idx_rec_created_at       ON recommendations(created_at DESC)",
    ]:
        try:
            await app.state.db.execute(_idx)
        except Exception:
            pass

    # 스키마 확장 마이그레이션 (idempotent)
    for _alter in [
        "ALTER TABLE disclosures ADD COLUMN IF NOT EXISTS contract_amount BIGINT",
        """CREATE TABLE IF NOT EXISTS theme_snapshots (
            id             BIGSERIAL PRIMARY KEY,
            theme_name     VARCHAR(100) NOT NULL,
            snap_date      DATE NOT NULL,
            stock_count    INT  NOT NULL DEFAULT 0,
            avg_return     NUMERIC(8,4),
            top_codes      TEXT,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(theme_name, snap_date)
        )""",
        "ALTER TABLE theme_snapshots ADD COLUMN IF NOT EXISTS momentum_score NUMERIC(6,3)",
        "ALTER TABLE theme_snapshots ADD COLUMN IF NOT EXISTS velocity INT",
        "ALTER TABLE theme_snapshots ADD COLUMN IF NOT EXISTS lead_codes TEXT",
        "CREATE INDEX IF NOT EXISTS idx_theme_snapshots_name_date ON theme_snapshots(theme_name, snap_date DESC)",
    ]:
        try:
            await app.state.db.execute(_alter)
        except Exception:
            pass

    # recommendation_performance / telegram_logs 자동 생성 (이미 존재하면 skip)
    for _sql in [
        """CREATE TABLE IF NOT EXISTS backtest_results (
            id           BIGSERIAL PRIMARY KEY,
            name         VARCHAR(200) NOT NULL,
            params       TEXT,
            result       TEXT,
            equity_curve TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS recommendation_performance (
            id BIGSERIAL PRIMARY KEY, rec_id BIGINT NOT NULL, code VARCHAR(10) NOT NULL,
            entry_price NUMERIC NOT NULL, event_type VARCHAR(50), signal_time TIMESTAMPTZ NOT NULL,
            r_1h NUMERIC, t_1h TIMESTAMPTZ, r_3h NUMERIC, t_3h TIMESTAMPTZ,
            r_5h NUMERIC, t_5h TIMESTAMPTZ, r_1d NUMERIC, t_1d TIMESTAMPTZ,
            r_2d NUMERIC, t_2d TIMESTAMPTZ, r_3d NUMERIC, t_3d TIMESTAMPTZ,
            r_4d NUMERIC, t_4d TIMESTAMPTZ, r_5d NUMERIC, t_5d TIMESTAMPTZ,
            r_7d NUMERIC, t_7d TIMESTAMPTZ, r_10d NUMERIC, t_10d TIMESTAMPTZ,
            r_special NUMERIC, t_special TIMESTAMPTZ, special_type VARCHAR(30), special_date DATE,
            is_success BOOLEAN, max_return NUMERIC, hit_target BOOLEAN DEFAULT FALSE,
            hit_stop BOOLEAN DEFAULT FALSE, tracking_complete BOOLEAN DEFAULT FALSE,
            last_updated TIMESTAMPTZ DEFAULT NOW(), created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(rec_id)
        )""",
        """CREATE TABLE IF NOT EXISTS telegram_logs (
            id BIGSERIAL PRIMARY KEY, msg_type VARCHAR(20) NOT NULL,
            code VARCHAR(10), name VARCHAR(100), title TEXT NOT NULL DEFAULT '',
            message TEXT NOT NULL, success BOOLEAN NOT NULL DEFAULT TRUE,
            error_msg TEXT, sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""",
    ]:
        try:
            await app.state.db.execute(_sql)
        except asyncpg.exceptions.UniqueViolationError:
            pass
    # is_success 즉시 백필: r_5d 확보된 미판정 레코드
    try:
        await app.state.db.execute("""
            UPDATE recommendation_performance
            SET is_success = (r_5d > 0),
                last_updated = NOW()
            WHERE r_5d IS NOT NULL AND is_success IS NULL
        """)
        await app.state.db.execute("""
            UPDATE recommendations r
            SET is_success = rp.is_success
            FROM recommendation_performance rp
            WHERE rp.rec_id = r.id AND rp.is_success IS NOT NULL AND r.is_success IS NULL
        """)
    except Exception as e:
        logger.warning(f"is_success backfill error: {e}")

    # backfill_history 테이블 자동 생성 (idempotent)
    for _bfsql in [
        """CREATE TABLE IF NOT EXISTS backfill_history (
            id            BIGSERIAL PRIMARY KEY,
            job_type      VARCHAR(50)  NOT NULL,
            triggered_by  VARCHAR(20)  NOT NULL DEFAULT 'auto',
            status        VARCHAR(20)  NOT NULL DEFAULT 'running',
            target_count  INT,
            success_count INT,
            skip_count    INT,
            fail_count    INT,
            rows_added    BIGINT,
            started_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            finished_at   TIMESTAMPTZ,
            error_msg     TEXT,
            meta          JSONB
        )""",
        """CREATE INDEX IF NOT EXISTS idx_backfill_history_type_started
            ON backfill_history(job_type, started_at DESC)""",
    ]:
        try:
            await app.state.db.execute(_bfsql)
        except Exception:
            pass

    # Materialized View 자동 새로고침 (1시간 주기)
    async def _refresh_mv_loop():
        import asyncio as _asyncio
        while True:
            try:
                await app.state.db.execute(
                    "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_rec_stats"
                )
            except Exception as _e:
                logger.warning(f"MV refresh failed: {_e}")
            await _asyncio.sleep(3600)

    # 성과 추적 워커 시작
    import asyncio
    _tracker_task  = asyncio.create_task(tracker_loop(app.state.db, app.state.redis))
    _mv_task       = asyncio.create_task(_refresh_mv_loop())
    logger.info("API server started")
    yield
    _tracker_task.cancel()
    _mv_task.cancel()
    await app.state.db.close()
    await app.state.redis.close()
    logger.info("API server stopped")


app = FastAPI(
    title="Feature Stock Detection API",
    description="KOSPI/KOSDAQ 실시간 특징주 탐지 및 매매 추천 시스템",
    version="1.0.0",
    lifespan=lifespan,
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

_CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-API-Key"],
)
app.add_middleware(APIKeyMiddleware)

app.include_router(stocks.router,          prefix="/api/v1/stocks",          tags=["stocks"])
app.include_router(features.router,        prefix="/api/v1/features",        tags=["features"])
app.include_router(recommendations.router, prefix="/api/v1/recommendations", tags=["recommendations"])
app.include_router(disclosures.router,     prefix="/api/v1/disclosures",     tags=["disclosures"])
app.include_router(backtest.router,        prefix="/api/v1/backtest",        tags=["backtest"])
app.include_router(themes.router,          prefix="/api/v1/themes",           tags=["themes"])
app.include_router(market.router,              prefix="/api/v1/market",            tags=["market"])
app.include_router(disclosure_filters.router, prefix="/api/v1/disclosure-filters", tags=["disclosure-filters"])
app.include_router(ml.router,               prefix="/api/v1/ml",                tags=["ml"])
app.include_router(news.router,             prefix="/api/v1/news",              tags=["news"])
app.include_router(watchlist.router,         prefix="/api/v1/watchlist",          tags=["watchlist"])
app.include_router(settings.router,         prefix="/api/v1/settings",          tags=["settings"])
app.include_router(notifications.router,  prefix="/api/v1/notifications",     tags=["notifications"])
app.include_router(tracking.router,       prefix="/api/v1/tracking",          tags=["tracking"])
app.include_router(admin.router,          prefix="/api/v1",                   tags=["admin"])
app.include_router(ranking.router,        prefix="/api/v1/ranking",           tags=["ranking"])
app.include_router(screener.router,       prefix="/api/v1/screener",          tags=["screener"])
app.include_router(trader.router,         prefix="/api/v1/trader",            tags=["trader"])

class NoCacheStaticFiles(StaticFiles):
    """Vite 빌드 자산 — 브라우저 heuristic 캐시 방지. 항상 서버에서 재검증."""
    async def get_response(self, path: str, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        return resp

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/assets", NoCacheStaticFiles(directory="static/assets"), name="assets")


@app.get("/favicon.svg", include_in_schema=False)
async def favicon():
    import os
    p = "static/favicon.svg"
    return FileResponse(p) if os.path.exists(p) else FileResponse("static/index.html")


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse("static/index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/health")
async def health(request: Request):
    results = {}
    try:
        async with request.app.state.db.acquire() as c:
            await c.fetchval("SELECT 1")
        results["postgres"] = "ok"
    except Exception as e:
        results["postgres"] = f"error: {e}"

    try:
        await request.app.state.redis.ping()
        results["redis"] = "ok"
    except Exception as e:
        results["redis"] = f"error: {e}"

    status = "ok" if all(v == "ok" for v in results.values()) else "degraded"
    return {"status": status, "components": results}


@app.get("/metrics")
async def metrics(request: Request):
    db    = request.app.state.db
    redis = request.app.state.redis

    today_feat = await db.fetchval(
        "SELECT COUNT(*) FROM feature_events WHERE detected_at >= NOW()-INTERVAL '24h'"
    )
    today_rec  = await db.fetchval(
        "SELECT COUNT(*) FROM recommendations WHERE created_at >= NOW()-INTERVAL '24h'"
    )
    buy_rec = await db.fetchval(
        "SELECT COUNT(*) FROM recommendations WHERE created_at >= NOW()-INTERVAL '24h' AND action='BUY'"
    )
    lag = await redis.get("stats:pipeline_lag_ms")

    return {
        "features_24h":      today_feat,
        "recommendations_24h": today_rec,
        "buy_signals_24h":   buy_rec,
        "pipeline_lag_ms":  float(lag or 0),
    }
@app.websocket("/ws/ticks")
async def ws_ticks(websocket: WebSocket):
    """실시간 체결 tick 스트림 — HTS 시세판용."""
    await websocket.accept()

    # Build stock name cache once per connection
    name_cache: dict[str, str] = {}
    try:
        async with websocket.app.state.db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT code, name FROM stocks WHERE market IN ('KOSPI', 'KOSDAQ')"
            )
            name_cache = {r["code"]: r["name"] for r in rows}
    except Exception as e:
        logger.debug(f"WS ticks: name cache error: {e}")

    # 1) 장 상태 메시지 즉시 전송
    market_open = _is_market_open()
    try:
        await websocket.send_bytes(orjson.dumps({
            "type": "market_status",
            "is_open": market_open,
            "ts": datetime.now(_KST).isoformat(),
        }))
    except Exception:
        pass

    # 2) 장 마감 시: daily_bars 최근 종가 스냅샷 전송 (상위 30 종목, 거래대금 기준)
    if not market_open:
        try:
            async with websocket.app.state.db.acquire() as conn:
                snap_rows = await conn.fetch(
                    """
                    WITH latest AS (
                        SELECT DISTINCT ON (db.code)
                            db.code, db.date::TEXT AS snap_date,
                            db.close, db.open, db.high, db.low,
                            db.volume, db.amount,
                            COALESCE(db.change_rate, 0.0)::float AS change_rate
                        FROM daily_bars db
                        JOIN stocks s ON s.code = db.code
                            AND s.market IN ('KOSPI', 'KOSDAQ')
                            AND s.is_active = TRUE
                        WHERE db.close > 0
                        ORDER BY db.code, db.date DESC
                    )
                    SELECT * FROM latest
                    ORDER BY amount DESC
                    LIMIT 30
                    """
                )
            for row in snap_rows:
                code  = row["code"]
                price = int(row["close"])
                cr    = float(row["change_rate"])
                # prev_close = price / (1 + cr/100), rounded to int
                denom = 1 + cr / 100
                prev_close = round(price / denom) if abs(denom) > 0.0001 else price
                tick = {
                    "code":        code,
                    "name":        name_cache.get(code, code),
                    "price":       price,
                    "prev_close":  prev_close,
                    "change":      price - prev_close,
                    "change_rate": cr,
                    "volume":      int(row["volume"] or 0),
                    "amount":      int(row["amount"] or 0),
                    "high":        int(row["high"] or price),
                    "low":         int(row["low"] or price),
                    "snapshot":    True,
                    "snap_date":   row["snap_date"],
                }
                await websocket.send_bytes(orjson.dumps(tick))
        except Exception as e:
            logger.debug(f"WS ticks snapshot error: {e}")

    # 3) Pub/Sub 구독 — 장중 실시간 tick 수신
    pubsub = websocket.app.state.redis.pubsub()
    await pubsub.subscribe("channel:ticks")
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    tick = orjson.loads(message["data"])
                    code = tick.get("code", "")
                    if code and "name" not in tick and code in name_cache:
                        tick["name"] = name_cache[code]
                    await websocket.send_bytes(orjson.dumps(tick))
                except Exception:
                    await websocket.send_bytes(message["data"])
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"WS ticks disconnected: {e}")
    finally:
        await pubsub.unsubscribe()


@app.websocket("/ws/realtime")
async def ws_realtime(websocket: WebSocket):
    await websocket.accept()
    pubsub = websocket.app.state.redis.pubsub()
    await pubsub.subscribe("channel:features", "channel:recommendations")
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_bytes(message["data"])
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"WS disconnected: {e}")
    finally:
        await pubsub.unsubscribe()


@app.get("/manual.html", include_in_schema=False)
async def serve_manual():
    import os
    p = "static/manual.html"
    if os.path.exists(p):
        return FileResponse(p, headers={"Cache-Control": "no-cache, must-revalidate"})
    return FileResponse("static/index.html")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    return FileResponse("static/index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
