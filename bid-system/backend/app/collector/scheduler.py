"""APScheduler 기반 백그라운드 작업 스케줄러"""
import logging
import time
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler_instance: Optional[BackgroundScheduler] = None
_last_retrain_time: float = 0.0
_RETRAIN_COOLDOWN_SECONDS = 4 * 3600  # 재학습 최소 간격 4시간


def set_scheduler(scheduler: Optional[BackgroundScheduler]) -> None:
    global _scheduler_instance
    _scheduler_instance = scheduler


def get_scheduler() -> Optional[BackgroundScheduler]:
    return _scheduler_instance


def _trigger_ml_retrain(reason: str = "") -> None:
    """수집 완료 후 ML 재학습을 백그라운드 스레드로 실행.
    재학습 중이거나 마지막 재학습으로부터 4시간 미경과 시 skip.
    """
    global _last_retrain_time
    from app.services import MyBidFeedbackService
    if MyBidFeedbackService._RETRAIN_EVENT.is_set():
        logger.info("ML 재학습 이미 진행 중 — skip (%s)", reason)
        return
    elapsed = time.time() - _last_retrain_time
    if elapsed < _RETRAIN_COOLDOWN_SECONDS:
        remaining_min = int((_RETRAIN_COOLDOWN_SECONDS - elapsed) / 60)
        logger.info("ML 재학습 쿨다운 중 — %d분 후 가능 (%s)", remaining_min, reason)
        return
    _last_retrain_time = time.time()
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
    """inpo21c 전 참여자 + 복수예가 + 공고헤더 수집 (매일 20:00 KST).

    수집 후 bids 역방향 동기화 + assessment_rate → bid_results 역동기화.
    """
    from app.database import SessionLocal
    from app.collector.inpo21c import collect_inpo21c
    from app.collector.service import sync_inpo21c_to_bids, sync_assessment_rate_from_inpo21c

    db = SessionLocal()
    try:
        result = collect_inpo21c(db, max_pages=30)
        logger.info("inpo21c 수집 완료: %s", result)
        sync_result = sync_inpo21c_to_bids(db)
        logger.info("inpo21c→bids 동기화: %s", sync_result)
        # [Phase 1] assessment_rate 역동기화 — inpo21c → bid_results
        rate_sync = sync_assessment_rate_from_inpo21c(db)
        logger.info("assessment_rate 역동기화: %s", rate_sync)
        if result.get("bids", 0) > 0:
            _trigger_ml_retrain("inpo21c 전참여자 수집 완료")
    except Exception as exc:
        logger.error("inpo21c 수집 실패: %s", exc)
    finally:
        db.close()


def run_auto_register_job() -> None:
    """inpo21c 수집 완료 후 우리 회사 참여 건 자동 등록 (매일 20:30 KST)."""
    from app.database import SessionLocal
    from app.journal_service import auto_register_from_inpo21c
    from sqlalchemy import text as _t

    db = SessionLocal()
    try:
        admin = db.execute(_t("SELECT id FROM users WHERE role='admin' LIMIT 1")).fetchone()
        user_id = admin[0] if admin else 1
        result = auto_register_from_inpo21c(db, user_id)
        logger.info("자동 이력 등록 완료: %s", result)
    except Exception as exc:
        logger.error("자동 이력 등록 실패: %s", exc)
    finally:
        db.close()


def run_inpo21c_national_job() -> None:
    """inpo21c 전국 낙찰 결과 수집 (매주 일요일 03:30 KST — 맞춤설정 비의존, 전국 커버리지)."""
    from app.database import SessionLocal
    from app.collector.inpo21c import collect_inpo21c_national
    from app.collector.service import sync_inpo21c_to_bids, sync_assessment_rate_from_inpo21c

    db = SessionLocal()
    try:
        result = collect_inpo21c_national(db, max_pages=100)
        logger.info("inpo21c 전국 수집 완료: %s", result)
        sync_result = sync_inpo21c_to_bids(db)
        logger.info("inpo21c→bids 동기화: %s", sync_result)
        rate_sync = sync_assessment_rate_from_inpo21c(db)
        logger.info("assessment_rate 역동기화: %s", rate_sync)
        if result.get("bids", 0) > 0:
            _trigger_ml_retrain("inpo21c 전국 수집 완료")
    except Exception as exc:
        logger.error("inpo21c 전국 수집 실패: %s", exc)
    finally:
        db.close()


