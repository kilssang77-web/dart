"""
일봉 + 수급 초기 백필 스크립트.
KIS API는 일봉 최대 100건/호출 → 1년치(약 250 거래일) = 3회 분할 호출.

사용:
  docker compose run --rm collector python /app/scripts/backfill_daily_bars.py --days 365
  docker compose run --rm collector python /app/scripts/backfill_daily_bars.py --days 365 --supply
"""
import asyncio
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta

import asyncpg
import httpx
import redis.asyncio as redis_lib

sys.path.insert(0, "/app")
from db.writer import write_daily_bars

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("backfill")

_KIS_BASE    = "https://openapi.koreainvestment.com:9443"
_CHUNK_DAYS  = 120   # KIS 1회 호출 최대 약 100거래일 ≈ 140 캘린더일, 여유있게 120일


async def get_token(client: httpx.AsyncClient) -> str:
    r = redis_lib.from_url(os.environ["REDIS_URL"])
    cached = await r.get("kis:access_token")
    await r.aclose()
    if cached:
        return cached.decode()
    resp = await client.post(
        f"{_KIS_BASE}/oauth2/tokenP",
        json={
            "grant_type": "client_credentials",
            "appkey":     os.environ["KIS_APP_KEY"],
            "appsecret":  os.environ["KIS_APP_SECRET"],
        },
    )
    return resp.json().get("access_token", "")


async def fetch_daily_bars_chunk(
    client: httpx.AsyncClient,
    headers: dict,
    code: str,
    start: str,
    end: str,
) -> list[dict]:
    """KIS FHKST03010100 일봉 (최대 100건/호출)."""
    try:
        resp = await client.get(
            f"{_KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            headers={**headers, "tr_id": "FHKST03010100"},
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD":         code,
                "FID_INPUT_DATE_1":       start,
                "FID_INPUT_DATE_2":       end,
                "FID_PERIOD_DIV_CODE":    "D",
                "FID_ORG_ADJ_PRC":        "0",
            },
        )
        d = resp.json()
        if d.get("rt_cd") != "0":
            logger.warning(f"[{code}] daily bars API: {d.get('msg1')}")
            return []
        return [
            {
                "code":        code,
                "date":        r.get("stck_bsop_date"),
                "open":        int(r.get("stck_oprc",   0) or 0),
                "high":        int(r.get("stck_hgpr",   0) or 0),
                "low":         int(r.get("stck_lwpr",   0) or 0),
                "close":       int(r.get("stck_clpr",   0) or 0),
                "volume":      int(r.get("acml_vol",    0) or 0),
                "amount":      int(r.get("acml_tr_pbmn", 0) or 0),
                "change_rate": float(r.get("prdy_ctrt", 0) or 0),
            }
            for r in d.get("output2", [])
            if r.get("stck_clpr")
        ]
    except Exception as e:
        logger.error(f"[{code}] fetch_daily_bars error: {e}")
        return []


