import logging
import os
import time
import orjson
import redis.asyncio as redis_lib

logger = logging.getLogger(__name__)

_WINDOW_SECONDS  = int(os.environ.get("CORRELATION_WINDOW_SEC",  "1200"))  # 20분
_MIN_STOCKS      = int(os.environ.get("CORRELATION_MIN_STOCKS",  "3"))
_BASE_SCORE      = float(os.environ.get("CORRELATION_BASE_SCORE", "0.62"))


class CorrelationDetector:
    """동일 섹터에서 N종목 이상 신호가 집중될 때 SECTOR_CORRELATION 신호를 발생시킨다.

    섹터 정보는 Redis `stock:sector:{code}` 키로 조회한다.
    키가 없으면 해당 종목은 correlation 추적에서 제외된다.
    """

    def __init__(self, redis_client: redis_lib.Redis):
        self.redis  = redis_client
        self.window = _WINDOW_SECONDS
        self.min_stocks = _MIN_STOCKS

    async def record_and_check(self, signal: dict) -> dict | None:
        """신호를 섹터 집계에 기록하고 임계치 초과 시 SECTOR_CORRELATION dict 반환."""
        code       = signal.get("code", "")
        price      = signal.get("price", 0)
        change_rate = signal.get("change_rate", 0.0)

        if not code:
            return None

        sector = await self._get_sector(code)
        if not sector:
            return None

        now = time.time()
        set_key = f"corr:sector:{sector}"

        try:
            # 종목 추가 (score=timestamp, member=code)
            await self.redis.zadd(set_key, {code: now})
            # 오래된 항목 제거
            await self.redis.zremrangebyscore(set_key, 0, now - self.window)
            # TTL 갱신
            await self.redis.expire(set_key, self.window + 60)
            # 현재 집계된 고유 종목 수
            unique_codes = await self.redis.zcard(set_key)
        except Exception as e:
            logger.debug(f"[Corr] Redis error for {code}/{sector}: {e}")
            return None

        if unique_codes < self.min_stocks:
            return None

        score = min(0.92, _BASE_SCORE + (unique_codes - self.min_stocks) * 0.05)
        logger.info(f"[Corr] 섹터 집중: {sector} {unique_codes}종목 — score={score:.2f}")

        return {
            "code":        code,
            "event_type":  "SECTOR_CORRELATION",
            "price":       int(price),
            "change_rate": float(change_rate),
            "signal_score": round(score, 3),
            "signal_data": {
                "sector":       sector,
                "stock_count":  int(unique_codes),
                "window_sec":   self.window,
            },
        }

    async def _get_sector(self, code: str) -> str | None:
        try:
            raw = await self.redis.get(f"stock:sector:{code}")
            if raw:
                return raw.decode() if isinstance(raw, bytes) else str(raw)
            # stock:meta:{code} 에 JSON 형태로 저장된 경우 폴백
            meta_raw = await self.redis.get(f"stock:meta:{code}")
            if meta_raw:
                meta = orjson.loads(meta_raw)
                return meta.get("sector") or meta.get("industry")
        except Exception:
            pass
        return None
