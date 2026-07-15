"""
KIS REST API 경량 현재가 조회 — API 서버 전용.
collector의 Redis 캐시 토큰(kis:access_token)을 재사용하며,
토큰 없을 때는 KIS_APP_KEY/SECRET 환경변수로 신규 발급.
"""
import logging
import os
import httpx
import redis.asyncio as redis_lib

logger = logging.getLogger(__name__)

_KIS_BASE = os.getenv("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443")
_APP_KEY  = os.getenv("KIS_APP_KEY", "")
_APP_SEC  = os.getenv("KIS_APP_SECRET", "")

_TOKEN_REDIS_KEY = "kis:access_token"


async def _get_token(redis: redis_lib.Redis) -> str | None:
    """Redis 캐시 우선, 없으면 직접 발급 (app_key 환경변수 필요)."""
    try:
        cached = await redis.get(_TOKEN_REDIS_KEY)
        if cached:
            return cached.decode() if isinstance(cached, bytes) else cached
    except Exception:
        pass

    if not _APP_KEY or not _APP_SEC:
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{_KIS_BASE}/oauth2/tokenP",
                json={
                    "grant_type": "client_credentials",
                    "appkey": _APP_KEY,
                    "appsecret": _APP_SEC,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get("access_token", "")
            if token and redis:
                ttl = max(data.get("expires_in", 86400) - 1800, 300)
                await redis.setex(_TOKEN_REDIS_KEY, ttl, token)
            return token or None
    except Exception as e:
        logger.debug(f"KIS token issue failed: {e}")
        return None


async def fetch_current_price(code: str, redis: redis_lib.Redis) -> dict | None:
    """
    KIS FHKST01010100으로 현재가 조회.
    장중에만 유효한 실시간가. 실패 시 None 반환.
    """
    token = await _get_token(redis)
    if not token:
        return None

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{_KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-price",
                headers={
                    "authorization": f"Bearer {token}",
                    "appkey":        _APP_KEY,
                    "appsecret":     _APP_SEC,
                    "tr_id":         "FHKST01010100",
                    "custtype":      "P",
                },
                params={
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": code,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("rt_cd") != "0":
                return None
            o = data.get("output", {})
            price = int(o.get("stck_prpr", 0) or 0)
            if price == 0:
                return None
            return {
                "price":       price,
                "prev_close":  int(o.get("stck_sdpr", 0) or 0),
                "change":      int(o.get("prdy_vrss", 0) or 0),
                "change_rate": float(o.get("prdy_ctrt", 0) or 0),
                "open":        int(o.get("stck_oprc", 0) or 0),
                "high":        int(o.get("stck_hgpr", 0) or 0),
                "low":         int(o.get("stck_lwpr", 0) or 0),
                "volume":      int(o.get("acml_vol", 0) or 0),
                "amount":      int(o.get("acml_tr_pbmn", 0) or 0),
                "source":      "realtime",
            }
    except Exception as e:
        logger.debug(f"KIS quote [{code}] failed: {e}")
        return None
