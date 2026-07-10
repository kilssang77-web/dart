"""
Simple Redis-backed cache helpers.

Usage:
    redis_client = get_redis()   # None if Redis unavailable
    val = await redis_get(rc, key)
    await redis_set(rc, key, value, ttl=60)
"""
import json
import logging
from typing import Any

import redis as _redis

from ..config import get_settings

logger = logging.getLogger(__name__)
_redis_client: "_redis.Redis | None" = None
_redis_init_done = False


def get_redis() -> "_redis.Redis | None":
    global _redis_client, _redis_init_done
    if _redis_init_done:
        return _redis_client
    _redis_init_done = True
    try:
        settings = get_settings()
        rc = _redis.from_url(
            settings.redis_url,
            socket_connect_timeout=5,
            socket_timeout=5,
            ssl_cert_reqs=None,
        )
        rc.ping()
        _redis_client = rc
        logger.info("Redis 연결 완료")
    except Exception as e:
        logger.warning("Redis 연결 실패 — 캐시 비활성화: %s", e)
        _redis_client = None
    return _redis_client


def cache_get(rc: "_redis.Redis | None", key: str) -> "Any | None":
    if rc is None:
        return None
    try:
        raw = rc.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def cache_set(rc: "_redis.Redis | None", key: str, value: Any, ttl: int = 60) -> None:
    if rc is None:
        return
    try:
        rc.setex(key, ttl, json.dumps(value, default=str))
    except Exception:
        pass


def cache_delete_pattern(rc: "_redis.Redis | None", pattern: str) -> None:
    if rc is None:
        return
    try:
        keys = rc.keys(pattern)
        if keys:
            rc.delete(*keys)
    except Exception:
        pass
