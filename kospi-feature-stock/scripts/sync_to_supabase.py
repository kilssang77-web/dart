"""
로컬 PostgreSQL → Supabase 증분 동기화.
대상: daily_bars(최근 SYNC_DAYS일), recommendations, feature_events, disclosures

실행:
  SRC_POSTGRES_DSN=<local> DST_POSTGRES_DSN=<supabase> python sync_to_supabase.py
"""
import asyncio
import logging
import os
from datetime import date, timedelta

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sync")

SYNC_DAYS = int(os.environ.get("SYNC_DAYS", "90"))
BATCH = 2000


async def upsert_batch(dst: asyncpg.Connection, table: str, rows: list[dict], pk: list[str]):
    if not rows:
        return 0
    cols = list(rows[0].keys())
    col_list = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(f"${i+1}" for i in range(len(cols)))
    conflict_cols = ", ".join(f'"{c}"' for c in pk)
    update_set = ", ".join(
        f'"{c}" = EXCLUDED."{c}"' for c in cols if c not in pk
    )
    sql = (
        f'INSERT INTO {table} ({col_list}) VALUES ({placeholders}) '
        f'ON CONFLICT ({conflict_cols}) DO UPDATE SET {update_set}'
    )
    await dst.executemany(sql, [tuple(r[c] for c in cols) for r in rows])
    return len(rows)


async def sync_table(src: asyncpg.Connection, dst: asyncpg.Connection,
                     query: str, table: str, pk: list[str], params: list):
    rows = await src.fetch(query, *params)
    if not rows:
        log.info(f"{table}: 동기화할 데이터 없음")
        return
    dicts = [dict(r) for r in rows]
    total = 0
    for i in range(0, len(dicts), BATCH):
        total += await upsert_batch(dst, table, dicts[i:i+BATCH], pk)
    log.info(f"{table}: {total:,}건 동기화 완료")


async def main():
    src_dsn = os.environ["SRC_POSTGRES_DSN"].replace("+asyncpg", "")
    dst_dsn = os.environ["DST_POSTGRES_DSN"].replace("+asyncpg", "")
    since = date.today() - timedelta(days=SYNC_DAYS)
    log.info(f"동기화 시작: {since} 이후 {SYNC_DAYS}일치")

    src = await asyncpg.connect(src_dsn)
    dst = await asyncpg.connect(dst_dsn)
    try:
        # 1. daily_bars
        await sync_table(src, dst,
            "SELECT code,date,open,high,low,close,volume,amount,change_rate,"
            "foreign_net_buy,inst_net_buy,short_sell_vol,rsi14,macd,macd_signal,"
            "bb_upper,bb_lower,ma5,ma20,ma60,atr14,market_cap "
            "FROM daily_bars WHERE date >= $1 ORDER BY date,code",
            "daily_bars", ["code", "date"], [since])

        # 2. stocks (전체 — 상장/폐지 반영)
        await sync_table(src, dst,
            "SELECT code,name,market,sector,industry,listing_date,is_active "
            "FROM stocks",
            "stocks", ["code"], [])

        # 3. recommendations (최근 SYNC_DAYS일)
        await sync_table(src, dst,
            "SELECT id,code,action,signal_time,entry_price,target_price,"
            "stop_loss_price,success_prob,risk_score,risk_reward_ratio,"
            "expected_return,rationale,rec_score,confidence_grade "
            "FROM recommendations WHERE signal_time >= $1 ORDER BY signal_time",
            "recommendations", ["id"], [since])

        # 4. feature_events (최근 30일)
        fe_since = date.today() - timedelta(days=30)
        await sync_table(src, dst,
            "SELECT id,code,event_type,detected_at,signal_data,signal_score,"
            "risk_score,volume_ratio,change_rate "
            "FROM feature_events WHERE detected_at >= $1 ORDER BY detected_at",
            "feature_events", ["id"], [fe_since])

        # 5. disclosures (최근 30일)
        await sync_table(src, dst,
            "SELECT id,code,rcept_no,disclosed_at,title,category,"
            "sentiment_score,is_favorable "
            "FROM disclosures WHERE disclosed_at >= $1 ORDER BY disclosed_at",
            "disclosures", ["id"], [fe_since])

        log.info("전체 동기화 완료")
    finally:
        await src.close()
        await dst.close()


if __name__ == "__main__":
    asyncio.run(main())
