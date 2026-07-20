"""
일회성 재무 데이터 수집 배치 — GitHub Actions에서 실행.
financials_worker.run_collection()을 한 번 호출하고 종료.
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
logger = logging.getLogger("financials-batch")


async def run():
    from main import StockCollector, load_all_stocks
    from financials_worker import run_collection

    svc = StockCollector()
    await svc.setup()

    codes = await load_all_stocks(svc.db)
    logger.info(f"[financials-batch] 활성 종목 {len(codes)}개 로드 완료")

    if not codes:
        logger.error("[financials-batch] 활성 종목 없음 — 종료")
        await svc.db.close()
        return

    await run_collection(svc, codes)

    logger.info("[financials-batch] 완료")
    await svc.db.close()


if __name__ == "__main__":
    asyncio.run(run())
