"""
Supabase 히스토리 백필 (pykrx → Supabase daily_bars)
market_scan.py 실행 전 1회 실행 필요. 약 90일치 일봉 데이터 적재.
실행: python backfill_supabase.py
"""
import asyncio
import asyncpg
import os
import time
import logging
from datetime import date, timedelta
from dotenv import load_dotenv
from pykrx import stock as krx
import pandas as pd

load_dotenv(os.path.expanduser("~/.env"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill")

DSN  = os.environ["POSTGRES_DSN"]
DAYS = int(os.environ.get("BACKFILL_DAYS", "90"))


def biz_dates(days: int) -> list:
    today = date.today()
    start = today - timedelta(days=days + 14)
    return pd.bdate_range(str(start), str(today)).date.tolist()[-days:]


async def upsert_bars(conn: asyncpg.Connection, rows: list) -> int:
    if not rows:
        return 0
    await conn.executemany(
        """
        INSERT INTO daily_bars
            (date, code, open, high, low, close, volume, amount, change_rate)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        ON CONFLICT (date, code) DO UPDATE SET
            open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
            close=EXCLUDED.close, volume=EXCLUDED.volume,
            amount=EXCLUDED.amount, change_rate=EXCLUDED.change_rate
        """,
        rows,
    )
    return len(rows)


async def upsert_stocks(conn: asyncpg.Connection, market: str, codes: list) -> None:
    if not codes:
        return
    rows = [(c, market) for c in codes]
    await conn.executemany(
        """
        INSERT INTO stocks (code, market, is_active)
        VALUES ($1, $2, true)
        ON CONFLICT (code) DO UPDATE SET market=EXCLUDED.market, is_active=true
        """,
        rows,
    )


async def main():
    conn = await asyncpg.connect(DSN)
    try:
        dates = biz_dates(DAYS)
        log.info(f"백필 기간: {dates[0]} ~ {dates[-1]} ({len(dates)}일)")

        total = 0
        for i, d in enumerate(dates):
            ds = d.strftime("%Y%m%d")
            rows = []

            for market in ["KOSPI", "KOSDAQ"]:
                try:
                    df = krx.get_market_ohlcv(ds, ds, market)
                    if df is None or df.empty:
                        continue

                    # 첫 날에는 stocks 테이블도 채움
                    if i == 0:
                        await upsert_stocks(conn, market, df.index.astype(str).str.zfill(6).tolist())

                    for code, r in df.iterrows():
                        code = str(code).zfill(6)
                        close_val = int(r.get("종가", 0) or 0)
                        if close_val <= 0:
                            continue
                        rows.append((
                            d, code,
                            int(r.get("시가", 0) or 0),
                            int(r.get("고가", 0) or 0),
                            int(r.get("저가", 0) or 0),
                            close_val,
                            int(r.get("거래량", 0) or 0),
                            int(r.get("거래대금", 0) or 0),
                            float(r.get("등락률", 0.0) or 0.0),
                        ))
                except Exception as e:
                    log.warning(f"{ds} {market}: {e}")
                time.sleep(0.5)

            if rows:
                n = await upsert_bars(conn, rows)
                total += n

            if (i + 1) % 5 == 0 or i == len(dates) - 1:
                log.info(f"[{i+1}/{len(dates)}] {ds}: {len(rows)}행 / 누계 {total:,}행")

        log.info(f"백필 완료: 총 {total:,}행")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
