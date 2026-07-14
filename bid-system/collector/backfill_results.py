import asyncio
import sys
from datetime import datetime, timedelta
sys.path.insert(0, "/app")
from main import fetch_results_scsbid, save_scsbid_to_db, MkSession, logger, COLLECT_ENABLED, G2B_API_KEY

def next_month(dt):
    if dt.month == 12:
        return datetime(dt.year + 1, 1, 1)
    return datetime(dt.year, dt.month + 1, 1)

async def backfill():
    if not COLLECT_ENABLED or not G2B_API_KEY:
        logger.error("COLLECT_ENABLED or G2B_API_KEY not set")
        return
    start, end, cursor, total = datetime(2024, 4, 1), datetime.now(), datetime(2024, 4, 1), 0
    while cursor < end:
        chunk_end = min(next_month(cursor) - timedelta(seconds=1), end)
        df = cursor.strftime("%Y%m%d") + "0000"
        dt = chunk_end.strftime("%Y%m%d") + "2359"
        logger.info(f"[backfill] {df[:8]}~{dt[:8]}")
        try:
            items = await fetch_results_scsbid(df, dt)
        except Exception as e:
            logger.warning(f"  skip: {e}")
            cursor = next_month(cursor)
            continue
        if items:
            db = MkSession()
            try:
                n = save_scsbid_to_db(db, items)
                total += n
                logger.info(f"  saved {n} / fetched {len(items)} (total {total})")
            finally:
                db.close()
        else:
            logger.info("  no items")
        cursor = next_month(cursor)
        await asyncio.sleep(1.5)
    logger.info(f"[DONE] total {total} saved")

asyncio.run(backfill())
