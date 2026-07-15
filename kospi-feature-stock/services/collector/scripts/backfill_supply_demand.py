"""
수급 데이터 6개월 백필 스크립트.

Usage (inside fstock-collector-supply container):
    python scripts/backfill_supply_demand.py [--days 130] [--concurrency 2]

- KIS REST API 사용 (30일씩 청크)
- feature_events 보유 종목 우선, 나머지 supply_demand 보유 종목 순
- ON CONFLICT DO UPDATE 로 안전하게 UPSERT
"""
import asyncio
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import asyncpg
import redis.asyncio as redis_lib

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.writer import write_supply_demand
from kis.auth import KISAuthManager, KISConfig
from kis.rest_client import KISRestClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("supply-backfill")

CHUNK_DAYS = 30     # KIS API 최대 반환 일수
RATE_DELAY = 0.4    # 호출 간격 (초)
CONCURRENCY = 2     # 동시 종목 수


def _biz_days(since: date, until: date) -> list[str]:
    """since~until 사이 평일 목록 (YYYYMMDD 형식, 최신→과거 순)."""
    result = []
    d = until
    while d >= since:
        if d.weekday() < 5:
            result.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return result


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=130, help="백필할 거래일 수 (기본 130)")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY)
    args = parser.parse_args()

    _dsn = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    pool = await asyncpg.create_pool(
        dsn=_dsn, min_size=2, max_size=6,
        ssl="require" if "supabase" in _dsn else False,
    )
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    redis_client = redis_lib.from_url(redis_url, decode_responses=False)

    cfg = KISConfig(
        app_key=os.environ["KIS_APP_KEY"],
        app_secret=os.environ["KIS_APP_SECRET"],
        account_no=os.environ["KIS_ACCOUNT_NO"],
    )
    auth = KISAuthManager(cfg, redis_client)
    kis = KISRestClient(cfg, auth)

    today = date.today()
    since = today - timedelta(days=args.days * 2)  # 달력일 기준 여유

    # 백필 대상 날짜 목록 (최신→과거)
    all_biz = _biz_days(since, today - timedelta(days=1))
    # 최대 args.days 거래일만
    target_dates: list[str] = all_biz[:args.days]
    oldest_target = date.fromisoformat(
        target_dates[-1][:4] + "-" + target_dates[-1][4:6] + "-" + target_dates[-1][6:8]
    )
    logger.info(f"목표 기간: {oldest_target} ~ {today - timedelta(days=1)} ({len(target_dates)} 거래일)")

    # 대상 종목: feature_events 보유 종목 우선
    rows = await pool.fetch(
        """
        SELECT code FROM (
            SELECT code, 1 AS prio FROM feature_events GROUP BY code
            UNION ALL
            SELECT code, 2 AS prio FROM supply_demand GROUP BY code
        ) t
        GROUP BY code ORDER BY MIN(prio), code
        """
    )
    codes = [r["code"] for r in rows]
    logger.info(f"대상 종목: {len(codes)}개")

    # 기존 데이터 확인 — (code, yyyymmdd) 집합
    existing = await pool.fetch(
        "SELECT DISTINCT code, to_char(date,'YYYYMMDD') AS d FROM supply_demand WHERE date >= $1",
        oldest_target,
    )
    existing_set = {(r["code"], r["d"]) for r in existing}
    logger.info(f"기존 (code,date) 쌍: {len(existing_set):,}")

    # 누락 (code, 청크) 목록 구성
    work: list[tuple[str, str, str]] = []  # (code, chunk_start, chunk_end)
    for code in codes:
        missing = [d for d in target_dates if (code, d) not in existing_set]
        if not missing:
            continue
        # 30일씩 묶기 (missing은 최신→과거 정렬이므로 청크도 그 방향)
        for i in range(0, len(missing), CHUNK_DAYS):
            chunk = missing[i:i + CHUNK_DAYS]
            start_d, end_d = chunk[-1], chunk[0]   # 과거 날짜, 최신 날짜
            work.append((code, start_d, end_d))

    logger.info(f"처리할 청크: {len(work):,}개")
    if not work:
        logger.info("백필할 데이터 없음 — 완료")
        await pool.close()
        return

    sem = asyncio.Semaphore(args.concurrency)
    success, empty, fail = 0, 0, 0
    total = len(work)

    async def process(idx: int, code: str, start_d: str, end_d: str):
        nonlocal success, empty, fail
        async with sem:
            try:
                records = await kis.get_supply_demand_range(code, start_d, end_d)
                for rec in records:
                    await write_supply_demand(pool, rec)
                if records:
                    success += len(records)
                    if idx % 200 == 0:
                        logger.info(f"[{idx}/{total}] {code} {start_d}~{end_d}: +{len(records)}건 (누적 {success})")
                else:
                    empty += 1
            except Exception as e:
                fail += 1
                logger.debug(f"[{idx}] {code} {start_d}~{end_d}: {e}")
            await asyncio.sleep(RATE_DELAY)

    tasks = [process(i + 1, c, s, e) for i, (c, s, e) in enumerate(work)]
    await asyncio.gather(*tasks)

    logger.info(f"백필 완료 — success={success}건, empty={empty}청크, error={fail}청크")
    await pool.close()
    await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
