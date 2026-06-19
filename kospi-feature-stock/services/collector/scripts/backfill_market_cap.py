"""
금융위원회 API로 daily_bars.market_cap 전체 히스토리 백필.
market_cap = 0 인 날짜를 대상으로 2022-01-01 이후 전체 채움.
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from main import StockCollector
from kis.govdata_client import fetch_stock_prices

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s - %(message)s",
)
logger = logging.getLogger("backfill_market_cap")


async def main():
    svc = StockCollector()
    await svc.setup()

    rows = await svc.db.fetch(
        """
        SELECT DISTINCT date FROM daily_bars
        WHERE date >= '2022-01-01'
          AND market_cap = 0
          AND code NOT IN ('0001','1001')
        ORDER BY date DESC
        """
    )
    missing = [r["date"] for r in rows]
    total = len(missing)
    logger.info(f"백필 대상: {total}일")

    updated = 0
    skipped = 0
    for i, d in enumerate(missing):
        bas_dt = d.strftime("%Y%m%d")
        try:
            items = await fetch_stock_prices(bas_dt)
            if not items:
                skipped += 1
                continue
            recs = [
                (int(item.get("mrktTotAmt", 0) or 0),
                 (item.get("srtnCd") or "").strip(),
                 d)
                for item in items
                if len((item.get("srtnCd") or "").strip()) == 6
                   and int(item.get("mrktTotAmt", 0) or 0) > 0
            ]
            if recs:
                await svc.db.executemany(
                    "UPDATE daily_bars SET market_cap=$1 WHERE code=$2 AND date=$3::date",
                    recs,
                )
                updated += len(recs)
            if (i + 1) % 50 == 0:
                logger.info(f"진행 {i+1}/{total} ({bas_dt}) 누적={updated:,}건")
            await asyncio.sleep(0.2)
        except Exception as e:
            logger.warning(f"{bas_dt} 오류: {e}")

    logger.info(f"백필 완료: {updated:,}건 갱신 / {skipped}일 스킵")


if __name__ == "__main__":
    asyncio.run(main())
