"""
KIS API inquire-price(FHKST01010100)로 stocks.market='UNKNOWN' 종목 일괄 보정.
응답의 rprs_mrkt_kor_name 필드 → 'KOSPI'/'코스닥'/'KONEX' 매핑.

사용: docker compose run --rm collector python /app/scripts/update_markets_by_kis.py
     docker compose run --rm collector python /app/scripts/update_markets_by_kis.py --all
"""
import asyncio
import asyncpg
import httpx
import logging
import os
import sys

import redis.asyncio as redis_lib

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("kis_market")

KRX_URL  = "https://openapi.koreainvestment.com:9443"
# 코스닥 한글명 → KOSDAQ
# rprs_mrkt_kor_name 예시: KOSPI, KOSPI200, 코스닥, KSQ150, 코스닥150, KONEX, 코넥스
def _parse_market(kor_name: str) -> str | None:
    if not kor_name:
        return None
    n = kor_name.upper()
    if n.startswith("KOSPI") or n.startswith("코스피"):
        return "KOSPI"
    if n.startswith("KSQ") or n.startswith("코스닥"):
        return "KOSDAQ"
    if n.startswith("KONEX") or n.startswith("코넥스"):
        return "KONEX"
    return None
SEM_LIMIT = 10   # 동시 요청 수
DELAY_SEC = 0.06 # 초당 ~16 요청 (KIS 제한 20/s 이하)


async def get_token(red: redis_lib.Redis, app_key: str, app_secret: str) -> str:
    cached = await red.get("kis:access_token")
    if cached:
        return cached.decode() if isinstance(cached, bytes) else cached
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{KRX_URL}/oauth2/tokenP",
                         json={"grant_type": "client_credentials",
                               "appkey": app_key, "appsecret": app_secret})
        r.raise_for_status()
        data  = r.json()
        token = data["access_token"]
        ttl   = max(data.get("expires_in", 86400) - 1800, 300)
        await red.setex("kis:access_token", ttl, token)
        return token


async def fetch_market(client: httpx.AsyncClient, token: str,
                       app_key: str, app_secret: str,
                       code: str, sem: asyncio.Semaphore) -> tuple[str, str | None]:
    async with sem:
        await asyncio.sleep(DELAY_SEC)
        try:
            r = await client.get(
                f"{KRX_URL}/uapi/domestic-stock/v1/quotations/inquire-price",
                headers={
                    "authorization": f"Bearer {token}",
                    "appkey": app_key,
                    "appsecret": app_secret,
                    "tr_id": "FHKST01010100",
                },
                params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("rt_cd") == "0":
                    kor_name = data.get("output", {}).get("rprs_mrkt_kor_name", "")
                    market   = _parse_market(kor_name)
                    return code, market
        except Exception as e:
            logger.debug(f"{code} error: {e}")
    return code, None


async def main() -> None:
    update_all = "--all" in sys.argv
    app_key    = os.environ["KIS_APP_KEY"]
    app_secret = os.environ["KIS_APP_SECRET"]
    dsn        = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    redis_url  = os.environ["REDIS_URL"]

    red = redis_lib.from_url(redis_url)
    db  = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=5)

    if update_all:
        rows = await db.fetch("SELECT code FROM stocks ORDER BY code")
    else:
        rows = await db.fetch("SELECT code FROM stocks WHERE market='UNKNOWN' ORDER BY code")
    codes = [r["code"] for r in rows]
    logger.info(f"대상: {len(codes)}개 종목")
    if not codes:
        await db.close(); await red.aclose(); return

    token = await get_token(red, app_key, app_secret)
    sem   = asyncio.Semaphore(SEM_LIMIT)

    results: list[tuple[str, str]] = []
    async with httpx.AsyncClient(timeout=15) as client:
        tasks = [fetch_market(client, token, app_key, app_secret, c, sem) for c in codes]
        done  = 0
        for coro in asyncio.as_completed(tasks):
            code, market = await coro
            if market:
                results.append((market, code))
            done += 1
            if done % 200 == 0:
                logger.info(f"진행: {done}/{len(codes)} (매핑 성공: {len(results)})")

    for i in range(0, len(results), 500):
        async with db.acquire() as conn:
            await conn.executemany(
                "UPDATE stocks SET market=$1, updated_at=NOW() WHERE code=$2",
                results[i:i+500],
            )

    await db.close()
    await red.aclose()

    mkt_count: dict[str, int] = {}
    for m, _ in results:
        mkt_count[m] = mkt_count.get(m, 0) + 1
    logger.info(f"완료. 업데이트: {len(results)}개 | {mkt_count}")


if __name__ == "__main__":
    asyncio.run(main())
