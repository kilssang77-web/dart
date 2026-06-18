import asyncio, sys
sys.path.insert(0, "/app")
from main import fetch_results_scsbid, save_scsbid_to_db, MkSession, logger

async def test():
    # 2025-12-01 ~ 2025-12-10 구간 낙찰결과 수집
    items = await fetch_results_scsbid("202512010000", "202512102359")
    print(f"API 조회: {len(items)}건")
    if items:
        db = MkSession()
        try:
            n = save_scsbid_to_db(db, items)
            print(f"저장: {n}건")
        finally:
            db.close()

asyncio.run(test())
