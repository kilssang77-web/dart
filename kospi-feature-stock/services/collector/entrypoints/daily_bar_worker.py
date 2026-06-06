"""
독립 서비스: 일봉 수집 + 기술지표 계산 + EOD 수급.
주기: 장 마감 후 1회 (16:10~17:00)
"""
import asyncio
import logging
import os
import sys

# collector 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import StockCollector, load_all_stocks, load_active_stocks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("collector-daily")


async def run():
    svc = StockCollector()
    await svc.setup()
    all_codes    = await load_all_stocks(svc.db)
    active_codes = await load_active_stocks(svc.redis)

    if not all_codes:
        logger.warning("[daily] stocks table empty — using active_codes")
        all_codes = active_codes

    logger.info(f"[daily] Starting daily_bar + supply_demand EOD for {len(all_codes)} stocks")

    # 시작 시 백필 (일봉 누락 종목)
    asyncio.create_task(svc._backfill_daily_bars(all_codes))

    await asyncio.gather(
        svc._daily_bar_loop(all_codes),
        svc._supply_demand_eod_loop(all_codes),
        return_exceptions=True,
    )


if __name__ == "__main__":
    asyncio.run(run())
