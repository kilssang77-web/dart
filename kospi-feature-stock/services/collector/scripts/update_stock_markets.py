"""
stocks 테이블의 market='UNKNOWN' 종목을 DART company API로 일괄 보정.
corp_cls 매핑: Y→KOSPI  K→KOSDAQ  N→KONEX  E→ETC

환경변수: POSTGRES_DSN, DART_API_KEY
사용:
  docker compose run --rm collector python /app/scripts/update_stock_markets.py
  docker compose run --rm collector python /app/scripts/update_stock_markets.py --all
"""
import asyncio
import asyncpg
import httpx
import io
import logging
import os
import sys
import xml.etree.ElementTree as ET
import zipfile

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s - %(message)s")
logger = logging.getLogger("update_markets")

DART_API    = "https://opendart.fss.or.kr/api"
CLS_MAP     = {"Y": "KOSPI", "K": "KOSDAQ", "N": "KONEX", "E": "ETC"}
CONCURRENCY = 8
DELAY_SEC   = 0.3


async def download_corp_code_map(api_key: str) -> dict[str, str]:
    logger.info("DART corpCode.xml 다운로드 중...")
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(f"{DART_API}/corpCode.xml", params={"crtfc_key": api_key})
        resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        xml_content = z.read(z.namelist()[0])
    root = ET.fromstring(xml_content)
    mapping: dict[str, str] = {}
    for item in root.findall("list"):
        stock_code = (item.findtext("stock_code") or "").strip()
        corp_code  = (item.findtext("corp_code")  or "").strip()
        if stock_code and len(stock_code) == 6 and corp_code:
            mapping[stock_code] = corp_code
    logger.info(f"corpCode.xml: {len(mapping)}개 매핑 로드")
    return mapping


async def fetch_market(client, api_key, stock_code, corp_code, sem):
    async with sem:
        try:
            resp = await client.get(
                f"{DART_API}/company.json",
                params={"crtfc_key": api_key, "corp_code": corp_code},
            )
            if resp.status_code == 200:
                cls = resp.json().get("corp_cls", "")
                return stock_code, CLS_MAP.get(cls, "UNKNOWN")
        except Exception as e:
            logger.debug(f"company.json error {stock_code}: {e}")
        await asyncio.sleep(DELAY_SEC)
    return stock_code, "UNKNOWN"


async def main():
    update_all = "--all" in sys.argv
    api_key    = os.environ.get("DART_API_KEY", "")
    dsn        = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    if not api_key:
        logger.error("DART_API_KEY 환경변수 미설정")
        return

    db = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=5)
    if update_all:
        rows = await db.fetch("SELECT code FROM stocks ORDER BY code")
    else:
        rows = await db.fetch("SELECT code FROM stocks WHERE market = 'UNKNOWN' ORDER BY code")
    target_codes = [r["code"] for r in rows]
    logger.info(f"보정 대상: {len(target_codes)}개 종목")
    if not target_codes:
        await db.close()
        return

    corp_map = await download_corp_code_map(api_key)
    to_query = [(c, corp_map[c]) for c in target_codes if c in corp_map]
    logger.info(f"DART company.json 조회 예정: {len(to_query)}개")

    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(timeout=15) as client:
        tasks = [fetch_market(client, api_key, sc, cc, sem) for sc, cc in to_query]
        results, done = [], 0
        for coro in asyncio.as_completed(tasks):
            code, market = await coro
            results.append((code, market))
            done += 1
            if done % 200 == 0:
                logger.info(f"진행: {done}/{len(to_query)}")

    updates = [(market, code) for code, market in results if market != "UNKNOWN"]
    for i in range(0, len(updates), 500):
        async with db.acquire() as conn:
            await conn.executemany(
                "UPDATE stocks SET market=$1, updated_at=NOW() WHERE code=$2",
                updates[i : i + 500],
            )
    await db.close()
    mkt_count: dict[str, int] = {}
    for _, m in results:
        mkt_count[m] = mkt_count.get(m, 0) + 1
    logger.info(f"완료. 업데이트: {len(updates)}개 | {mkt_count}")


if __name__ == "__main__":
    asyncio.run(main())
