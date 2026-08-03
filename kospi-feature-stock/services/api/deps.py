import asyncio
import logging
import time
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


# ── 인메모리 캐시 (Redis 요청 제거) ──────────────────────────────────────────────
# Redis 500k/월 한도 절감을 위해 process-level TTL 캐시로 대체.
# 단일 프로세스 API 서버이므로 메모리 일관성 문제 없음.

_mem_cache: dict[str, tuple[float, list]] = {}   # key → (expires_at, data)
_stale_cache: dict[str, tuple[float, list]] = {}  # key → (expires_at, data)


def _cache_get(store: dict, key: str) -> list | None:
    entry = store.get(key)
    if entry and time.monotonic() < entry[0]:
        return entry[1]
    return None


def _cache_set(store: dict, key: str, data: list, ttl: int) -> None:
    store[key] = (time.monotonic() + ttl, data)


def _serialize(rows: list) -> list[dict]:
    """asyncpg Record 리스트를 dict 리스트로 변환 (date/datetime → isoformat)."""
    def _conv(v):
        if v is None:
            return None
        if hasattr(v, "isoformat"):
            return v.isoformat()
        try:
            return float(v) if hasattr(v, "__float__") else v
        except Exception:
            return v

    return [{k: _conv(v) for k, v in (dict(r) if not isinstance(r, dict) else r).items()} for r in rows]


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
    인메모리 Cache-aside 패턴. DB 장애 시 stale 캐시 반환.
    redis 파라미터는 시그니처 호환을 위해 유지하나 캐시 저장엔 사용하지 않음.
    """
    cached = _cache_get(_mem_cache, cache_key)
    if cached is not None:
        return cached

    try:
        rows = await db_fetch(db, query, *params)
        result_list = _serialize(rows)
        _cache_set(_mem_cache,   cache_key, result_list, ttl)
        _cache_set(_stale_cache, cache_key, result_list, ttl * stale_multiplier)
        return result_list
    except Exception as exc:
        logger.warning(f"DB unavailable ({type(exc).__name__}): {exc}")

    stale = _cache_get(_stale_cache, cache_key)
    if stale is not None:
        logger.info(f"Serving stale cache for: {cache_key}")
        return stale

    raise HTTPException(status_code=503, detail="Database temporarily unavailable")