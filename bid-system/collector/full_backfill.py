"""
2024-04 ~ 현재까지 낙찰정보서비스 월별 백필
main.py의 수정된 save_scsbid_to_db (bidwinnrNm, prtcptCnum) 사용
"""
import asyncio, sys
from datetime import datetime, timedelta
sys.path.insert(0, "/app")
from main import fetch_results_scsbid, save_scsbid_to_db, MkSession, logger, COLLECT_ENABLED, G2B_API_KEY

def next_month(dt):
    return datetime(dt.year + (dt.month // 12), dt.month % 12 + 1, 1)

async def full_backfill(start_year=2024, start_month=4):
    if not COLLECT_ENABLED or not G2B_API_KEY:
        logger.error("COLLECT_ENABLED or G2B_API_KEY not set"); return
    cursor = datetime(start_year, start_month, 1)
    end = datetime.now()
    total = 0
    while cursor < end:
        chunk_end = min(next_month(cursor) - timedelta(seconds=1), end)
        df = cursor.strftime("%Y%m%d") + "0000"
        dt = chunk_end.strftime("%Y%m%d") + "2359"
        logger.info(f"[backfill] {df[:8]}~{dt[:8]}")
        try:
            items = await fetch_results_scsbid(df, dt)
        except Exception as e:
            logger.warning(f"  API 오류 skip: {e}")
            cursor = next_month(cursor)
            continue
        if items:
            db = MkSession()
            try:
                n = save_scsbid_to_db(db, items)
                total += n
                logger.info(f"  저장 {n}건 / 조회 {len(items)}건 (누계 {total}건)")
            finally:
                db.close()
        else:
            logger.info(f"  결과없음")
        cursor = next_month(cursor)
        await asyncio.sleep(1.5)
    logger.info(f"[DONE] 전체 {total}건 저장 완료")

if __name__ == "__main__":
    asyncio.run(full_backfill())
