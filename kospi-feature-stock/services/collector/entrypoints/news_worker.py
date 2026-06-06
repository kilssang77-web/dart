"""
독립 서비스: 뉴스 크롤링 + DART + KIND 공시 수집.
주기: 뉴스 30분, 공시 5분
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
logger = logging.getLogger("collector-news")


async def run():
    svc = StockCollector()
    await svc.setup()
    active_codes = await load_active_stocks(svc.redis)
    logger.info(f"[news] Starting news+disclosure collection for {len(active_codes)} active stocks")

    await asyncio.gather(
        svc._news_loop(active_codes),
        svc.dart.run(),
        svc.kind.run(),
        return_exceptions=True,
    )


if __name__ == "__main__":
    asyncio.run(run())