def run_inpo21c_region_job(region: str, industry: str = "") -> None:
    """inpo21c 지역/업종 필터 수집 — 맞춤설정 비의존 전국 커버리지 확대."""
    from app.database import SessionLocal
    from app.collector.inpo21c import collect_inpo21c_by_region
    from app.collector.service import sync_inpo21c_to_bids

    db = SessionLocal()
    try:
        result = collect_inpo21c_by_region(db, region=region, industry=industry, max_pages=30)
        logger.info("inpo21c 지역수집 완료 [%s/%s]: %s", region, industry or "전업종", result)
        if result.get("bids", 0) > 0:
            sync_inpo21c_to_bids(db)
            _trigger_ml_retrain(f"inpo21c 지역수집 [{region}] 완료")
    except Exception as exc:
        logger.error("inpo21c 지역수집 실패 [%s]: %s", region, exc)
    finally:
        db.close()


def run_post_open_collect_job() -> None:
    """개찰 후 6시간 내 결과 + 복수예가 즉시 수집 (매일 10:30/16:30/22:30 KST).

    [Task #16] 개찰 직후 복수예가(yega) 수집 추가:
      - 결과 수집 완료 후 days_back=1 단기 예가상세 수집
      - inpo21c 데이터 없는 공고만 G2B 예가 API 수집 (중복 최소화)
    """
    from app.config import get_settings
    from app.database import SessionLocal
    from app.collector.client import NarajangterClient
    from app.collector.service import collect_results, collect_g2b_yega_detail

    settings = get_settings()
    db = SessionLocal()
    try:
        client = NarajangterClient(api_key=settings.g2b_api_key)
        result = collect_results(db, client, days_back=3)
        logger.info("개찰 후 결과 수집 완료: 성공=%d, 실패=%d", result.success_count, result.fail_count)
        _trigger_ml_retrain("개찰 후 결과 수집 완료")

        # 복수예가 즉시 수집 (당일 개찰 건 — inpo21c 미수집 fallback)
        try:
            yega_result = collect_g2b_yega_detail(db, days_back=1)
            logger.info("개찰 직후 예가수집: inserted=%d skipped_inpo=%d",
                        yega_result.get("inserted", 0), yega_result.get("skipped_by_inpo", 0))
        except Exception as ye:
            logger.warning("개찰 직후 예가수집 실패: %s", ye)
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


def run_competitor_anomaly_job() -> None:
    """경쟁사 담합 의심 패턴 스캔 + 알림 생성 (매일 09:00 KST).

    최근 14일 inpo21c_participants에서 CV 기반 이상 패턴을 탐지하고
    상위 5건에 대해 관리자 전원에게 알림을 생성한다.
    """
    from app.database import SessionLocal
    from app.models import User
    from app.services import NotificationService
    from app.ml.anomaly_detector import scan_recent_collusion

    db = SessionLocal()
    try:
        anomalies = scan_recent_collusion(db, days=14, limit=300)
        if not anomalies:
            logger.info("담합 의심 패턴 없음 (최근 14일)")
            return

        # 관리자 + 일반 사용자 전체 user_id
        user_ids = [u.id for u in db.query(User).filter(User.is_active.is_(True)).all()]
        if not user_ids:
            return

        svc = NotificationService(db)
        created = svc.bulk_create_anomaly_alerts(user_ids, anomalies, top_n=5)
        logger.info("담합 의심 알림 생성: %d건 (이상패턴 %d개 탐지)", created, len(anomalies))
    except Exception as exc:
        logger.error("담합 의심 스캔 실패: %s", exc)
    finally:
        db.close()


