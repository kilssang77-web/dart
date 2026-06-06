"""
독립 서비스: 장 마감 후 전체 종목 배치 탐지.
트리거: _daily_bars_done 이벤트 (stats 갱신 완료 신호)
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import StockCollector, load_all_stocks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("collector-batch")


async def run():
    svc = StockCollector()
    await svc.setup()
    all_codes = await load_all_stocks(svc.db)
    logger.info(f"[batch] Starting batch scanner for {len(all_codes)} stocks")

    # Redis stats 먼저 갱신 (daily bar 서비스가 완료했다고 가정)
    await svc._update_redis_stats(all_codes)
    svc._daily_bars_done.set()

    await asyncio.gather(
        svc._batch_scan_loop(all_codes),
        return_exceptions=True,
    )


if __name__ == "__main__":
    asyncio.run(run())
