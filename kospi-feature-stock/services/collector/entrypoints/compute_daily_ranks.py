"""
장 마감 후 단면(cross-sectional) 랭크 피처 계산 → Redis 저장.

저장 키: ranks:{YYYYMMDD}:{code}  (hash: rank_return_5d, rank_vol_ratio, rank_foreign_net, rank_rsi14)
TTL: 2일 (다음날 intraday-poller까지 유효)

목적: 학습 시 groupby("__date").rank(pct=True)로 계산한 단면 랭크와 추론 시 0.5 고정값 사이의
      train-test mismatch 해소 → AUC +0.02~0.04 기대.
"""
import asyncio
import logging
import os
from datetime import date

import asyncpg
import redis.asyncio as aioredis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("daily-ranks")


async def main() -> None:
    dsn = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    redis_url = os.environ["REDIS_URL"]

    pool = await asyncpg.create_pool(
        dsn=dsn, min_size=2, max_size=5, statement_cache_size=0,
    )
    redis_cli = aioredis.from_url(redis_url, decode_responses=True)

    today = date.today()
    today_str = today.strftime("%Y%m%d")
    logger.info(f"[daily-ranks] {today_str} 단면 랭크 계산 시작...")

    try:
        rows = await pool.fetch(
            """
            WITH latest AS (
                SELECT DISTINCT ON (d.code)
                    d.code,
                    d.close,
                    d.volume,
                    d.rsi14,
                    d.date AS trade_date
                FROM daily_bars d
                WHERE d.date <= $1
                  AND d.date >= $1 - INTERVAL '5 days'
                  AND d.close > 0
                  AND d.code NOT IN ('0001', '1001')
                ORDER BY d.code, d.date DESC
            ),
            p5 AS (
                SELECT DISTINCT ON (code) code, close AS close_5d
                FROM daily_bars
                WHERE date <= $1 - INTERVAL '5 days'
                  AND close > 0
                  AND code NOT IN ('0001', '1001')
                ORDER BY code, date DESC
            ),
            v20 AS (
                SELECT code, AVG(volume) AS avg_vol
                FROM (
                    SELECT code, volume,
                           ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) AS rn
                    FROM daily_bars
                    WHERE date <= $1 AND date >= $1 - INTERVAL '30 days'
                      AND code NOT IN ('0001', '1001')
                ) sub
                WHERE rn <= 20
                GROUP BY code
            ),
            a20 AS (
                SELECT code, AVG(amount) AS avg_amt
                FROM (
                    SELECT code, amount,
                           ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) AS rn
                    FROM daily_bars
                    WHERE date <= $1 AND date >= $1 - INTERVAL '30 days'
                      AND code NOT IN ('0001', '1001')
                ) sub
                WHERE rn <= 20
                GROUP BY code
            ),
            f5sum AS (
                SELECT code, SUM(COALESCE(foreign_net_buy, 0)) AS fnet5
                FROM (
                    SELECT code, foreign_net_buy,
                           ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) AS rn
                    FROM daily_bars
                    WHERE date <= $1 AND date >= $1 - INTERVAL '10 days'
                      AND code NOT IN ('0001', '1001')
                ) sub
                WHERE rn <= 5
                GROUP BY code
            )
            SELECT
                l.code,
                CASE WHEN p5.close_5d > 0
                     THEN (l.close / p5.close_5d - 1) * 100
                     ELSE 0.0
                END AS return_5d,
                CASE WHEN v20.avg_vol > 0
                     THEN l.volume::float / v20.avg_vol
                     ELSE 1.0
                END AS vol_ratio_20d,
                CASE WHEN a20.avg_amt > 0
                     THEN COALESCE(f5sum.fnet5, 0) / a20.avg_amt
                     ELSE 0.0
                END AS foreign_net_ratio,
                COALESCE(l.rsi14, 50.0) AS rsi14
            FROM latest l
            LEFT JOIN p5     ON p5.code     = l.code
            LEFT JOIN v20    ON v20.code    = l.code
            LEFT JOIN a20    ON a20.code    = l.code
            LEFT JOIN f5sum  ON f5sum.code  = l.code
            """,
            today,
        )

        if not rows:
            logger.warning("[daily-ranks] 오늘 데이터 없음 — 스킵")
            return

        logger.info(f"[daily-ranks] {len(rows)}개 종목 조회 완료")

        import pandas as pd

        df = pd.DataFrame([dict(r) for r in rows])
        for col in ["return_5d", "vol_ratio_20d", "foreign_net_ratio", "rsi14"]:
            df[col] = df[col].astype(float).fillna(0.0)

        df["rank_return_5d"]   = df["return_5d"].rank(pct=True).fillna(0.5)
        df["rank_vol_ratio"]   = df["vol_ratio_20d"].rank(pct=True).fillna(0.5)
        df["rank_foreign_net"] = df["foreign_net_ratio"].rank(pct=True).fillna(0.5)
        df["rank_rsi14"]       = df["rsi14"].rank(pct=True).fillna(0.5)

        pipe = redis_cli.pipeline()
        for _, row in df.iterrows():
            key = f"ranks:{today_str}:{row['code']}"
            pipe.hset(key, mapping={
                "rank_return_5d":   round(float(row["rank_return_5d"]),   4),
                "rank_vol_ratio":   round(float(row["rank_vol_ratio"]),   4),
                "rank_foreign_net": round(float(row["rank_foreign_net"]), 4),
                "rank_rsi14":       round(float(row["rank_rsi14"]),       4),
            })
            pipe.expire(key, 172800)  # 2일 TTL
        await pipe.execute()

        logger.info(f"[daily-ranks] {len(df)}개 종목 랭크 저장 완료 (ranks:{today_str}:*)")

    finally:
        await pool.close()
        await redis_cli.aclose()


if __name__ == "__main__":
    asyncio.run(main())
