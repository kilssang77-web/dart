"""
낙찰정보서비스 백필 — 429 Rate Limit 대응: 페이지 간 3초 딜레이
"""
import asyncio, sys, httpx
from datetime import datetime, timedelta
sys.path.insert(0, "/app")
from main import save_scsbid_to_db, MkSession, logger, COLLECT_ENABLED, G2B_API_KEY, G2B_RESULT_BASE

def next_month(dt):
    return datetime(dt.year + (dt.month // 12), dt.month % 12 + 1, 1)

async def fetch_month(df, dt):
    all_items, page = [], 1
    async with httpx.AsyncClient(timeout=60.0) as c:
        while True:
            retries = 0
            while retries < 5:
                try:
                    params = {"inqryDiv":1,"inqryBgnDt":df,"inqryEndDt":dt,"numOfRows":100,"pageNo":page,"type":"json","serviceKey":G2B_API_KEY}
                    r = await c.get(f"{G2B_RESULT_BASE}/getScsbidListSttusCnstwk", params=params)
                    if r.status_code == 429:
                        wait = 120 * (retries + 1)
                        logger.warning(f"  429 Rate Limit — {wait}초 대기 ({retries+1}/5)")
                        await asyncio.sleep(wait)
                        retries += 1
                        continue
                    r.raise_for_status()
                    body = r.json().get("response",{}).get("body",{})
                    items = body.get("items",[])
                    if not items: return all_items
                    if isinstance(items, dict): items = [items]
                    all_items.extend(items)
                    total = int(body.get("totalCount",0) or 0)
                    if page % 10 == 0:
                        logger.info(f"  페이지 {page}: {len(all_items)}/{total}건")
                    if page * 100 >= total: return all_items
                    page += 1
                    await asyncio.sleep(3.0)   # 페이지 간 3초 딜레이
                    break
                except Exception as e:
                    retries += 1
                    logger.warning(f"  오류 retry {retries}: {e}")
                    await asyncio.sleep(30 * retries)
            else:
                logger.warning(f"  페이지 {page} 재시도 초과 — 다음 월로 넘어감")
                return all_items
    return all_items

async def full_backfill(start_year=2024, start_month=4):
    if not COLLECT_ENABLED or not G2B_API_KEY:
        logger.error("COLLECT_ENABLED or G2B_API_KEY 미설정"); return
    cursor = datetime(start_year, start_month, 1)
    end = datetime.now()
    grand_total = 0
    while cursor < end:
        chunk_end = min(next_month(cursor) - timedelta(seconds=1), end)
        df = cursor.strftime("%Y%m%d") + "0000"
        dt = chunk_end.strftime("%Y%m%d") + "2359"
        logger.info(f"[backfill] {df[:8]}~{dt[:8]}")
        items = await fetch_month(df, dt)
        if items:
            db = MkSession()
            try:
                n = save_scsbid_to_db(db, items)
                grand_total += n
                logger.info(f"  저장 {n}건 / 조회 {len(items)}건 (누계 {grand_total}건)")
            finally:
                db.close()
        else:
            logger.info("  결과없음")
        cursor = next_month(cursor)
        await asyncio.sleep(5.0)   # 월 간 5초 딜레이
    logger.info(f"[DONE] 전체 {grand_total}건 저장 완료")

if __name__ == "__main__":
    asyncio.run(full_backfill())
