"""
Historical daily-bar backfill script.

Usage (inside collector container or locally with env vars set):
    python scripts/backfill_history.py [--start 20200101] [--end 20250917]
                                       [--codes 005930,000660] [--concurrency 3]
                                       [--checkpoint /tmp/backfill_ckpt.json]

- Fetches KIS daily bars in 90-day chunks (API returns max ~100 bars/call)
- Writes each chunk to daily_bars via write_daily_bars()
- _update_technical_indicators() is called automatically per stock on each batch
- Checkpoint file tracks completed codes; rerun safely resumes
"""
import asyncio
import json
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import asyncpg
import redis.asyncio as redis_lib

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.writer import write_daily_bars
from kis.auth import KISAuthManager, KISConfig
from kis.rest_client import KISRestClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("backfill")

CHUNK_DAYS   = 90   # trading-day approximation per API call
RATE_DELAY   = 0.22  # seconds between calls per worker (≈ 4.5 req/s/worker)


def _date_chunks(start: date, end: date, chunk: int = CHUNK_DAYS):
    """Yield (chunk_start, chunk_end) pairs covering [start, end] inclusive."""
    cur = start
    while cur <= end:
        nxt = min(cur + timedelta(days=chunk - 1), end)
        yield cur, nxt
        cur = nxt + timedelta(days=1)


async def _backfill_code(
    code: str,
    start: date,
    end: date,
    kis: KISRestClient,
    pool: asyncpg.Pool,
    sem: asyncio.Semaphore,
) -> int:
    total = 0
    for chunk_start, chunk_end in _date_chunks(start, end):
        s = chunk_start.strftime("%Y%m%d")
        e = chunk_end.strftime("%Y%m%d")
        async with sem:
            bars = await kis.get_daily_bars(code, s, e)
            await asyncio.sleep(RATE_DELAY)
        if bars:
            n = await write_daily_bars(pool, bars)
            total += n
    return total


async def _get_all_codes(pool: asyncpg.Pool) -> list[str]:
    """Return distinct codes already in daily_bars, oldest-date first (priority: needs most backfill)."""
    rows = await pool.fetch(
        "SELECT code FROM daily_bars GROUP BY code ORDER BY MIN(date) DESC"
    )
    return [r["code"] for r in rows]


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start",       default="20200101")
    parser.add_argument("--end",         default=None,
                        help="default: day before current oldest bar")
    parser.add_argument("--codes",       default=None,
                        help="comma-separated code list (default: all in DB)")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--checkpoint",  default="/tmp/backfill_ckpt.json")
    parser.add_argument("--index-only",  action="store_true",
                        help="backfill only KOSPI(0001)/KOSDAQ(1001) index bars using get_index_bars")
    args = parser.parse_args()

    start = date.fromisoformat(
        args.start[:4] + "-" + args.start[4:6] + "-" + args.start[6:8]
    )

    _dsn = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    pool = await asyncpg.create_pool(
        dsn=_dsn, min_size=2, max_size=8,
        ssl="require" if "supabase" in _dsn else False,
        statement_cache_size=0,
    )
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    redis_client = redis_lib.from_url(redis_url, decode_responses=False)

    # Determine end date
    if args.end:
        end = date.fromisoformat(
            args.end[:4] + "-" + args.end[4:6] + "-" + args.end[6:8]
        )
    else:
        row = await pool.fetchrow("SELECT MIN(date) as oldest FROM daily_bars")
        oldest = row["oldest"]
        end = (oldest - timedelta(days=1)) if oldest else date(2025, 9, 17)

    logger.info(f"Backfill range: {start} → {end}")

    # ── KOSPI/KOSDAQ 지수 백필 (--index-only) ──────────────────────
    if args.index_only:
        logger.info("Index-only mode: backfilling KOSPI(0001) and KOSDAQ(1001)")
        cfg = KISConfig(
            app_key=os.environ["KIS_APP_KEY"],
            app_secret=os.environ["KIS_APP_SECRET"],
            account_no=os.environ["KIS_ACCOUNT_NO"],
        )
        auth = KISAuthManager(cfg, redis_client)
        kis  = KISRestClient(cfg, auth)
        sem  = asyncio.Semaphore(1)
        for mkt_code in ["0001", "1001"]:
            total = 0
            for chunk_start, chunk_end in _date_chunks(start, end if args.end else date.today()):
                s = chunk_start.strftime("%Y%m%d")
                e_str = chunk_end.strftime("%Y%m%d")
                async with sem:
                    bars = await kis.get_index_bars(mkt_code, s, e_str)
                    await asyncio.sleep(RATE_DELAY)
                if bars:
                    n = await write_daily_bars(pool, bars)
                    total += n
            logger.info(f"Index {mkt_code}: {total} bars inserted/updated ({start} ~ end)")
        await pool.close()
        return

    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    else:
        codes = await _get_all_codes(pool)

    logger.info(f"Total codes to backfill: {len(codes)}")

    # Checkpoint
    ckpt_path = Path(args.checkpoint)
    done: set[str] = set()
    if ckpt_path.exists():
        done = set(json.loads(ckpt_path.read_text()).get("done", []))
        logger.info(f"Resuming — {len(done)} codes already done")

    cfg = KISConfig(
        app_key=os.environ["KIS_APP_KEY"],
        app_secret=os.environ["KIS_APP_SECRET"],
        account_no=os.environ["KIS_ACCOUNT_NO"],
    )
    auth = KISAuthManager(cfg, redis_client)
    kis  = KISRestClient(cfg, auth)

    sem        = asyncio.Semaphore(args.concurrency)
    remaining  = [c for c in codes if c not in done]
    total_bars = 0

    async def process(code: str, idx: int):
        nonlocal total_bars
        try:
            n = await _backfill_code(code, start, end, kis, pool, sem)
            total_bars += n
            done.add(code)
            if idx % 20 == 0 or n > 0:
                logger.info(f"[{idx}/{len(remaining)}] {code}: +{n} bars (cumulative {total_bars})")
        except Exception as e:
            logger.warning(f"[{idx}] {code} failed: {e}")
        # Save checkpoint every 10 codes
        if idx % 10 == 0:
            ckpt_path.write_text(json.dumps({"done": list(done)}))

    tasks = [process(c, i + 1) for i, c in enumerate(remaining)]
    await asyncio.gather(*tasks)

    ckpt_path.write_text(json.dumps({"done": list(done)}))
    logger.info(f"Backfill complete — {total_bars} total bars inserted/updated for {len(done)} codes")

    await pool.close()
    await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
