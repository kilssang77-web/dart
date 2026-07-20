"""
일회성 govdata 수집 배치 — GitHub Actions에서 실행.
금융위원회 공공데이터 API → daily_bars.market_cap + stocks.shares_total 갱신.
"""
import asyncio
import logging
import os
import sys

_this_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_this_dir)
sys.path.insert(0, _parent_dir)   # services/collector/
sys.path.insert(0, _this_dir)     # services/collector/entrypoints/

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("govdata-batch")


async def run():
    from main import StockCollector
    from govdata_worker import _fetch_latest, _apply, _sync_holidays_if_needed

    svc = StockCollector()
    await svc.setup()

    await _sync_holidays_if_needed(svc)

    target_date, items = await _fetch_latest()
    if items and target_date:
        await _apply(svc, target_date, items)
        logger.info("[govdata-batch] 완료")
    else:
        logger.error("[govdata-batch] 최근 7일 유효 데이터 없음")

    await svc.db.close()


if __name__ == "__main__":
    asyncio.run(run())
