from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import asyncpg
import redis.asyncio as redis_lib
import os
import logging

from routers import stocks, features, recommendations, disclosures, backtest, themes, market, disclosure_filters

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
    logger.info("API server started")
    yield
    await app.state.db.close()
    await app.state.redis.close()
    logger.info("API server stopped")


app = FastAPI(
    title="Feature Stock Detection API",
    description="KOSPI/KOSDAQ 실시간 특징주 탐지 및 매매 추천 시스템",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse("static/index.html")


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
    pubsub = websocket.app.state.redis.pubsub()
    await pubsub.subscribe("channel:ticks")
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
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