async def fetch_daily_bars(
    client: httpx.AsyncClient,
    headers: dict,
    code: str,
    total_days: int,
) -> list[dict]:
    """1년치 일봉: _CHUNK_DAYS씩 분할 호출 후 병합."""
    now = datetime.now()
    all_bars: dict[str, dict] = {}   # date → bar (dedup)

    # 과거부터 현재 방향으로 청크 분리
    chunks = []
    end_dt = now
    while (now - end_dt).days < total_days:
        start_dt = end_dt - timedelta(days=_CHUNK_DAYS)
        chunks.append((start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d")))
        end_dt = start_dt - timedelta(days=1)
        if (now - end_dt).days >= total_days:
            break

    for start, end in chunks:
        bars = await fetch_daily_bars_chunk(client, headers, code, start, end)
        for b in bars:
            all_bars[b["date"]] = b
        await asyncio.sleep(0.2)

    return list(all_bars.values())


async def fetch_supply_demand_chunk(
    client: httpx.AsyncClient,
    headers: dict,
    code: str,
    start: str,
    end: str,
) -> list[dict]:
    """KIS FHKST01010900 수급 (최대 100건/호출)."""
    try:
        resp = await client.get(
            f"{_KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-investor",
            headers={**headers, "tr_id": "FHKST01010900"},
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD":         code,
                "FID_INPUT_DATE_1":       start,
                "FID_INPUT_DATE_2":       end,
                "FID_PERIOD_DIV_CODE":    "D",
            },
        )
        d = resp.json()
        if d.get("rt_cd") != "0":
            logger.warning(f"[{code}] supply API: {d.get('msg1')}")
            return []
        result = []
        for r in d.get("output2", []) or d.get("output", []):
            dt = r.get("stck_bsop_date") or r.get("bsop_date")
            if not dt:
                continue
            result.append({
                "code":         code,
                "date":         dt,
                "foreign_net":  int(r.get("frgn_ntby_qty", 0) or 0),
                "inst_net":     int(r.get("orgn_ntby_qty", 0) or 0),
                "indiv_net":    int(r.get("indv_ntby_qty",  0) or 0),
                "foreign_hold_rate": float(r.get("frgn_hldn_qty", 0) or 0),
            })
        return result
    except Exception as e:
        logger.error(f"[{code}] fetch_supply error: {e}")
        return []


async def fetch_supply_demand(
    client: httpx.AsyncClient,
    headers: dict,
    code: str,
    total_days: int,
) -> list[dict]:
    """수급 데이터 분할 호출 후 병합."""
    now = datetime.now()
    all_rows: dict[str, dict] = {}

    chunks = []
    end_dt = now
    while (now - end_dt).days < total_days:
        start_dt = end_dt - timedelta(days=_CHUNK_DAYS)
        chunks.append((start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d")))
        end_dt = start_dt - timedelta(days=1)
        if (now - end_dt).days >= total_days:
            break

    for start, end in chunks:
        rows = await fetch_supply_demand_chunk(client, headers, code, start, end)
        for r in rows:
            all_rows[r["date"]] = r
        await asyncio.sleep(0.2)

    return list(all_rows.values())


async def write_supply_demand(pool: asyncpg.Pool, rows: list[dict]) -> int:
    if not rows:
        return 0
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO supply_demand (code, date, foreign_net, inst_net, indiv_net, foreign_hold_rate)
            VALUES ($1, $2::date, $3, $4, $5, $6)
            ON CONFLICT (code, date) DO UPDATE SET
                foreign_net  = EXCLUDED.foreign_net,
                inst_net     = EXCLUDED.inst_net,
                indiv_net    = EXCLUDED.indiv_net,
                foreign_hold_rate = EXCLUDED.foreign_hold_rate
            """,
            [
                (r["code"], r["date"], r["foreign_net"], r["inst_net"],
                 r["indiv_net"], r.get("foreign_hold_rate"))
                for r in rows
            ],
        )
    return len(rows)


async def update_redis_stats(pool: asyncpg.Pool, redis: redis_lib.Redis, codes: list[str]):
    """일봉 기반 Redis 통계 갱신."""
    ex = 90_000
    updated = 0
    for code in codes:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT close, volume, amount, foreign_net_buy, inst_net_buy, short_sell_vol
                FROM daily_bars WHERE code=$1 ORDER BY date DESC LIMIT 280
                """,
                code,
            )
        if not rows:
            continue

        closes  = [r["close"]  for r in rows]
        volumes = [r["volume"] for r in rows]
        amounts = [r["amount"] or 0 for r in rows]

        pipe = redis.pipeline()
        for n in [5, 20, 60]:
            if len(volumes) >= n:
                pipe.set(f"stats:{code}:avg_vol_{n}d",   sum(volumes[:n]) / n, ex=ex)
        if len(amounts) >= 20:
            pipe.set(f"stats:{code}:avg_amount_20d", sum(amounts[:20]) / 20, ex=ex)
        for days in [20, 65, 130, 260]:
            if len(closes) >= days:
                pipe.set(f"stats:{code}:high_{days}d", max(closes[:days]), ex=ex)
        for field, col in [("foreign", "foreign_net_buy"), ("inst", "inst_net_buy")]:
            nets = [r[col] or 0 for r in rows[:20]]
            if nets:
                pipe.set(f"stats:{code}:avg_{field}_20d", sum(nets) / len(nets), ex=ex)
        shorts = [r["short_sell_vol"] or 0 for r in rows[:10]]
        if len(shorts) >= 6:
            recent = sum(shorts[:3]) / 3
            older  = sum(shorts[3:6]) / 3 + 1
            pipe.set(f"stats:{code}:short_increasing", int(recent > older), ex=ex)
        await pipe.execute()
        updated += 1

    logger.info(f"Redis 통계 갱신 완료: {updated}/{len(codes)} 종목")


async def main(days: int, include_supply: bool):
    dsn   = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    pool  = await asyncpg.create_pool(dsn=dsn, min_size=3, max_size=10)
    redis = redis_lib.from_url(os.environ["REDIS_URL"])

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT code FROM stocks WHERE is_active=TRUE AND is_trading_halt=FALSE ORDER BY code"
        )
    codes = [r["code"] for r in rows]
    logger.info(f"백필 대상: {len(codes)} 종목 / 기간: 최근 {days}일")

    async with httpx.AsyncClient(timeout=30) as client:
        token = await get_token(client)
        if not token:
            logger.error("토큰 발급 실패")
            return

        headers = {
            "authorization": f"Bearer {token}",
            "appkey":        os.environ["KIS_APP_KEY"],
            "appsecret":     os.environ["KIS_APP_SECRET"],
            "custtype":      "P",
        }

        sem = asyncio.Semaphore(3)
        total_bars = 0
        total_sd   = 0

        async def process(code: str):
            nonlocal total_bars, total_sd
            async with sem:
                try:
                    bars = await fetch_daily_bars(client, headers, code, days)
                    if bars:
                        n = await write_daily_bars(pool, bars)
                        total_bars += n
                    if include_supply:
                        sd = await fetch_supply_demand(client, headers, code, days)
                        if sd:
                            n2 = await write_supply_demand(pool, sd)
                            total_sd += n2
                    logger.info(f"  {code}: 일봉 {len(bars)}건" +
                                (f" / 수급 {len(sd) if include_supply else 0}건" if include_supply else ""))
                except Exception as e:
                    logger.error(f"  {code} 오류: {e}")

        batch_size = 10
        for i in range(0, len(codes), batch_size):
            await asyncio.gather(*[process(c) for c in codes[i:i+batch_size]])
            logger.info(f"진행: {min(i+batch_size, len(codes))}/{len(codes)} 종목")

    logger.info(f"\n일봉 저장 완료: {total_bars}건" +
                (f" / 수급 저장: {total_sd}건" if include_supply else ""))
    logger.info("Redis 통계 갱신 중...")
    await update_redis_stats(pool, redis, codes)
    await pool.close()
    await redis.aclose()
    logger.info("백필 완료.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days",   type=int,  default=365, help="수집 기간(일), 기본값 365")
    parser.add_argument("--supply", action="store_true",    help="수급 데이터도 백필")
    args = parser.parse_args()
    asyncio.run(main(args.days, args.supply))