def run_auto_qualify_bids_job() -> None:
    """신규 공고 자동 적격 판정 (매일 06:30 KST).

    지난 24시간 내 수집된 공고 중 적격심사 대상(1억 이상)에 대해
    회사 프로파일 기준으로 GO/WATCH/NO-GO 판정 후 qualification_checks 저장.
    admin user(id=1) 소유로 저장하여 bids 목록에서 공통 참조 가능.
    """
    from datetime import datetime, timedelta
    from app.database import SessionLocal
    from sqlalchemy import text as _t

    db = SessionLocal()
    try:
        cutoff = datetime.now() - timedelta(hours=24)
        # 회사 프로파일
        prof_row = db.execute(_t("""
            SELECT annual_revenue, bond_limit_total, target_industries, target_regions,
                   construction_capabilities, workforce_count
            FROM company_profile LIMIT 1
        """)).fetchone()
        if not prof_row:
            logger.info("auto_qualify: company_profile 없음 — 건너뜀")
            return

        annual_revenue = int(prof_row[0] or 0)
        bond_limit = int(prof_row[1] or 0)
        target_industries = list(prof_row[2] or [])
        target_regions = list(prof_row[3] or [])
        caps = prof_row[4] or []
        workforce = int(prof_row[5] or 0)
        our_experience = 0
        for cap in caps:
            if isinstance(cap, dict):
                our_experience = max(our_experience, int(cap.get("performance", 0) or 0))

        # 회사 프로파일 데이터가 부실하면 full qualification 체크 의미 없음
        profile_has_data = (annual_revenue > 0 or our_experience > 0 or bond_limit > 0
                            or target_industries or target_regions)

        # 적격심사 대상 신규 공고 (기존 체크 없는 것)
        new_bids = db.execute(_t("""
            SELECT b.id, b.base_amount, b.industry_id, b.region_id, b.agency_id
            FROM bids b
            WHERE b.created_at >= :cutoff
              AND b.base_amount >= 100000000
              AND NOT EXISTS (
                SELECT 1 FROM qualification_checks qc
                WHERE qc.bid_id = b.id AND qc.user_id = 1
              )
            ORDER BY b.created_at DESC
            LIMIT 500
        """), {"cutoff": cutoff}).fetchall()

        if not new_bids:
            logger.info("auto_qualify: 신규 대상 공고 없음")
            return

        from app.ml.qualification import check_qualification
        checked = failed = 0
        for bid_row in new_bids:
            bid_id, base_amount, industry_id, region_id, agency_id = bid_row
            base = int(base_amount or 0)
            if base < 100_000_000:
                continue

            # 산업/지역 매칭 체크
            industry_ok = (not target_industries) or (industry_id and int(industry_id) in target_industries)
            region_ok = (not target_regions) or (region_id and int(region_id) in target_regions)
            bond_ok = (bond_limit == 0) or (base <= bond_limit)

            if not industry_ok:
                verdict, pass_prob, fail_reason = "FAIL", 0.05, "업종 불일치"
            elif not bond_ok:
                verdict, pass_prob, fail_reason = "FAIL", 0.10, "보증한도 초과"
            elif not region_ok:
                verdict, pass_prob, fail_reason = "WATCH", 0.50, "지역 범위 외"
            elif not profile_has_data:
                # 프로파일 미입력 시 UNCERTAIN — 잘못된 FAIL 방지
                verdict, pass_prob, fail_reason = "UNCERTAIN", 0.5, "회사 프로파일 미입력"
            else:
                try:
                    result = check_qualification(
                        base_amount=base,
                        estimated_price_center=0.9,
                        estimated_price_std=0.012,
                        our_experience=our_experience,
                        annual_revenue=annual_revenue,
                        workforce_count=workforce,
                    )
                    verdict = result.verdict
                    pass_prob = float(result.pass_prob)
                    fail_reason = result.fail_reason
                except Exception:
                    verdict, pass_prob, fail_reason = "UNCERTAIN", 0.5, None

            try:
                db.execute(_t("""
                    INSERT INTO qualification_checks
                        (bid_id, user_id, our_share_rate, our_experience, pass_prob,
                         verdict, fail_reason, score_breakdown)
                    VALUES (:bid_id, 1, 1.0, :exp, :prob, :verdict, :reason, '{}')
                    ON CONFLICT DO NOTHING
                """), {
                    "bid_id": bid_id, "exp": our_experience,
                    "prob": pass_prob, "verdict": verdict, "reason": fail_reason,
                })
                checked += 1
            except Exception:
                failed += 1

        db.commit()
        logger.info("auto_qualify 완료: 판정=%d건 (실패=%d)", checked, failed)
    except Exception as exc:
        logger.error("auto_qualify 실패: %s", exc)
    finally:
        db.close()


