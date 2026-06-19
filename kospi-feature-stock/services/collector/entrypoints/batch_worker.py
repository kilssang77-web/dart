"""
독립 서비스: 장 마감 후 전체 종목 배치 탐지.
트리거: Redis 키 daily_bars:ready:{YYYYMMDD}
        tick 컨테이너(_daily_bar_loop)가 일봉 수집 완료 시 설정.
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone, timedelta, time as dtime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import StockCollector, load_all_stocks
from batch_scanner import BatchScanner

_KST = timezone(timedelta(hours=9))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("collector-batch")

_STATS_TIME    = dtime(16, 10)   # main.py STATS_TIME 과 일치
_FALLBACK_TIME = dtime(17, 30)   # 이 시각 이후엔 신호 없어도 강행


async def _wait_for_daily_bars(redis, today_str: str) -> None:
    """tick 컨테이너가 daily_bars:ready:{date} 키를 설정할 때까지 대기.

    - 주말이면 즉시 통과 (일봉 수집 없음)
    - 17:30 KST 초과 시 tick 컨테이너 장애로 간주하고 강행
    """
    while True:
        now_kst = datetime.now(_KST)

        if now_kst.weekday() >= 5:
            logger.info("[batch] Weekend — skipping daily bar wait")
            return

        ready = await redis.get(f"daily_bars:ready:{today_str}")
        if ready:
            logger.info(f"[batch] daily_bars:ready:{today_str} confirmed — proceeding")
            return

        if now_kst.time() >= _FALLBACK_TIME:
            logger.warning(
                f"[batch] No daily_bars:ready signal by {_FALLBACK_TIME} KST "
                "— running without tick collector signal"
            )
            return

        reason = (
            f"before stats time ({now_kst.strftime('%H:%M')} KST)"
            if now_kst.time() < _STATS_TIME
            else f"waiting for tick collector ({now_kst.strftime('%H:%M')} KST)"
        )
        logger.info(f"[batch] {reason} — retrying in 60s")
        await asyncio.sleep(60)


async def run():
    svc = StockCollector()
    await svc.setup()
    all_codes = await load_all_stocks(svc.db)
    logger.info(f"[batch] Starting — {len(all_codes)} stocks")

    today_str = datetime.now(_KST).strftime("%Y%m%d")
    await _wait_for_daily_bars(svc.redis, today_str)

    # Redis 통계 갱신 (tick 컨테이너가 이미 처리했어도 재실행 무해)
    await svc._update_redis_stats(all_codes)

    # 배치 탐지 실행
    scanner = BatchScanner(svc.db, svc.redis, svc.kafka)
    try:
        events = await scanner.run(all_codes)
        logger.info(f"[batch] BatchScan completed — {len(events)} signals")
    except Exception as e:
        logger.error(f"[batch] BatchScan failed: {e}")

    # result_5d 백필
    try:
        n = await svc._backfill_result_5d()
        if n:
            logger.info(f"[batch] Result5d backfilled {n} events")
    except Exception as e:
        logger.error(f"[batch] Result5d error: {e}")

    # 내일 _STATS_TIME KST까지 슬립 — restart:unless-stopped 무한재시작 방지
    tomorrow = datetime.now(_KST).date() + timedelta(days=1)
    next_run = datetime(
        tomorrow.year, tomorrow.month, tomorrow.day,
        _STATS_TIME.hour, _STATS_TIME.minute,
        tzinfo=_KST,
    )
    wait_sec = max((next_run - datetime.now(_KST)).total_seconds(), 3600)
    logger.info(f"[batch] Done. Sleeping {wait_sec:.0f}s until {next_run.strftime('%Y-%m-%d %H:%M %Z')}")
    await asyncio.sleep(wait_sec)


if __name__ == "__main__":
    asyncio.run(run())
