"""
독립 서비스: 금융위원회 주식시세 API → daily_bars.market_cap + stocks.shares_total 갱신.

주기: 일 1회 (18:00 KST 이후 — T-1 데이터 확실히 확보)
  - T 데이터는 T+1 오전에 제공 → T-1부터 시도하여 최신 유효 데이터 사용
  - 갱신 범위: 오늘부터 최대 7 거래일 이전까지 스캔하여 최신 데이터 자동 선택
"""
import asyncio
import logging
import os
import sys
from datetime import date, timedelta, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import StockCollector, load_all_stocks
from kis.govdata_client import fetch_stock_prices

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("collector-govdata")

_KST              = timezone(timedelta(hours=9))
_REDIS_KEY        = "govdata:last_run_date"
_RUN_HOUR_KST     = 18          # 18:00 KST 이후 실행
_LOOKBACK_DAYS    = 7           # 최대 7일 이전까지 시도
_SLEEP_SECONDS    = 3600        # 1시간마다 실행 조건 체크


async def _fetch_latest(lookback: int = _LOOKBACK_DAYS) -> tuple[date | None, list[dict]]:
    """T-1 ~ T-lookback 범위에서 가장 최신 데이터가 있는 날짜와 데이터 반환."""
    today = date.today()
    for days_back in range(1, lookback + 1):
        trial = today - timedelta(days=days_back)
        bas_dt = trial.strftime("%Y%m%d")
        try:
            items = await fetch_stock_prices(bas_dt)
            if items:
                logger.info(f"[govdata] {bas_dt} 데이터 {len(items)}개 확인")
                return trial, items
        except Exception as e:
            logger.warning(f"[govdata] {bas_dt} 조회 오류: {e}")
    return None, []


async def _apply(svc: StockCollector, target_date: date, items: list[dict]) -> None:
    """조회된 시세 데이터를 DB에 반영."""
    bar_updates   = 0
    stock_updates = 0

    # 배치 처리 (asyncpg executemany)
    bar_records   = []
    stock_records = []

    for item in items:
        srtn_cd = (item.get("srtnCd") or "").strip()
        if not srtn_cd or len(srtn_cd) != 6:
            continue

        market_cap   = int(item.get("mrktTotAmt", 0) or 0)
        shares_total = int(item.get("lstgStCnt",  0) or 0)

        if market_cap > 0:
            bar_records.append((market_cap, srtn_cd, target_date))
        if shares_total > 0:
            stock_records.append((shares_total, srtn_cd))

    if bar_records:
        await svc.db.executemany(
            "UPDATE daily_bars SET market_cap=$1 WHERE code=$2 AND date=$3::date",
            bar_records,
        )
        bar_updates = len(bar_records)

    if stock_records:
        await svc.db.executemany(
            "UPDATE stocks SET shares_total=$1 WHERE code=$2",
            stock_records,
        )
        stock_updates = len(stock_records)

    logger.info(
        f"[govdata] 갱신 완료 ({target_date}): "
        f"daily_bars.market_cap {bar_updates}개 / stocks.shares_total {stock_updates}개"
    )


async def run():
    svc = StockCollector()
    await svc.setup()

    while True:
        now_kst = datetime.now(_KST)

        # 18:00 KST 이후에만 실행
        if now_kst.hour < _RUN_HOUR_KST:
            await asyncio.sleep(_SLEEP_SECONDS)
            continue

        # 오늘 이미 실행했으면 스킵
        today_str = now_kst.strftime("%Y-%m-%d")
        last_run  = await svc.redis.get(_REDIS_KEY)
        if last_run and (last_run.decode() if isinstance(last_run, bytes) else last_run) == today_str:
            await asyncio.sleep(_SLEEP_SECONDS)
            continue

        logger.info("[govdata] 실행 시작")
        try:
            target_date, items = await _fetch_latest()
            if items and target_date:
                await _apply(svc, target_date, items)
                await svc.redis.set(_REDIS_KEY, today_str, ex=86400 * 2)
            else:
                logger.error("[govdata] 최근 7일 데이터 없음")
        except Exception as e:
            logger.error(f"[govdata] 실행 오류: {e}", exc_info=True)

        await asyncio.sleep(_SLEEP_SECONDS)


if __name__ == "__main__":
    asyncio.run(run())
