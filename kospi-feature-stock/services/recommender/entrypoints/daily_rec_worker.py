"""
배치 추천 생성 워커 — 장 마감 후 오늘 탐지된 feature_events에 대한 추천 생성.
GitHub Actions에서 collector-daily 완료 후 실행.
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("rec-daily")


async def run():
    from main import RecommenderService
    from entry_recommender import EntryRecommender, update_threshold

    svc = RecommenderService()
    await svc.setup()

    await svc._sync_threshold(update_threshold)

    recommender = EntryRecommender()

    # 최근 48시간 미처리 feature_events 재처리 (오늘 + 어제 분 포함)
    import os as _os
    _os.environ.setdefault("REC_RECOVERY_HOURS", "48")

    await svc._recover_missed_events(recommender)

    logger.info("[rec-daily] 추천 생성 완료")

    await svc._db.close()
    await svc._redis.aclose()


if __name__ == "__main__":
    asyncio.run(run())
