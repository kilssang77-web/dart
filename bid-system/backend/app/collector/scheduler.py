"""APScheduler 기반 백그라운드 작업 스케줄러"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def run_collection_job(collect_type: str) -> None:
    """G2B 수집 작업 실행. collect_type: "all" | "notices" | "results" """
    from app.config import get_settings
    from app.database import SessionLocal
    from app.collector.client import NarajangterClient
    from app.collector.service import collect_notices, collect_results, run_full_collection

    settings = get_settings()
    db = SessionLocal()
    try:
        client = NarajangterClient(api_key=settings.g2b_api_key)
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


def run_results_and_sync() -> None:
    """G2B 개찰 결과 수집 후 투찰이력 자동 연계 (18:00 KST)."""
    run_collection_job("results")

    from app.database import SessionLocal
    from app.services import G2BSyncService

    db = SessionLocal()
    try:
        result = G2BSyncService().sync(db)
        logger.info("투찰이력 자동 연계: %s", result)
    except Exception as exc:
        logger.error("투찰이력 연계 실패: %s", exc)
    finally:
        db.close()


def run_scsbid_job() -> None:
    """낙찰정보서비스 참여자수 + 낙찰율 보강 (매일 19:00 KST — 개찰결과 수집 후)."""
    from app.database import SessionLocal
    from app.collector.service import collect_scsbid_results

    db = SessionLocal()
    try:
        result = collect_scsbid_results(db, days_back=7)
        logger.info("scsbid 수집 완료: 성공=%d, 실패=%d", result.success_count, result.fail_count)
    except Exception as exc:
        logger.error("scsbid 수집 실패: %s", exc)
    finally:
        db.close()


def run_bid_notices_inpo21c_job() -> None:
    """inpo21c 입찰공고 중 사전정보 수집 (매일 09:00 KST — 투찰 전 예가방법 파악)."""
    from app.database import SessionLocal
    from app.collector.inpo21c import collect_bid_notices_inpo21c

    db = SessionLocal()
    try:
        result = collect_bid_notices_inpo21c(db, max_pages=5)
        logger.info("inpo21c 입찰공고 수집 완료: %s", result)
    except Exception as exc:
        logger.error("inpo21c 입찰공고 수집 실패: %s", exc)
    finally:
        db.close()


def run_inpo21c_job() -> None:
    """inpo21c 전 참여자 + 복수예가 + 공고헤더 수집 (매주 월요일 02:00 KST)."""
    from app.database import SessionLocal
    from app.collector.inpo21c import collect_inpo21c

    db = SessionLocal()
    try:
        result = collect_inpo21c(db, max_pages=10)
        logger.info("inpo21c 수집 완료: %s", result)
    except Exception as exc:
        logger.error("inpo21c 수집 실패: %s", exc)
    finally:
        db.close()


def run_srate_spike_check_job() -> None:
    """사정율 급변 탐지 후 전체 공지 알림 생성 (매일 07:00 KST)."""
    SPIKE_THRESHOLD_PCT = 2.0  # ±2%p 이상이면 급변 알림

    from app.database import SessionLocal
    from app.services import SrateTrendService, NotificationService

    db = SessionLocal()
    try:
        trends = SrateTrendService().get_top_trends(db, limit=10)
        svc = NotificationService(db)
        fired = 0
        for t in trends:
            delta_pct = abs(t.get("delta", 0)) * 100
            if delta_pct >= SPIKE_THRESHOLD_PCT:
                agency_name = t.get("agency_name", "발주처 미상")
                direction = t.get("direction", "up")
                svc.create_srate_spike(agency_name, "전체", direction, delta_pct)
                fired += 1
        logger.info("사정율 급변 알림: %d건 발송", fired)
    except Exception as exc:
        logger.error("사정율 급변 알림 실패: %s", exc)
    finally:
        db.close()


def create_scheduler() -> BackgroundScheduler:
    """BackgroundScheduler 생성 및 작업 등록."""
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
        run_results_and_sync,
        trigger=CronTrigger(hour=18, minute=0, timezone="Asia/Seoul"),
        id="collect_results_and_sync_daily",
        name="개찰결과 수집 + 투찰이력 연계 (매일 18:00 KST)",
        replace_existing=True,
    )
    scheduler.add_job(
        run_scsbid_job,
        trigger=CronTrigger(hour=19, minute=0, timezone="Asia/Seoul"),
        id="collect_scsbid_daily",
        name="낙찰정보서비스 참여자수 보강 (매일 19:00 KST)",
        replace_existing=True,
    )
    scheduler.add_job(
        run_bid_notices_inpo21c_job,
        trigger=CronTrigger(hour=9, minute=0, timezone="Asia/Seoul"),
        id="collect_bid_notices_inpo21c_daily",
        name="inpo21c 입찰공고 사전정보 (매일 09:00 KST)",
        replace_existing=True,
    )
    scheduler.add_job(
        run_inpo21c_job,
        trigger=CronTrigger(day_of_week="mon", hour=2, minute=0, timezone="Asia/Seoul"),
        id="collect_inpo21c_weekly",
        name="inpo21c 전참여자+예가 수집 (매주 월 02:00 KST)",
        replace_existing=True,
    )
    scheduler.add_job(
        run_srate_spike_check_job,
        trigger=CronTrigger(hour=7, minute=0, timezone="Asia/Seoul"),
        id="srate_spike_check_daily",
        name="사정율 급변 알림 탐지 (매일 07:00 KST)",
        replace_existing=True,
    )

    return scheduler