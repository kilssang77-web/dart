"""
독립 서비스: 장중 전 종목 REST 인트라데이 스캔.
대상: KOSPI + KOSDAQ 활성 종목 (거래대금 순 정렬, ~2,000종목)
주기: ~3~6분 풀 사이클 (INTRADAY_REQ_INTERVAL × 종목수)
탐지: 신고가 돌파(tick-data), 거래량·거래대금 급증(feature-detected 직접 발행)
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import StockCollector, load_kospi_kosdaq, load_active_stocks, refresh_active_codes_from_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("collector-intraday")


async def run():
    svc = StockCollector()
    await svc.setup()

    # Redis active_codes 초기화
    cached = await svc.redis.get("stocks:active_codes")
    if not cached:
        await refresh_active_codes_from_db(svc.db, svc.redis, top_n=80)

    # KOSPI/KOSDAQ 전 종목 (거래대금 내림차순 → 활성 종목이 먼저 스캔됨)
    all_codes = await load_kospi_kosdaq(svc.db)
    if not all_codes:
        logger.error("[intraday] No KOSPI/KOSDAQ stocks found — aborting")
        return

    logger.info(f"[intraday] Starting REST scan for {len(all_codes)} KOSPI/KOSDAQ stocks")
    await svc._intraday_rest_scan_loop(all_codes)


if __name__ == "__main__":
    asyncio.run(run())
