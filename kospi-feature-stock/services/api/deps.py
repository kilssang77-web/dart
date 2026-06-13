import asyncio
import logging
from fastapi import Request, HTTPException
import asyncpg
import orjson
import redis.asyncio as redis_lib

logger = logging.getLogger("api.deps")


def get_db(request: Request) -> asyncpg.Pool:
    return request.app.state.db


def get_redis(request: Request) -> redis_lib.Redis:
    return request.app.state.redis


# ── Redis 실시간 현재가 일괄 보정 ─────────────────────────────────────────────

async def enrich_live_prices(redis: redis_lib.Redis, dicts: list[dict],
                              price_field: str = "current_price",
                              rate_field: str = "change_rate") -> None:
    """quote:{code} 에서 실시간 현재가·등락률로 daily_bars 기반 필드를 덮어씀."""
    if not dicts:
        return
    codes = list({d["code"] for d in dicts if d.get("code")})
    try:
        pipe = redis.pipeline()
        for c in codes:
            pipe.get(f"quote:{c}")
        results = await pipe.execute()
    except Exception:
        return
    live: dict = {}
    for c, raw in zip(codes, results):
        if raw:
            try:
                tick = orjson.loads(raw)
                if tick.get("price"):
                    live[c] = tick
            except Exception:
                pass
    for d in dicts:
        q = live.get(d.get("code", ""))
        if q:
            d[price_field] = q["price"]
            d[rate_field]  = q.get("change_rate") or 0.0


# ── DB 재시도 래퍼 ─────────────────────────────────────────────────────────────

async def db_fetch(db: asyncpg.Pool, query: str, *params, retries: int = 1) -> list:
    """transient 연결 오류 시 1회 재시도."""
    for attempt in range(retries + 1):
        try:
            return await db.fetch(query, *params)
        except (asyncpg.PostgresConnectionError, asyncpg.TooManyConnectionsError):
            if attempt < retries:
                await asyncio.sleep(0.3 * (attempt + 1))
            else:
                raise


async def db_fetchrow(db: asyncpg.Pool, query: str, *params, retries: int = 1):
    """transient 연결 오류 시 1회 재시도."""
    for attempt in range(retries + 1):
        try:
            return await db.fetchrow(query, *params)
        except (asyncpg.PostgresConnectionError, asyncpg.TooManyConnectionsError):
            if attempt < retries:
                await asyncio.sleep(0.3 * (attempt + 1))
            else:
                raise


# ── Redis 캐시 + Stale fallback ────────────────────────────────────────────────

def _serialize(rows: list) -> bytes:
    """asyncpg Record/dict 리스트를 JSON bytes로 변환 (date/datetime 포함)."""
    def _conv(v):
        if v is None:
            return None
        if hasattr(v, "isoformat"):
            return v.isoformat()
        try:
            return float(v) if hasattr(v, "__float__") else v
        except Exception:
            return v

    return orjson.dumps(
        [{k: _conv(v) for k, v in (dict(r) if not isinstance(r, dict) else r).items()} for r in rows]
    )


async def cached_fetch(
    redis: redis_lib.Redis,
    db: asyncpg.Pool,
    cache_key: str,
    query: str,
    *params,
    ttl: int = 60,
    stale_multiplier: int = 10,
) -> list:
    """
    Cache-aside 패턴. DB 장애 시 최대 ttl × stale_multiplier 초 동안 stale 캐시 반환.
    """
    fresh_k = f"apicache:{cache_key}"
    stale_k = f"stalecache:{cache_key}"

    try:
        raw = await redis.get(fresh_k)
        if raw:
            return orjson.loads(raw)
    except Exception:
        pass

    try:
        rows = await db_fetch(db, query, *params)
        result_list = [dict(r) for r in rows]
        try:
            payload = _serialize(result_list)
            await redis.set(fresh_k, payload, ex=ttl)
            await redis.set(stale_k, payload, ex=ttl * stale_multiplier)
        except Exception:
            pass
        return result_list
    except Exception as exc:
        logger.warning(f"DB unavailable ({type(exc).__name__}): {exc}")
        logger.debug(f"DB unavailable cache_key={cache_key}")

    try:
        stale = await redis.get(stale_k)
        if stale:
            logger.info("Serving stale cache")
            logger.debug(f"Serving stale cache for: {cache_key}")
            return orjson.loads(stale)
    except Exception:
        pass

    raise HTTPException(status_code=503, detail="Database temporarily unavailable")