def run_vacuum_analyze_job() -> None:
    """VACUUM ANALYZE — 주요 테이블 통계 갱신 (매주 토 02:00 KST)."""
    from app.database import SessionLocal
    from sqlalchemy import text

    db = SessionLocal()
    try:
        # VACUUM은 트랜잭션 밖에서 실행해야 하므로 autocommit 연결 사용
        raw_conn = db.connection().engine.raw_connection()
        raw_conn.set_isolation_level(0)
        cur = raw_conn.cursor()
        for tbl in ["bids", "bid_results", "agencies", "inpo21c_participants", "notifications"]:
            cur.execute(f"VACUUM ANALYZE {tbl}")
            logger.info("VACUUM ANALYZE 완료: %s", tbl)
        cur.close()
        raw_conn.set_isolation_level(1)
        raw_conn.close()
    except Exception as exc:
        logger.error("VACUUM ANALYZE 실패: %s", exc)
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
        r = db.execute(text(BASE_SQL.format(where="REGEXP_REPLACE(LOWER(ib.announcement_no), '[[:space:]\\-/]', '', 'g') = :norm")),
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
        # note IS NULL: 수동/이관 등록 레코드(note 있음)는 제외
        reset_cnt = db.execute(text("""
            UPDATE bid_journal
            SET winner_rate = NULL, rate_gap = NULL, result = NULL,
                our_rank = NULL, total_bidders = NULL, updated_at = NOW()
            WHERE winner_rate > 0.97
              AND note IS NULL
        """)).rowcount
        if reset_cnt:
            db.commit()
            logger.info("journal_auto_fill: winner_rate 오인 %d건 초기화", reset_cnt)

        rows = db.execute(text("""
            SELECT j.id, j.bid_id, j.announcement_no, j.submitted_rate,
                   j.pred_srate_center, b.agency_id,
                   b.bid_open_date, b.base_amount, j.user_id
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
            jid, bid_id, announcement_no, submitted_rate, pred_srate, agency_id, bid_open_date, base_amount, user_id = row
            try:
                # 3단계 퍼지 매칭
                inpo_row, match_type = _fetch_inpo_row(db, announcement_no, agency_id, bid_open_date, base_amount)

                # bid_results 직접 조회 (fallback)
                # sucsfbidRate는 낙찰금액/예정가격 비율이라 1.0 초과 가능 — 기초금액 기준 범위(0.80~0.97)만 사용
                br_row = db.execute(text("""
                    SELECT
                        COUNT(*)                                                          AS total,
                        MIN(CASE WHEN is_winner AND bid_rate BETWEEN 0.70 AND 1.05
                                 THEN bid_rate END)                                       AS winner_rate,
                        SUM(CASE WHEN bid_rate BETWEEN 0.70 AND 1.05
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

                # actual_bid_outcomes 동기화
                _OUTCOME_MAP = {"낙찰": "WON", "패찰": "LOST"}
                outcome_result = _OUTCOME_MAP.get(result)
                if outcome_result and submitted_rate and user_id:
                    try:
                        from datetime import datetime as _dt
                        from app.models import ActualBidOutcome
                        existing = db.query(ActualBidOutcome).filter(
                            ActualBidOutcome.bid_id == bid_id,
                            ActualBidOutcome.user_id == user_id,
                        ).first()
                        fields = dict(
                            bid_id          = bid_id,
                            user_id         = user_id,
                            announcement_no = announcement_no,
                            submitted_rate  = float(submitted_rate),
                            result          = outcome_result,
                            actual_srate    = actual_srate,
                            winner_rate     = winner_rate,
                            our_rank        = our_rank,
                            total_bidders   = total_bidders,
                            predicted_srate = float(pred_srate) if pred_srate else None,
                            srate_error     = srate_error,
                            collected_at    = _dt.utcnow(),
                        )
                        if existing:
                            for k, v in fields.items():
                                setattr(existing, k, v)
                        else:
                            db.add(ActualBidOutcome(**fields))
                        db.commit()
                    except Exception as oe:
                        db.rollback()
                        logger.warning("journal_auto_fill actual_outcome #%d 오류: %s", jid, oe)

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


def run_kpi_snapshot_job() -> None:
    """KPI 스냅샷 일별 갱신 — bid_journal 기반 (매일 22:30 KST).

    actual_bid_outcomes 가 비어있어도 bid_journal 직접 집계로 동작.
    """
    from datetime import date as date_type
    from app.database import SessionLocal
    from app.services import KpiService
    from sqlalchemy import text

    db = SessionLocal()
    try:
        today = date_type.today()
        start_of_month = today.replace(day=1)

        user_ids = [r[0] for r in db.execute(text(
            "SELECT DISTINCT user_id FROM bid_journal WHERE user_id IS NOT NULL"
        )).fetchall()]

        svc = KpiService()
        saved = 0

        for uid in user_ids:
            rows = db.execute(text("""
                SELECT result, submitted_rate, winner_rate, srate_error, our_rank, total_bidders
                FROM bid_journal
                WHERE user_id = :uid
                  AND result IS NOT NULL
                  AND DATE(updated_at) BETWEEN :start AND :today
            """), {"uid": uid, "start": start_of_month, "today": today}).fetchall()

            if not rows:
                continue

            total_bids = len(rows)
            total_wins = sum(1 for r in rows if r[0] == "낙찰")
            win_rate   = round(total_wins / total_bids, 4) if total_bids > 0 else 0.0

            srate_errs = [abs(float(r[3])) for r in rows if r[3] is not None]
            srate_mae  = round(sum(srate_errs) / len(srate_errs), 5) if srate_errs else None

            rank_losses = [float(r[4]) for r in rows if r[0] == "패찰" and r[4] is not None]
            avg_rank_at_loss = round(sum(rank_losses) / len(rank_losses), 2) if rank_losses else None

            kpi = {
                "user_id":           uid,
                "snapshot_date":     today,
                "period_type":       "MONTHLY",
                "total_bids":        total_bids,
                "total_wins":        total_wins,
                "win_rate":          win_rate,
                "srate_mae":         srate_mae,
                "avg_rank_at_loss":  avg_rank_at_loss,
                "qualify_pass_rate": None,
                "win_prob_calibration": None,
                "go_rate":           None,
                "no_go_saved":       0,
            }
            svc.upsert_snapshot(db, kpi)
            saved += 1
            logger.info("KPI 스냅샷: user=%d, bids=%d, wins=%d, win_rate=%.2f%%",
                        uid, total_bids, total_wins, win_rate * 100)

        db.commit()
        logger.info("KPI 스냅샷 갱신 완료: %d명", saved)
    except Exception as exc:
        logger.error("KPI 스냅샷 갱신 실패: %s", exc)
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


def run_incomplete_participants_job() -> None:
    """참가자 수 부족 입찰 전참여자 재수집 (매주 토요일 04:00 KST).

    낙찰자만 있고 전 참여자가 3명 미만인 입찰 건을 재수집하여
    win_prob_model 학습 데이터 품질을 향상시킨다.
    """
    from app.database import SessionLocal
    from app.collector.inpo21c import collect_incomplete_participants

    db = SessionLocal()
    try:
        result = collect_incomplete_participants(db, min_parts=3, max_bids=500)
        logger.info("incomplete 참가자 재수집 완료: %s", result)
        if result.get("filled", 0) > 0:
            _trigger_ml_retrain("incomplete 참가자 재수집 완료")
    except Exception as exc:
        logger.error("incomplete 참가자 재수집 실패: %s", exc)
    finally:
        db.close()


def run_g2b_all_participants_job() -> None:
    """G2B 전참여자 수집 (매일 19:00 KST — getOpengResultListInfoOpengCompt).

    최근 7일 개찰 완료 공고의 모든 참여자(투찰금액·투찰률·추첨번호)를
    bid_results에 upsert하고 participant_count를 갱신한다.
    """
    from app.database import SessionLocal
    from app.collector.service import collect_all_participants_g2b

    db = SessionLocal()
    try:
        result = collect_all_participants_g2b(db, days_back=7)
        logger.info("G2B 전참여자 수집 완료: %s", result)
        if result.get("filled", 0) > 0:
            _trigger_ml_retrain("G2B 전참여자 수집 완료")
    except Exception as exc:
        logger.error("G2B 전참여자 수집 실패: %s", exc)
    finally:
        db.close()


def run_g2b_yega_job() -> None:
    """G2B 예비가격 상세 수집 (매일 21:15 KST — getOpengResultListInfoCnstwkPreparPcDetail).

    [Task #16] days_back=3으로 확장 — 당일+전일 개찰 건 커버.
    최근 3일 개찰 완료 공고의 복수예가 15개(추첨여부 포함)를
    g2b_yega_details 테이블에 upsert. ML pos_weights 학습 데이터로 활용.
    inpo21c_yega에 이미 데이터가 있는 공고는 자동 스킵.
    """
    from app.database import SessionLocal
    from app.collector.service import collect_g2b_yega_detail

    db = SessionLocal()
    try:
        result = collect_g2b_yega_detail(db, days_back=30)
        logger.info("G2B 예가상세 수집 완료: %s", result)
    except Exception as exc:
        logger.error("G2B 예가상세 수집 실패: %s", exc)
    finally:
        db.close()


def run_pre_spec_collect_job() -> None:
    """사전규격 공사 목록 수집 (매일 07:00 KST) — 입찰공고 前 최상위 신호."""
    from app.database import SessionLocal
    from app.collector.service import collect_pre_spec_notices

    db = SessionLocal()
    try:
        result = collect_pre_spec_notices(db, days_back=2)
        logger.info("사전규격 수집 완료: %s", result)
    except Exception as exc:
        logger.error("사전규격 수집 실패: %s", exc)
    finally:
        db.close()


def run_pre_spec_match_job() -> None:
    """사전규격 → 공고 매핑 재실행 (매일 12:00 KST) — 공고 등록 후 매핑 갱신."""
    from app.database import SessionLocal
    from app.collector.service import match_pre_spec_to_bids

    db = SessionLocal()
    try:
        result = match_pre_spec_to_bids(db)
        logger.info("사전규격 매핑 완료: %s", result)
    except Exception as exc:
        logger.error("사전규격 매핑 실패: %s", exc)
    finally:
        db.close()


def run_contract_collect_job() -> None:
    """계약정보 수집 (매일 23:00 KST) — 당일 계약체결 건 수집."""
    from app.database import SessionLocal
    from app.collector.service import collect_bid_contracts

    db = SessionLocal()
    try:
        result = collect_bid_contracts(db, days_back=2)
        logger.info("계약정보 수집 완료: %s", result)
    except Exception as exc:
        logger.error("계약정보 수집 실패: %s", exc)
    finally:
        db.close()


def run_competitor_stats_job() -> None:
    """경쟁사 통계 재계산 + GMM 재피팅 (매주 일요일 04:30 KST).

    bid_results 기반 competitor_stats upsert 후 GMM 클러스터 재피팅.
    """
    from app.database import SessionLocal
    from app.services.competitor import rebuild_competitor_stats

    db = SessionLocal()
    try:
        result = rebuild_competitor_stats(db)
        logger.info("경쟁사 통계 재계산: %s", result)
        # GMM 재피팅
        from app.ml.competitor_cluster import fit_from_db
        fit_from_db(db)
        logger.info("GMM 클러스터 재피팅 완료")
    except Exception as exc:
        logger.error("경쟁사 통계 재계산 실패: %s", exc)
    finally:
        db.close()


def run_missing_results_job() -> None:
    """낙찰결과 누락 보완 수집 (매주 수요일 03:00 KST).

    bid_executions(개찰대기/낙찰/패찰)에 bid_results가 없는 건을 G2B API로 보완.
    lookback_days=90, max_bids=200
    """
    from app.database import SessionLocal
    from app.collector.service import collect_results_for_missing_bids

    db = SessionLocal()
    try:
        result = collect_results_for_missing_bids(db, lookback_days=90, max_bids=200)
        logger.info("낙찰결과 누락 보완: %s", result)
        if result.get("filled", 0) > 0:
            _trigger_ml_retrain("낙찰결과 누락 보완 완료")
    except Exception as exc:
        logger.error("낙찰결과 누락 보완 실패: %s", exc)
    finally:
        db.close()


def run_agency_budget_patterns_job() -> None:
    """발주기관 예산 집행 패턴 재계산 (매주 월 05:30 KST).

    bids 히스토리 기반 월별 surge_index 산출 → agency_budget_patterns upsert.
    """
    from app.database import SessionLocal
    from app.services.agency import rebuild_agency_budget_patterns

    db = SessionLocal()
    try:
        result = rebuild_agency_budget_patterns(db)
        logger.info("agency_budget_patterns 재계산: %s", result)
    except Exception as exc:
        logger.error("agency_budget_patterns 재계산 실패: %s", exc)
    finally:
        db.close()


def run_kiscon_collect_job() -> None:
    """경쟁사 실적 프로필 집계 (매주 일 03:30 KST).

    biz_reg_no 보유 상위 300개 경쟁사에 대해 bid_results 집계:
    - 면허 업종 역추론 (참여 공고 industry 분포)
    - 주력 발주기관 top5 + 낙찰률
    - 강점 기관 (낙찰률 30%+, 회피 전략 대상)
    - 최근 2년 투찰·낙찰·금액 실적
    → competitor_kiscon_profiles upsert
    """
    from app.database import SessionLocal
    from app.collector.kiscon_service import collect_kiscon_profiles

    db = SessionLocal()
    try:
        result = collect_kiscon_profiles(db, limit=300, force_refresh=False)
        logger.info("경쟁사 실적 프로필 집계 완료: %s", result)
    except Exception as exc:
        logger.error("경쟁사 실적 프로필 집계 실패: %s", exc)
    finally:
        db.close()


def run_backfill_incremental_job() -> None:
    """G2B 역사 낙찰 데이터 증분 갱신 (매월 2일 02:00 KST).
    전월 1개월치를 수집해 신규 낙찰 결과를 보완한다.
    """
    from app.database import SessionLocal
    from app.collector.service import backfill_historical_bids
    from datetime import datetime, timedelta

    db = SessionLocal()
    try:
        # 전월 범위
        today = datetime.now()
        first_of_this_month = today.replace(day=1)
        last_month_end = first_of_this_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        date_from = last_month_start.strftime("%Y-%m-%d")
        date_to   = last_month_end.strftime("%Y-%m-%d")

        result = backfill_historical_bids(db, date_from=date_from, date_to=date_to)
        logger.info("역사데이터 증분 갱신 완료: %s", result)
        if result.get("inserted_results", 0) > 50:
            _trigger_ml_retrain("월별 백필 완료")
    except Exception as exc:
        logger.error("역사데이터 증분 갱신 실패: %s", exc)
    finally:
        db.close()


def create_scheduler() -> BackgroundScheduler:
    """BackgroundScheduler 생성 및 작업 등록."""
    scheduler = BackgroundScheduler(timezone="Asia/Seoul")

    scheduler.add_job(
        run_auto_qualify_bids_job,
        trigger=CronTrigger(hour=7, minute=0, timezone="Asia/Seoul"),
        id="auto_qualify_bids_daily",
        name="신규 공고 자동 적격 판정 (매일 07:00 KST)",
        replace_existing=True,
        max_instances=1,
    )
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
        run_auto_register_job,
        trigger=CronTrigger(hour=20, minute=30, timezone="Asia/Seoul"),
        id="auto_register_inpo21c_daily",
        name="inpo21c 참여 이력 자동 등록 (매일 20:30 KST)",
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
    scheduler.add_job(
        run_competitor_anomaly_job,
        trigger=CronTrigger(hour=9, minute=0, timezone="Asia/Seoul"),
        id="competitor_anomaly_daily",
        name="경쟁사 담합 의심 패턴 스캔 (매일 09:00 KST)",
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
        trigger=CronTrigger(day_of_week="sun", hour=6, minute=0, timezone="Asia/Seoul"),
        id="freq_rebuild_weekly",
        name="발주기관 빈도표+전략 재계산 (매주 일 06:00 KST)",
        replace_existing=True,
        max_instances=1,
    )
    # 전국 낙찰 수집: 화·목·일 05:30 KST (주 3회 — fstock 백필 피크 타임 이후)
    for dow, hh, mm in (("tue", 5, 30), ("thu", 5, 30), ("sun", 5, 30)):
        scheduler.add_job(
            run_inpo21c_national_job,
            trigger=CronTrigger(day_of_week=dow, hour=hh, minute=mm, timezone="Asia/Seoul"),
            id=f"collect_inpo21c_national_{dow}",
            name=f"inpo21c 전국 낙찰 수집 ({dow} {hh:02d}:{mm:02d} KST)",
            replace_existing=True,
            max_instances=1,
        )
    # 지역별 수집: 미수집 지역(전남·경남·충남·충북·전북·경기·서울) 순환 — 주 2회
    # 수·토 22:00 KST, 지역 7개 × 건축 건 중심 전참여자 확보
    for i, (dow, hh, region) in enumerate((
        ("wed", 22, "경기"),   ("sat", 22, "서울"),
        ("wed", 23, "경남"),   ("sat", 23, "충남"),
        ("thu", 22, "전남"),   ("sun", 22, "충북"),
    )):
        scheduler.add_job(
            run_inpo21c_region_job,
            trigger=CronTrigger(day_of_week=dow, hour=hh, minute=0, timezone="Asia/Seoul"),
            args=[region, "건축"],
            id=f"inpo21c_region_{region}",
            name=f"inpo21c 지역수집 [{region}/건축] ({dow} {hh:02d}:00 KST)",
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
    # KPI 스냅샷 일별 갱신 (매일 22:30 KST — journal_auto_fill 완료 후)
    scheduler.add_job(
        run_kpi_snapshot_job,
        trigger=CronTrigger(hour=22, minute=30, timezone="Asia/Seoul"),
        id="kpi_snapshot_daily",
        name="KPI 스냅샷 일별 갱신 (매일 22:30 KST)",
        replace_existing=True,
        max_instances=1,
    )
    # 참가자 수 부족 입찰 재수집 (매주 토요일 04:00 KST — win_prob_model 학습 데이터 품질 향상)
    scheduler.add_job(
        run_incomplete_participants_job,
        trigger=CronTrigger(day_of_week="sat", hour=4, minute=0, timezone="Asia/Seoul"),
        id="incomplete_participants_weekly",
        name="참가자 수 부족 입찰 재수집 (매주 토 04:00 KST)",
        replace_existing=True,
        max_instances=1,
    )
    # G2B 전참여자 수집 (매일 21:00 KST — inpo21c 수집 후 fallback/draw_no 보완)
    # [Phase 1] inpo21c(20:00) 이후로 이동: inpo21c 있는 공고는 draw_no만 보완
    scheduler.add_job(
        run_g2b_all_participants_job,
        trigger=CronTrigger(hour=21, minute=0, timezone="Asia/Seoul"),
        id="g2b_all_participants_daily",
        name="G2B 전참여자 수집 (매일 21:00 KST — inpo21c fallback)",
        replace_existing=True,
        max_instances=1,
    )
    # G2B 예비가격 상세 수집 (매일 21:15 KST — inpo21c 이후 미수집 공고 fallback)
    # [Phase 1] inpo21c_yega 있는 공고는 자동 스킵
    scheduler.add_job(
        run_g2b_yega_job,
        trigger=CronTrigger(hour=21, minute=15, timezone="Asia/Seoul"),
        id="g2b_yega_detail_daily",
        name="G2B 예비가격 상세 수집 (매일 21:15 KST — inpo21c fallback)",
        replace_existing=True,
        max_instances=1,
    )
    # [Phase 2] 사전규격 공사 목록 수집 (매일 07:00 KST — 입찰 前 최상위 신호)
    scheduler.add_job(
        run_pre_spec_collect_job,
        trigger=CronTrigger(hour=7, minute=0, timezone="Asia/Seoul"),
        id="pre_spec_collect_daily",
        name="사전규격 수집 (매일 07:00 KST)",
        replace_existing=True,
        max_instances=1,
    )
    # [Phase 2] 사전규격 → 공고 매핑 (매일 12:00 KST — 공고 등록 후 갱신)
    scheduler.add_job(
        run_pre_spec_match_job,
        trigger=CronTrigger(hour=12, minute=0, timezone="Asia/Seoul"),
        id="pre_spec_match_daily",
        name="사전규격 공고 매핑 (매일 12:00 KST)",
        replace_existing=True,
        max_instances=1,
    )
    # [Phase 3] 계약정보 수집 (매일 23:00 KST — 당일 계약체결 건)
    scheduler.add_job(
        run_contract_collect_job,
        trigger=CronTrigger(hour=23, minute=0, timezone="Asia/Seoul"),
        id="contract_collect_daily",
        name="계약정보 수집 (매일 23:00 KST)",
        replace_existing=True,
        max_instances=1,
    )
    # 역사 데이터 월별 증분 갱신 (매월 2일 02:00 KST — 전월 데이터 보완)
    scheduler.add_job(
        run_backfill_incremental_job,
        trigger=CronTrigger(day=2, hour=2, minute=0, timezone="Asia/Seoul"),
        id="backfill_incremental_monthly",
        name="G2B 역사데이터 증분 갱신 (매월 2일 02:00 KST)",
        replace_existing=True,
        max_instances=1,
    )
    # [Task #14] 낙찰결과 누락 보완 수집 (매주 수요일 03:00 KST)
    scheduler.add_job(
        run_missing_results_job,
        trigger=CronTrigger(day_of_week="wed", hour=3, minute=0, timezone="Asia/Seoul"),
        id="collect_missing_results_weekly",
        name="낙찰결과 누락 보완 수집 (매주 수 03:00 KST)",
        replace_existing=True,
        max_instances=1,
    )
    # [Task #17] 경쟁사 통계 재계산 + GMM 재피팅 (매주 일요일 04:30 KST)
    scheduler.add_job(
        run_competitor_stats_job,
        trigger=CronTrigger(day_of_week="sun", hour=4, minute=30, timezone="Asia/Seoul"),
        id="competitor_stats_weekly",
        name="경쟁사 통계 재계산+GMM 재피팅 (매주 일 04:30 KST)",
        replace_existing=True,
        max_instances=1,
    )
    # [Task #18] 발주기관 예산 집행 패턴 재계산 (매주 월 05:30 KST)
    scheduler.add_job(
        run_agency_budget_patterns_job,
        trigger=CronTrigger(day_of_week="mon", hour=5, minute=30, timezone="Asia/Seoul"),
        id="agency_budget_patterns_weekly",
        name="발주기관 예산 집행 패턴 재계산 (매주 월 05:30 KST)",
        replace_existing=True,
        max_instances=1,
    )
    # [#8] KISCON 경쟁사 면허·실적 수집 (매주 일 03:30 KST — competitor_stats 재계산 전)
    scheduler.add_job(
        run_kiscon_collect_job,
        trigger=CronTrigger(day_of_week="sun", hour=3, minute=30, timezone="Asia/Seoul"),
        id="kiscon_profiles_weekly",
        name="KISCON 경쟁사 면허·실적 수집 (매주 일 03:30 KST)",
        replace_existing=True,
        max_instances=1,
    )

    # [#13] VACUUM ANALYZE 정기 실행 (매주 토 02:00 KST)
    scheduler.add_job(
        run_vacuum_analyze_job,
        trigger=CronTrigger(day_of_week="sat", hour=2, minute=0, timezone="Asia/Seoul"),
        id="vacuum_analyze_weekly",
        name="VACUUM ANALYZE 주간 실행 (매주 토 02:00 KST)",
        replace_existing=True,
        max_instances=1,
    )

    return scheduler