"""
stocks 테이블의 industry, shares_total, par_value 컬럼을
KIS inquire-price(FHKST01010100) 응답으로 일괄 보정.

추출 필드:
  bstp_kor_isnm      -> industry (업종명)
  stck_lstg_totl_cnt -> shares_total (상장주식수)
  stck_fcam          -> par_value (액면가)

사용:
  docker compose run --rm collector-tick python /app/scripts/update_stock_info.py
  docker compose run --rm collector-tick python /app/scripts/update_stock_info.py --all
"""
import asyncio
import asyncpg
import httpx
import logging
import os
import sys

import redis.asyncio as redis_lib

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("update_stock_info")

KRX_URL    = os.getenv("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443")
SEM_LIMIT  = 8
DELAY_SEC  = 0.12

MARKET_CODE = {"KOSPI": "J", "KOSDAQ": "Q", "KONEX": "N"}


async def get_token(red: redis_lib.Redis, app_key: str, app_secret: str) -> str:
    cached = await red.get("kis:access_token")
    if cached:
        return cached.decode() if isinstance(cached, bytes) else cached
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{KRX_URL}/oauth2/tokenP",
            json={"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret},
        )
        r.raise_for_status()
        data  = r.json()
        token = data["access_token"]
        ttl   = max(data.get("expires_in", 86400) - 1800, 300)
        await red.setex("kis:access_token", ttl, token)
        return token


async def fetch_info(
    client: httpx.AsyncClient,
    token: str,
    app_key: str,
    app_secret: str,
    code: str,
    market: str,
    sem: asyncio.Semaphore,
) -> dict | None:
    mkt_code = MARKET_CODE.get(market, "J")
    async with sem:
        await asyncio.sleep(DELAY_SEC)
        for mkt in dict.fromkeys([mkt_code, "J", "Q"]):
            try:
                r = await client.get(
                    f"{KRX_URL}/uapi/domestic-stock/v1/quotations/inquire-price",
                    headers={
                        "authorization": f"Bearer {token}",
                        "appkey": app_key,
                        "appsecret": app_secret,
                        "tr_id": "FHKST01010100",
                    },
                    params={"FID_COND_MRKT_DIV_CODE": mkt, "FID_INPUT_ISCD": code},
                    timeout=10,
                )
                if r.status_code != 200:
                    continue
                data = r.json()
                if data.get("rt_cd") != "0":
                    continue
                o = data.get("output", {})
                if not o:
                    continue

                industry = (o.get("bstp_kor_isnm") or "").strip() or None

                raw_shares = o.get("lstn_stcn", "")
                try:
                    shares_total = int(raw_shares) if raw_shares and str(raw_shares).strip() else None
                except (ValueError, TypeError):
                    shares_total = None

                raw_par = o.get("stck_fcam", "")
                try:
                    par_value = int(raw_par) if raw_par and str(raw_par).strip() else None
                except (ValueError, TypeError):
                    par_value = None

                if industry or shares_total:
                    return {"code": code, "industry": industry,
                            "shares_total": shares_total, "par_value": par_value}
            except Exception as e:
                logger.debug(f"{code}/{mkt} error: {e}")
    return None


async def main() -> None:
    update_all = "--all" in sys.argv
    app_key    = os.environ["KIS_APP_KEY"]
    app_secret = os.environ["KIS_APP_SECRET"]
    dsn        = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    redis_url  = os.environ["REDIS_URL"]

    red = redis_lib.from_url(redis_url)
    db  = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=5, ssl="require" if "supabase" in dsn else False, statement_cache_size=0)

    if update_all:
        rows = await db.fetch(
            "SELECT code, market FROM stocks WHERE market NOT IN ('UNKNOWN','ETC') ORDER BY code"
        )
    else:
        rows = await db.fetch(
            """SELECT code, market FROM stocks
               WHERE market NOT IN ('UNKNOWN','ETC')
                 AND (industry IS NULL OR shares_total IS NULL)
               ORDER BY code"""
        )
    targets = [(r["code"], r["market"]) for r in rows]
    logger.info(f"조회 대상: {len(targets)}개 종목")
    if not targets:
        await db.close(); await red.aclose(); return

    token = await get_token(red, app_key, app_secret)
    logger.info("KIS 토큰 발급 완료")

    sem = asyncio.Semaphore(SEM_LIMIT)
    results: list[dict] = []

    async with httpx.AsyncClient(timeout=15) as client:
        tasks = [
            fetch_info(client, token, app_key, app_secret, code, market, sem)
            for code, market in targets
        ]
        done = 0
        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result:
                results.append(result)
            done += 1
            if done % 200 == 0:
                logger.info(f"  진행: {done}/{len(targets)}  수집: {len(results)}")

    logger.info(f"수집 완료: {len(results)}개")

    updates = [
        (r["industry"], r["shares_total"], r["par_value"], r["code"])
        for r in results
    ]
    for i in range(0, len(updates), 500):
        async with db.acquire() as conn:
            await conn.executemany(
                """UPDATE stocks
                   SET industry     = COALESCE($1, industry),
                       shares_total = COALESCE($2, shares_total),
                       par_value    = COALESCE($3, par_value),
                       updated_at   = NOW()
                   WHERE code = $4""",
                updates[i:i+500],
            )

    await db.close()
    await red.aclose()
    logger.info(f"업데이트 완료: {len(updates)}개")


if __name__ == "__main__":
    asyncio.run(main())
