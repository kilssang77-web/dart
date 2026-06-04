"""APScheduler 설정 — 나라장터 수집 스케줄"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def run_collection_job(collect_type: str) -> None:
    """DB 세션 생성 후 수집 서비스 호출.

    collect_type: "all" | "notices" | "results"
    """
    from app.config import get_settings
    from app.database import SessionLocal
    from app.collector.client import NarajangterClient
    from app.collector.service import collect_notices, collect_results, run_full_collection

    settings = get_settings()
    db = SessionLocal()
    try:
        client = NarajangterClient(api_key=settings.nara_api_key)
        if collect_type == "all":
            run_full_collection(db)
        elif collect_type == "notices":
            for ctype in ("notice_cnstwk", "notice_servc", "notice_thng"):
                collect_notices(db, client, ctype)
        elif collect_type == "results":
            collect_results(db, client)
        else:
            logger.warning("알 수 없는 collect_type: %s", collect_type)
    except Exception as exc:
        logger.error("수집 작업 실패 [%s]: %s", collect_type, exc)
    finally:
        db.close()


def create_scheduler() -> BackgroundScheduler:
    """BackgroundScheduler 생성 — 매일 06:00 KST 공고 수집, 18:00 KST 낙찰결과 수집"""
    scheduler = BackgroundScheduler(timezone="Asia/Seoul")

    scheduler.add_job(
        run_collection_job,
        trigger=CronTrigger(hour=6, minute=0, timezone="Asia/Seoul"),
        args=["notices"],
        id="collect_notices_daily",
        name="공고 수집 (매일 06:00 KST)",
        replace_existing=True,
    )
    scheduler.add_job(
        run_collection_job,
        trigger=CronTrigger(hour=18, minute=0, timezone="Asia/Seoul"),
        args=["results"],
        id="collect_results_daily",
        name="낙찰결과 수집 (매일 18:00 KST)",
        replace_existing=True,
    )

    return scheduler
