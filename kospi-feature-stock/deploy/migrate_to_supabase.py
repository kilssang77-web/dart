"""
로컬 PostgreSQL  Supabase 데이터 마이그레이션
"""
import asyncio
import asyncpg
from datetime import date, timedelta

SRC_DSN = "postgresql://stockuser:StrongPass123!@localhost:5432/feature_stock"
DST_DSN = "postgresql://postgres.bbgujvxckrcvvaiyimeh:3bQVcscGrl2cuxVf@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres"

BATCH = 500
CUTOFF_6M = (date.today() - timedelta(days=180)).isoformat()
CUTOFF_3M = (date.today() - timedelta(days=90)).isoformat()


async def upsert_table(src, dst, table, where_clause="", where_args=None, conflict="(id)"):
    cols_rows = await src.fetch(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name=$1 ORDER BY ordinal_position", table
    )
    col_names = [r["column_name"] for r in cols_rows]
    q = f"SELECT * FROM {table}"
    if where_clause:
        q += f" WHERE {where_clause}"
    rows = await src.fetch(q, *(where_args or []))
    if not rows:
        print(f"  {table}: 0 rows")
        return 0
    ph = ", ".join(f"${i+1}" for i in range(len(col_names)))
    cols_str = ", ".join(col_names)
    upd = ", ".join(f"{c}=EXCLUDED.{c}" for c in col_names if c not in ("id","code","hdate"))
    if upd:
        sql = f"INSERT INTO {table} ({cols_str}) VALUES ({ph}) ON CONFLICT {conflict} DO UPDATE SET {upd}"
    else:
        sql = f"INSERT INTO {table} ({cols_str}) VALUES ({ph}) ON CONFLICT {conflict} DO NOTHING"
    total = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i+BATCH]
        await dst.executemany(sql, [tuple(r) for r in batch])
        total += len(batch)
        print(f"  {table}: {total}/{len(rows)}", end="\r")
    print(f"  {table}: {total} rows done        ")
    return total


async def main():
    print("로컬 DB 연결...")
    src = await asyncpg.connect(SRC_DSN, command_timeout=120)
    print("Supabase 연결...")
    dst = await asyncpg.connect(DST_DSN, ssl="require", command_timeout=120)

    print(f"\n[1/6] stocks")
    await upsert_table(src, dst, "stocks", conflict="(code)")

    print(f"\n[2/6] kr_holidays")
    await upsert_table(src, dst, "kr_holidays", conflict="(hdate)")

    print(f"\n[3/6] daily_bars (since {CUTOFF_6M})")
    await upsert_table(src, dst, "daily_bars",
                       where_clause="date >= $1", where_args=[CUTOFF_6M],
                       conflict="(code, date)")

    print(f"\n[4/6] supply_demand (since {CUTOFF_3M})")
    await upsert_table(src, dst, "supply_demand",
                       where_clause="date >= $1", where_args=[CUTOFF_3M],
                       conflict="(code, date)")

    print(f"\n[5/6] feature_events (since {CUTOFF_3M})")
    await upsert_table(src, dst, "feature_events",
                       where_clause="detected_at >= $1", where_args=[CUTOFF_3M],
                       conflict="(id)")

    print(f"\n[6/6] recommendations (since {CUTOFF_3M})")
    await upsert_table(src, dst, "recommendations",
                       where_clause="created_at >= $1", where_args=[CUTOFF_3M],
                       conflict="(id)")

    await src.close()
    await dst.close()
    print("\n마이그레이션 완료!")


if __name__ == "__main__":
    asyncio.run(main())