"""
일일 손실 한도 가드
- Redis에 당일 실현 손실 누적
- 한도 초과 시 자동매매 중단 신호 발행
"""
import logging
from datetime import datetime, timezone, timedelta

import redis.asyncio as redis_lib

logger = logging.getLogger(__name__)

_KST = timezone(timedelta(hours=9))
_DAILY_LOSS_KEY = "trader:daily_loss"   # 당일 실현 손실 (원, 음수)
_LIMIT_HIT_KEY  = "trader:daily_limit_hit"


class DailyLossGuard:

    def __init__(self, redis_client: redis_lib.Redis, daily_loss_limit: int = 100_000):
        self.redis = redis_client
        self.limit = abs(daily_loss_limit)   # 양수로 저장

    async def record_loss(self, pnl_amount: int) -> bool:
        """
        손익 기록.
        pnl_amount: 원 단위 손익 (양수=이익, 음수=손실)
        Returns True if daily loss limit just exceeded.
        """
        if pnl_amount >= 0:
            return False   # 이익이면 가드 불필요

        loss = abs(pnl_amount)
        total_loss = await self.redis.incrbyfloat(_DAILY_LOSS_KEY, loss)
        now_kst = datetime.now(_KST)
        # 자정 지나면 키 만료 (다음날 리셋)
        seconds_until_midnight = (
            (now_kst.replace(hour=23, minute=59, second=59) - now_kst).seconds + 1
        )
        await self.redis.expire(_DAILY_LOSS_KEY, seconds_until_midnight)

        if total_loss >= self.limit:
            await self.redis.set(_LIMIT_HIT_KEY, "1", ex=seconds_until_midnight)
            logger.warning(
                f"일일 손실 한도 초과: {total_loss:,.0f}원 >= {self.limit:,.0f}원 — 자동매매 중단"
            )
            return True
        return False

    async def is_limit_hit(self) -> bool:
        val = await self.redis.get(_LIMIT_HIT_KEY)
        return val is not None

    async def get_today_loss(self) -> int:
        val = await self.redis.get(_DAILY_LOSS_KEY)
        return int(float(val)) if val else 0

    async def reset(self) -> None:
        """수동 리셋 (관리자 전용)."""
        await self.redis.delete(_DAILY_LOSS_KEY, _LIMIT_HIT_KEY)
        logger.info("일일 손실 가드 수동 리셋 완료")

    async def get_status(self) -> dict:
        loss    = await self.get_today_loss()
        hit     = await self.is_limit_hit()
        return {
            "today_loss": loss,
            "daily_limit": self.limit,
            "remaining": max(0, self.limit - loss),
            "is_limit_hit": hit,
            "usage_pct": round(loss / self.limit * 100, 1) if self.limit else 0,
        }
