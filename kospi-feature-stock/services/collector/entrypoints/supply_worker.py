"""
독립 서비스: 장중 수급 수집 (30분 간격).
대상: active_codes (기본 20종목 + 탐지 종목)
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import StockCollector, load_active_stocks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("collector-supply")


async def run():
    svc = StockCollector()
    await svc.setup()
    active_codes = await load_active_stocks(svc.redis)
    logger.info(f"[supply] Starting supply_demand loop for {len(active_codes)} stocks")

    # 최근 5 영업일 백필 (시작 시 1회)
    asyncio.create_task(svc._backfill_supply_demand(active_codes))

    await asyncio.gather(
        svc._supply_demand_loop(active_codes),
        return_exceptions=True,
    )


if __name__ == "__main__":
    asyncio.run(run())
