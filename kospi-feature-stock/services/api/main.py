from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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

from routers import stocks, features, recommendations, disclosures, backtest, themes, market, disclosure_filters, ml, news, watchlist, settings, notifications, tracking
from perf_tracker import tracker_loop

logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    dsn = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    app.state.db = await asyncpg.create_pool(
        dsn=dsn, min_size=5, max_size=20,
        command_timeout=30,
    )
    app.state.redis = redis_lib.from_url(
        os.environ["REDIS_URL"], decode_responses=False
    )
    # 스키마 확장 마이그레이션 (idempotent)
    for _alter in [
        "ALTER TABLE disclosures ADD COLUMN IF NOT EXISTS contract_amount BIGINT",
        """CREATE TABLE IF NOT EXISTS theme_snapshots (
            id          BIGSERIAL PRIMARY KEY,
            theme_name  VARCHAR(100) NOT NULL,
            snap_date   DATE NOT NULL,
            stock_count INT  NOT NULL DEFAULT 0,
            avg_return  NUMERIC(8,4),
            top_codes   TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(theme_name, snap_date)
        )""",
    ]:
        try:
            await app.state.db.execute(_alter)
        except Exception:
            pass

    # recommendation_performance / telegram_logs 자동 생성 (이미 존재하면 skip)
    for _sql in [
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
    # 성과 추적 워커 시작
    import asyncio
    _tracker_task = asyncio.create_task(tracker_loop(app.state.db, app.state.redis))
    logger.info("API server started")
    yield
    _tracker_task.cancel()
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
    allow_headers=["*"],
)

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

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")


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


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    return FileResponse("static/index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
