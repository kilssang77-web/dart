"""
한국 주식시장 특화 예외처리
- 공휴일 / 거래정지 / 액면분할
"""
import logging
from datetime import date, timedelta
from typing import Optional
import asyncpg

logger = logging.getLogger(__name__)

# 공휴일 데이터 (DB의 kr_holidays 테이블이 주 데이터, 여기는 폴백)
_HOLIDAYS_FALLBACK: set[date] = {
    date(2025, 1, 1), date(2025, 1, 28), date(2025, 1, 29), date(2025, 1, 30),
    date(2025, 3, 1), date(2025, 5, 5), date(2025, 5, 6), date(2025, 6, 6),
    date(2025, 8, 15), date(2025, 10, 3), date(2025, 10, 5),
    date(2025, 10, 6), date(2025, 10, 7), date(2025, 10, 9), date(2025, 12, 25),
}


def is_trading_day(d: Optional[date] = None) -> bool:
    d = d or date.today()
    return d.weekday() < 5 and d not in _HOLIDAYS_FALLBACK


def prev_trading_day(d: Optional[date] = None) -> date:
    d = (d or date.today()) - timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def next_trading_day(d: Optional[date] = None) -> date:
    d = (d or date.today()) + timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


class StockSplitHandler:
    """액면분할 발생 시 과거 데이터 소급 조정"""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def apply(self, code: str, split_date: date, ratio: float):
        """ratio = 분할 비율 (예: 5 → 1주가 5주로)"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # 과거 가격 하향 조정, 거래량 상향 조정
                await conn.execute(
                    """
                    UPDATE daily_bars
                    SET
                        open   = ROUND(open::NUMERIC   / $1),
                        high   = ROUND(high::NUMERIC   / $1),
                        low    = ROUND(low::NUMERIC    / $1),
                        close  = ROUND(close::NUMERIC  / $1),
                        volume = ROUND(volume::NUMERIC * $1),
                        adj_factor = COALESCE(adj_factor, 1.0) / $1
                    WHERE code=$2 AND date < $3
                    """,
                    ratio, code, split_date,
                )
                # 패턴 벡터 무효화 (재계산 필요)
                await conn.execute(
                    "UPDATE feature_events SET pattern_vector=NULL WHERE code=$1 AND detected_at < $2",
                    code, split_date,
                )
                # 이력 기록
                await conn.execute(
                    """
                    UPDATE stocks
                    SET split_history = split_history || $1::jsonb,
                        updated_at    = NOW()
                    WHERE code = $2
                    """,
                    f'[{{"date":"{split_date}","ratio":{ratio}}}]',
                    code,
                )
        logger.info(f"Split applied: {code} ratio={ratio} date={split_date}")


class TradingHaltHandler:
    """거래정지 처리 — 구독 자동 해제 포함"""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def halt(self, code: str, reason: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE stocks SET is_trading_halt=TRUE, halt_reason=$2, updated_at=NOW() WHERE code=$1",
                code, reason,
            )
        logger.warning(f"Trading halt: {code} [{reason}]")

    async def resume(self, code: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE stocks SET is_trading_halt=FALSE, halt_reason=NULL, updated_at=NOW() WHERE code=$1",
                code,
            )
        logger.info(f"Trading resumed: {code}")

    async def filter_active(self, codes: list[str]) -> list[str]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT code FROM stocks WHERE code=ANY($1) AND is_trading_halt=FALSE AND is_active=TRUE",
                codes,
            )
        return [r["code"] for r in rows]
