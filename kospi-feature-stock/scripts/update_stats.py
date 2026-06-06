"""
장마감 후 Redis 통계 갱신 (매일 16:00+ 실행).
사용: python scripts/update_stats.py
"""
import asyncio
import asyncpg
import redis.asyncio as redis_lib
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("update_stats")


async def main():
    dsn = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    db  = await asyncpg.create_pool(dsn=dsn, min_size=3, max_size=10)
    red = redis_lib.from_url(os.environ["REDIS_URL"])

    async with db.acquire() as conn:
        codes = [r["code"] for r in await conn.fetch(
            "SELECT code FROM stocks WHERE is_active=TRUE AND is_trading_halt=FALSE"
        )]

    logger.info(f"Updating stats for {len(codes)} stocks...")
    batch = 50
    updated = 0

    for i in range(0, len(codes), batch):
        chunk = codes[i:i+batch]
        await asyncio.gather(*[_update(code, db, red) for code in chunk])
        updated += len(chunk)
        if updated % 200 == 0:
            logger.info(f"  {updated}/{len(codes)} done")
        await asyncio.sleep(0.05)

    logger.info(f"Stats update complete: {updated} stocks")
    await db.close()
    await red.aclose()


async def _update(code: str, db: asyncpg.Pool, red: redis_lib.Redis):
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT date, close, volume, amount, foreign_net_buy, inst_net_buy, short_sell_vol
            FROM daily_bars
            WHERE code = $1
            ORDER BY date DESC
            LIMIT 260
            """,
            code,
        )
    if not rows:
        return

    closes  = [r["close"]  for r in rows]
    volumes = [r["volume"] for r in rows]
    amounts = [r["amount"] or 0 for r in rows]

    pipe = red.pipeline()

    # 거래량 이동평균
    for n in [5, 20, 60]:
        if len(volumes) >= n:
            pipe.set(f"stats:{code}:avg_vol_{n}d", sum(volumes[:n])/n, ex=90000)

    # 거래대금 20일 평균
    if len(amounts) >= 20:
        pipe.set(f"stats:{code}:avg_amount_20d", sum(amounts[:20])/20, ex=90000)

    # 고가
    for n in [20, 65, 130, 260]:
        if len(closes) >= n:
            pipe.set(f"stats:{code}:high_{n}d", max(closes[:n]), ex=90000)

    # 수급 평균
    for field, col in [("foreign", "foreign_net_buy"), ("inst", "inst_net_buy")]:
        nets = [r[col] or 0 for r in rows[:20]]
        if nets:
            pipe.set(f"stats:{code}:avg_{field}_20d", sum(nets)/len(nets), ex=90000)

    # 공매도 추세
    shorts = [r["short_sell_vol"] or 0 for r in rows[:10]]
    if len(shorts) >= 5:
        recent = sum(shorts[:3]) / 3
        older  = sum(shorts[3:6]) / 3 + 0.001
        pipe.set(f"stats:{code}:short_increasing", int(recent > older), ex=90000)

    await pipe.execute()


if __name__ == "__main__":
    asyncio.run(main())
