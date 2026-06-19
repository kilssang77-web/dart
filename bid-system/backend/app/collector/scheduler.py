"""APScheduler 기반 백그라운드 작업 스케줄러"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def _trigger_ml_retrain(reason: str = "") -> None:
    """수집 완료 후 ML 재학습을 백그라운드 스레드로 실행. 재학습 중이면 skip."""
    from app.services import MyBidFeedbackService
    if MyBidFeedbackService.RETRAIN_LOCK:
        logger.info("ML 재학습 이미 진행 중 — skip (%s)", reason)
        return
    logger.info("ML 재학습 트리거 — 사유: %s", reason or "수집 완료")
    import threading
    threading.Thread(target=MyBidFeedbackService._run_retrain, daemon=True).start()


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
            _trigger_ml_retrain("전체 수집(all) 완료")
        elif collect_type == "notices":
            # 공사 + 용역 동시 수집 (G2B API coverage 확대)
            collect_notices(db, client, "notice_cnstwk")
            collect_notices(db, client, "notice_servc")
        elif collect_type == "results":
            collect_results(db, client)
            _trigger_ml_retrain("G2B 결과 수집 완료")
        else:
            logger.warning("알 수 없는 collect_type: %s", collect_type)
    except Exception as exc:
        logger.error("수집 작업 실패 [%s]: %s", collect_type, exc)
    finally:
        db.close()


def run_results_and_sync() -> None:
    """G2B 개찰 결과 수집 후 투찰이력 자동 연계 + ML 재학습 (18:00 KST)."""
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
    """inpo21c 입찰공고 사전정보 수집 + bids 동기화 (매일 09:00 KST).

    G2B BidPublicInfoService02 대체: info21c /bid/con 에서 개찰 전
    공고(예가방법, 낙찰하한율 등)를 수집하고 bids 테이블에 자동 등록.
    """
    from app.database import SessionLocal
    from app.collector.inpo21c import collect_bid_notices_inpo21c
    from app.services import InpoNoticesSyncService

    db = SessionLocal()
    try:
        result = collect_bid_notices_inpo21c(db, max_pages=5)
        logger.info("inpo21c 입찰공고 수집 완료: %s", result)
        sync = InpoNoticesSyncService().sync(db)
        logger.info("inpo21c → bids 동기화: %s", sync)
    except Exception as exc:
        logger.error("inpo21c 입찰공고 수집/동기화 실패: %s", exc)
    finally:
        db.close()


def run_inpo21c_job() -> None:
    """inpo21c 전 참여자 + 복수예가 + 공고헤더 수집 (매일 19:30 KST).

    변경: 주 1회(월) → 매일 19:30 KST (개찰 후 ~1시간 30분).
    당일 개찰 결과를 당일 수집하여 ML 학습 데이터 실시간 갱신.
    수집 후 bids 테이블 역방향 동기화 (base_amount, bid_open_date, participant_count).
    """
    from app.database import SessionLocal
    from app.collector.inpo21c import collect_inpo21c
    from app.collector.service import sync_inpo21c_to_bids

    db = SessionLocal()
    try:
        result = collect_inpo21c(db, max_pages=10)
        logger.info("inpo21c 수집 완료: %s", result)
        sync_result = sync_inpo21c_to_bids(db)
        logger.info("inpo21c→bids 동기화: %s", sync_result)
        if result.get("bids", 0) > 0:
            _trigger_ml_retrain("inpo21c 전참여자 수집 완료")
    except Exception as exc:
        logger.error("inpo21c 수집 실패: %s", exc)
    finally:
        db.close()


def run_inpo21c_national_job() -> None:
    """inpo21c 전국 낙찰 결과 수집 (매주 일요일 03:30 KST — 맞춤설정 비의존, 전국 커버리지)."""
    from app.database import SessionLocal
    from app.collector.inpo21c import collect_inpo21c_national
    from app.collector.service import sync_inpo21c_to_bids

    db = SessionLocal()
    try:
        result = collect_inpo21c_national(db, max_pages=100)
        logger.info("inpo21c 전국 수집 완료: %s", result)
        sync_result = sync_inpo21c_to_bids(db)
        logger.info("inpo21c→bids 동기화: %s", sync_result)
        if result.get("bids", 0) > 0:
            _trigger_ml_retrain("inpo21c 전국 수집 완료")
    except Exception as exc:
        logger.error("inpo21c 전국 수집 실패: %s", exc)
    finally:
        db.close()


def run_post_open_collect_job() -> None:
    """개찰 후 6시간 내 결과 수집 트리거 — 매일 10:00/16:00/22:00 KST 실행."""
    from app.config import get_settings
    from app.database import SessionLocal
    from app.collector.client import NarajangterClient
    from app.collector.service import collect_results

    settings = get_settings()
    db = SessionLocal()
    try:
        client = NarajangterClient(api_key=settings.g2b_api_key)
        result = collect_results(db, client, days_back=3)
        logger.info("개찰 후 결과 수집 완료: 성공=%d, 실패=%d", result.success_count, result.fail_count)
        _trigger_ml_retrain("개찰 후 결과 수집 완료")
    except Exception as exc:
        logger.error("개찰 후 결과 수집 실패: %s", exc)
    finally:
        db.close()


def run_execution_deadline_job() -> None:
    """투찰 마감 임박 알림 (D-0/D-1) + 개찰대기 결과 입력 리마인더 (매일 08:00 KST)."""
    from datetime import date, timedelta, datetime, timezone
    from sqlalchemy import func
    from app.database import SessionLocal
    from app.models import BidExecution
    from app.services import NotificationService

    db = SessionLocal()
    try:
        today = date.today()
        tomorrow = today + timedelta(days=1)
        utc_now = datetime.now(timezone.utc)
        overdue_cutoff = utc_now - timedelta(days=2)

        svc = NotificationService(db)
        deadline_created = 0

        # D-0: 오늘 개찰 마감
        for ex in db.query(BidExecution).filter(
            BidExecution.status.in_(["참여결정", "투찰완료"]),
            func.date(BidExecution.bid_open_date) == today,
        ).all():
            svc.create_execution_deadline(ex.user_id, ex.title, days_left=0, execution_id=ex.id)
            deadline_created += 1

        # D-1: 내일 개찰 마감
        for ex in db.query(BidExecution).filter(
            BidExecution.status.in_(["참여결정", "투찰완료"]),
            func.date(BidExecution.bid_open_date) == tomorrow,
        ).all():
            svc.create_execution_deadline(ex.user_id, ex.title, days_left=1, execution_id=ex.id)
            deadline_created += 1

        # 개찰대기 2일 초과 → 결과 입력 요청
        reminder_created = 0
        for ex in db.query(BidExecution).filter(
            BidExecution.status == "개찰대기",
            BidExecution.bid_open_date <= overdue_cutoff,
        ).all():
            svc.create_result_reminder(ex.user_id, ex.title, execution_id=ex.id)
            reminder_created += 1

        logger.info("투찰 마감 알림: 마감=%d건, 결과입력=%d건", deadline_created, reminder_created)
    except Exception as exc:
        logger.error("투찰 마감 알림 실패: %s", exc)
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


def run_freq_rebuild_job() -> None:
    """발주기관 빈도표 + 전략 DB 주간 재계산 (매주 일요일 03:00 KST)."""
    from app.database import SessionLocal
    from app.services import FrequencyService, AgencyStrategyService

    db = SessionLocal()
    try:
        freq_result = FrequencyService(db).rebuild_all()
        strat_result = AgencyStrategyService(db).rebuild_all()
        logger.info("빈도표 재계산 완료: freq=%s, strategy=%s", freq_result, strat_result)
    except Exception as exc:
        logger.error("빈도표 재계산 실패: %s", exc)
    finally:
        db.close()


def _normalize_ano(s: str) -> str:
    """공고번호 정규화 — 공백·하이픈·슬래시 제거 후 소문자."""
    import re
    return re.sub(r"[\s\-/]", "", s or "").lower()


def _fetch_inpo_row(db, announcement_no: str, agency_id: int, bid_open_date, base_amount: int):
    """
    3단계 퍼지 매칭으로 inpo21c_bids에서 개찰 결과 조회.
      1) 정확한 announcement_no 매칭
      2) 정규화 announcement_no 매칭 (하이픈/공백 제거)
      3) agency_id + 개찰일 ±1일 + base_amount ±3%
    """
    from sqlalchemy import text

    BASE_SQL = """
        SELECT ib.yega_ratio / 100.0 AS srate,
               COUNT(ip.id)          AS total_bidders,
               MIN(CASE WHEN ip.is_winner THEN ip.base_ratio END) AS winner_rate
        FROM inpo21c_bids ib
        LEFT JOIN inpo21c_participants ip ON ip.inpo21c_bid_id = ib.inpo21c_bid_id
        WHERE {where}
        GROUP BY ib.yega_ratio
        LIMIT 1
    """

    # 1단계: 정확 매칭
    if announcement_no:
        r = db.execute(text(BASE_SQL.format(where="ib.announcement_no = :ano")),
                       {"ano": announcement_no}).fetchone()
        if r and (r[0] or r[2]):
            return r, "exact"

    # 2단계: 정규화 매칭 (다른 포맷 공고번호 처리)
    if announcement_no:
        norm = _normalize_ano(announcement_no)
        r = db.execute(text(BASE_SQL.format(where="REGEXP_REPLACE(LOWER(ib.announcement_no), '[\\\\s\\\\-/]', '', 'g') = :norm")),
                       {"norm": norm}).fetchone()
        if r and (r[0] or r[2]):
            return r, "normalized"

    # 3단계: 기관 + 날짜 ±1일 + 금액 ±3%
    if agency_id and bid_open_date and base_amount:
        try:
            lo = int(base_amount * 0.97)
            hi = int(base_amount * 1.03)
            r = db.execute(text("""
                SELECT ib.yega_ratio / 100.0 AS srate,
                       COUNT(ip.id)          AS total_bidders,
                       MIN(CASE WHEN ip.is_winner THEN ip.base_ratio END) AS winner_rate
                FROM inpo21c_bids ib
                LEFT JOIN inpo21c_participants ip ON ip.inpo21c_bid_id = ib.inpo21c_bid_id
                JOIN bids b2 ON b2.announcement_no = ib.announcement_no
                WHERE b2.agency_id = :aid
                  AND b2.bid_open_date BETWEEN :dt_lo AND :dt_hi
                  AND b2.base_amount BETWEEN :lo AND :hi
                GROUP BY ib.yega_ratio
                ORDER BY COUNT(ip.id) DESC
                LIMIT 1
            """), {
                "aid": agency_id,
                "dt_lo": bid_open_date - __import__("datetime").timedelta(days=1),
                "dt_hi": bid_open_date + __import__("datetime").timedelta(days=1),
                "lo": lo, "hi": hi,
            }).fetchone()
            if r and (r[0] or r[2]):
                return r, "fuzzy"
        except Exception:
            pass

    return None, None


def run_journal_auto_fill_job() -> None:
    """
    bid_journal 결과 자동 수집 (3단계 퍼지 매칭).

    개찰일이 지난 pending 저널에 대해:
      1단계: 정확한 announcement_no 매칭
      2단계: 정규화 announcement_no (공백·하이픈 제거)
      3단계: 기관 + 날짜 ±1일 + 금액 ±3% 퍼지 매칭
    """
    from app.database import SessionLocal
    from sqlalchemy import text

    db = SessionLocal()
    try:
        # sucsfbidRate 오인으로 winner_rate > 0.97 저장된 레코드 초기화
        reset_cnt = db.execute(text("""
            UPDATE bid_journal
            SET winner_rate = NULL, rate_gap = NULL, result = NULL,
                our_rank = NULL, total_bidders = NULL, updated_at = NOW()
            WHERE winner_rate > 0.97
        """)).rowcount
        if reset_cnt:
            db.commit()
            logger.info("journal_auto_fill: winner_rate 오인 %d건 초기화", reset_cnt)

        rows = db.execute(text("""
            SELECT j.id, j.bid_id, j.announcement_no, j.submitted_rate,
                   j.pred_srate_center, b.agency_id,
                   b.bid_open_date, b.base_amount
            FROM bid_journal j
            JOIN bids b ON b.id = j.bid_id
            WHERE j.result IS NULL
              AND j.submitted_rate IS NOT NULL
              AND (b.bid_open_date IS NULL OR b.bid_open_date <= NOW() - INTERVAL '2 hours')
            ORDER BY b.bid_open_date DESC NULLS LAST
            LIMIT 100
        """)).fetchall()

        if not rows:
            logger.info("journal_auto_fill: 대기 건 없음")
            return

        filled = 0
        match_stats = {"exact": 0, "normalized": 0, "fuzzy": 0, "bid_results": 0}

        for row in rows:
            jid, bid_id, announcement_no, submitted_rate, pred_srate, agency_id, bid_open_date, base_amount = row
            try:
                # 3단계 퍼지 매칭
                inpo_row, match_type = _fetch_inpo_row(db, announcement_no, agency_id, bid_open_date, base_amount)

                # bid_results 직접 조회 (fallback)
                # sucsfbidRate는 낙찰금액/예정가격 비율이라 1.0 초과 가능 — 기초금액 기준 범위(0.80~0.97)만 사용
                br_row = db.execute(text("""
                    SELECT
                        COUNT(*)                                                          AS total,
                        MIN(CASE WHEN is_winner AND bid_rate BETWEEN 0.80 AND 0.97
                                 THEN bid_rate END)                                       AS winner_rate,
                        SUM(CASE WHEN bid_rate BETWEEN 0.80 AND 0.97
                                  AND bid_rate <= :srate THEN 1 ELSE 0 END)              AS rank_approx
                    FROM bid_results
                    WHERE bid_id = :bid_id
                """), {"bid_id": bid_id, "srate": float(submitted_rate)}).fetchone()

                actual_srate  = float(inpo_row[0]) if inpo_row and inpo_row[0] else None
                total_bidders = (int(inpo_row[1]) if inpo_row and inpo_row[1] else
                                 (int(br_row[0]) if br_row and br_row[0] else None))
                winner_rate   = (float(inpo_row[2]) if inpo_row and inpo_row[2] else
                                 (float(br_row[1]) if br_row and br_row[1] else None))
                our_rank      = int(br_row[2]) + 1 if br_row and br_row[2] is not None else None

                if match_type:
                    match_stats[match_type] = match_stats.get(match_type, 0) + 1
                elif br_row and br_row[1]:
                    match_stats["bid_results"] += 1

                if winner_rate is None and actual_srate is None:
                    continue

                sub = float(submitted_rate)
                if winner_rate is not None:
                    result = '낙찰' if abs(sub - winner_rate) < 0.00005 else '패찰'
                elif actual_srate is not None:
                    result = '패찰'
                else:
                    continue

                rate_gap    = round(winner_rate - sub, 6) if winner_rate else None
                srate_error = round(float(actual_srate) - float(pred_srate), 6) if actual_srate and pred_srate else None

                db.execute(text("""
                    UPDATE bid_journal SET
                        result        = :result,
                        actual_srate  = :actual_srate,
                        our_rank      = :our_rank,
                        total_bidders = :total_bidders,
                        winner_rate   = :winner_rate,
                        rate_gap      = :rate_gap,
                        srate_error   = :srate_error,
                        opened_at     = NOW(),
                        updated_at    = NOW()
                    WHERE id = :jid
                      AND result IS NULL
                """), {
                    "result":        result,
                    "actual_srate":  actual_srate,
                    "our_rank":      our_rank,
                    "total_bidders": total_bidders,
                    "winner_rate":   winner_rate,
                    "rate_gap":      rate_gap,
                    "srate_error":   srate_error,
                    "jid":           jid,
                })
                db.commit()
                filled += 1
                logger.info("journal_auto_fill: #%d → %s [%s] (rate_gap=%.4f)",
                            jid, result, match_type or "bid_results", rate_gap or 0)

            except Exception as e:
                db.rollback()
                logger.warning("journal_auto_fill #%d 오류: %s", jid, e)

        logger.info("journal_auto_fill 완료: %d/%d건 처리 매칭통계=%s",
                    filled, len(rows), match_stats)

    except Exception as e:
        logger.error("journal_auto_fill 전체 오류: %s", e)
    finally:
        db.close()


def run_pre_open_alert_job() -> None:
    """개찰 3시간 전 사전 알림 (매 정시 실행)."""
    from datetime import datetime, timezone, timedelta
    from app.database import SessionLocal
    from app.models import BidExecution
    from app.services import NotificationService

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        window_start = now + timedelta(hours=2)
        window_end   = now + timedelta(hours=4)
        executions = db.query(BidExecution).filter(
            BidExecution.status.in_(["참여결정", "투찰완료"]),
            BidExecution.bid_open_date >= window_start,
            BidExecution.bid_open_date <= window_end,
        ).all()
        svc = NotificationService(db)
        created = 0
        for ex in executions:
            svc.create_pre_open_alert(ex.user_id, ex.title, execution_id=ex.id)
            created += 1
        logger.info("3시간 전 알림: %d건", created)
    except Exception as exc:
        logger.error("3시간 전 알림 실패: %s", exc)
    finally:
        db.close()


def run_validation_job() -> None:
    """Walk-forward 모델 검증 — 전월 예측 vs 실제 낙찰률 캘리브레이션 (매월 1일 03:00 KST)."""
    from app.database import SessionLocal
    from app.ml.validation import WalkForwardValidator

    db = SessionLocal()
    try:
        result = WalkForwardValidator().run(db)
        logger.info("Walk-forward 검증: %s", result)
    except Exception as e:
        logger.error("Walk-forward 검증 실패: %s", e)
    finally:
        db.close()


def create_scheduler() -> BackgroundScheduler:
    """BackgroundScheduler 생성 및 작업 등록."""
    scheduler = BackgroundScheduler(timezone="Asia/Seoul")

    scheduler.add_job(
        run_collection_job,
        trigger=CronTrigger(hour=6, minute=30, timezone="Asia/Seoul"),
        args=["notices"],
        id="collect_notices_daily",
        name="공고 수집 (매일 06:30 KST)",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_results_and_sync,
        trigger=CronTrigger(hour=18, minute=30, timezone="Asia/Seoul"),
        id="collect_results_and_sync_daily",
        name="개찰결과 수집 + 투찰이력 연계 (매일 18:30 KST)",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_scsbid_job,
        trigger=CronTrigger(hour=19, minute=30, timezone="Asia/Seoul"),
        id="collect_scsbid_daily",
        name="낙찰정보서비스 참여자수 보강 (매일 19:30 KST)",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_bid_notices_inpo21c_job,
        trigger=CronTrigger(hour=9, minute=30, timezone="Asia/Seoul"),
        id="collect_bid_notices_inpo21c_daily",
        name="inpo21c 입찰공고 사전정보 (매일 09:30 KST)",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_inpo21c_job,
        trigger=CronTrigger(hour=20, minute=0, timezone="Asia/Seoul"),
        id="collect_inpo21c_daily",
        name="inpo21c 전참여자+예가 수집 (매일 20:00 KST)",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_srate_spike_check_job,
        trigger=CronTrigger(hour=7, minute=30, timezone="Asia/Seoul"),
        id="srate_spike_check_daily",
        name="사정율 급변 알림 탐지 (매일 07:30 KST)",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_execution_deadline_job,
        trigger=CronTrigger(hour=8, minute=30, timezone="Asia/Seoul"),
        id="execution_deadline_notify_daily",
        name="투찰 마감 임박 알림 D-0/D-1 (매일 08:30 KST)",
        replace_existing=True,
        max_instances=1,
    )
    for hr, mi in ((10, 30), (16, 30), (22, 30)):
        scheduler.add_job(
            run_post_open_collect_job,
            trigger=CronTrigger(hour=hr, minute=mi, timezone="Asia/Seoul"),
            id=f"post_open_collect_{hr}",
            name=f"개찰 후 결과 수집 ({hr:02d}:{mi:02d} KST)",
            replace_existing=True,
            max_instances=1,
        )

    scheduler.add_job(
        run_freq_rebuild_job,
        trigger=CronTrigger(day_of_week="sun", hour=4, minute=0, timezone="Asia/Seoul"),
        id="freq_rebuild_weekly",
        name="발주기관 빈도표+전략 재계산 (매주 일 04:00 KST)",
        replace_existing=True,
        max_instances=1,
    )
    # 전국 낙찰 수집: 화·목·일 03:30 KST (주 3회 — 커버리지 갭 최소화)
    for dow, hh, mm in (("tue", 3, 30), ("thu", 3, 30), ("sun", 4, 30)):
        scheduler.add_job(
            run_inpo21c_national_job,
            trigger=CronTrigger(day_of_week=dow, hour=hh, minute=mm, timezone="Asia/Seoul"),
            id=f"collect_inpo21c_national_{dow}",
            name=f"inpo21c 전국 낙찰 수집 ({dow} {hh:02d}:{mm:02d} KST)",
            replace_existing=True,
            max_instances=1,
        )
    # 투찰 저널 자동 결과 수집 (매일 21:00 — 개찰 완료 후 inpo21c 데이터 안정화 후)
    scheduler.add_job(
        run_journal_auto_fill_job,
        trigger=CronTrigger(hour=21, minute=0, timezone="Asia/Seoul"),
        id="journal_auto_fill_daily",
        name="투찰저널 개찰결과 자동 수집 (매일 21:00 KST)",
        replace_existing=True,
        max_instances=1,
    )
    # 개찰 3시간 전 사전 알림 (매 정시)
    scheduler.add_job(
        run_pre_open_alert_job,
        trigger=CronTrigger(minute=0, timezone="Asia/Seoul"),
        id="pre_open_alert_hourly",
        name="개찰 3시간 전 사전 알림 (매 정시 KST)",
        replace_existing=True,
        max_instances=1,
    )
    # Walk-forward 모델 검증 (매월 1일 03:00 KST)
    scheduler.add_job(
        run_validation_job,
        trigger=CronTrigger(day=1, hour=3, minute=0, timezone="Asia/Seoul"),
        id="walkforward_monthly",
        name="Walk-forward 모델 검증 (매월 1일 03:00 KST)",
        replace_existing=True,
        max_instances=1,
    )

    return scheduler