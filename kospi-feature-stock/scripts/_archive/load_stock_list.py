"""
전체 KOSPI/KOSDAQ 종목 리스트를 DB에 적재.
사용: python scripts/load_stock_list.py
"""
import asyncio
import asyncpg
import httpx
import orjson
import os
import redis.asyncio as redis_lib
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("load_stocks")

KRX_URL = "https://openapi.koreainvestment.com:9443"
STOCK_LIST_TRS = {
    "KOSPI":  ("FHKST03010100", "J"),
    "KOSDAQ": ("FHKST03010100", "Q"),
}


async def get_or_issue_token(red: redis_lib.Redis, app_key: str, app_secret: str) -> str:
    cached = await red.get("kis:access_token")
    if cached:
        token = cached.decode() if isinstance(cached, bytes) else cached
        if token:
            logger.info("KIS token loaded from Redis cache")
            return token

    logger.info("KIS token not cached, requesting new token...")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{KRX_URL}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": app_key,
                "appsecret": app_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        token = data["access_token"]
        ttl = data.get("expires_in", 86400) - 1800
        await red.setex("kis:access_token", max(ttl, 300), token)
        logger.info("KIS token issued and cached")
        return token


async def fetch_stock_list(market: str, tr_id: str, fid: str, token: str, app_key: str, app_secret: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{KRX_URL}/uapi/domestic-stock/v1/quotations/inquire-price-2",
            headers={
                "Content-Type": "application/json",
                "authorization": f"Bearer {token}",
                "appkey": app_key,
                "appsecret": app_secret,
                "tr_id": tr_id,
            },
            params={"FID_COND_MRKT_DIV_CODE": fid},
        )
        if resp.status_code != 200:
            logger.warning(f"Failed to fetch {market}: {resp.status_code} {resp.text[:200]}")
            return []
        data = resp.json()
        return data.get("output", [])


async def main():
    dsn = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    db  = await asyncpg.create_pool(dsn=dsn)
    red = redis_lib.from_url(os.environ["REDIS_URL"])

    app_key    = os.environ["KIS_APP_KEY"]
    app_secret = os.environ["KIS_APP_SECRET"]

    token = await get_or_issue_token(red, app_key, app_secret)

    inserted = 0
    codes_all = []

    for market, (tr_id, fid) in STOCK_LIST_TRS.items():
        stocks = await fetch_stock_list(market, tr_id, fid, token, app_key, app_secret)
        logger.info(f"{market}: {len(stocks)} stocks")
        for s in stocks:
            code = s.get("mksc_shrn_iscd") or s.get("shtn_iscd", "")
            name = s.get("hts_kor_isnm", "")
            if not code or not name:
                continue
            codes_all.append(code)
            async with db.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO stocks (code, name, market, is_active)
                    VALUES ($1, $2, $3, TRUE)
                    ON CONFLICT (code) DO UPDATE SET
                        name=EXCLUDED.name,
                        market=EXCLUDED.market,
                        updated_at=NOW()
                    """,
                    code, name, market,
                )
            inserted += 1

    await red.set("stocks:active_codes", orjson.dumps(codes_all), ex=86400)
    logger.info(f"Loaded {inserted} stocks -> Redis cached {len(codes_all)} codes")

    await db.close()
    await red.aclose()


if __name__ == "__main__":
    asyncio.run(main())
