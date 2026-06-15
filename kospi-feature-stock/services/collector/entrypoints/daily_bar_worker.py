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
from redis_stats import refresh_all_stats, refresh_market_returns

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

    # 일봉 수집 완료 후 Redis 탐지 통계 갱신 (탐지 규칙 정상 동작 보장)
    logger.info("[daily] 일봉 수집 완료 — Redis 탐지 통계 갱신 시작")
    try:
        refreshed = await refresh_all_stats(svc.db, svc.redis, all_codes)
        logger.info(f"[daily] Redis 통계 갱신 완료: {refreshed}/{len(all_codes)}개")
    except Exception as e:
        logger.error(f"[daily] Redis 통계 갱신 실패: {e}")

    # KOSPI 지수 수익률 갱신 (ml_client의 per-event DB 쿼리 제거)
    try:
        await refresh_market_returns(svc.db, svc.redis)
    except Exception as e:
        logger.error(f"[daily] KOSPI 수익률 갱신 실패: {e}")

    # admin 엔드포인트용 카운터 캐시 갱신 (TTL 72h, SCAN 대체)
    try:
        _TTL = 60 * 60 * 72
        vc = await svc.db.fetchval(
            "SELECT COUNT(*) FROM feature_events WHERE pattern_vector IS NOT NULL"
        )
        rc = await svc.db.fetchval(
            "SELECT COUNT(*) FROM feature_events WHERE result_5d IS NOT NULL"
        )
        await svc.redis.set("stats:vector_count", int(vc or 0), ex=_TTL)
        await svc.redis.set("stats:result_count",  int(rc or 0), ex=_TTL)
        logger.info(f"[daily] 카운터 캐시 갱신: vector={vc}, result={rc}")
    except Exception as e:
        logger.error(f"[daily] 카운터 캐시 갱신 실패: {e}")


if __name__ == "__main__":
    asyncio.run(run())
