"""관리자 전용 API — 사용자 관리 + 공종 필터 + 시스템 상태 모니터링."""
import logging
import os

logger = logging.getLogger(__name__)

from typing import Optional, List
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from ...database import get_db
from ...models import User, Industry, IndustryFilter, CollectionLog
from ...schemas import CollectionLogOut
from ...common.security import require_role, hash_password
from ...services import AdminService

_admin_svc = AdminService()

router = APIRouter(prefix="/admin", tags=["관리자"])


class UserUpdateBody(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_role("admin"))):
    return _admin_svc.list_users(db)


class UserCreateBody(BaseModel):
    email: str
    password: str
    name: str
    role: str = "viewer"
    department: Optional[str] = None


@router.post("/users", status_code=201)
def create_user(
    body: UserCreateBody,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    return _admin_svc.create_user(
        db, email=body.email, password=body.password,
        name=body.name, role=body.role, department=body.department,
    )


@router.put("/users/{uid}")
def update_user(
    uid: int,
    body: UserUpdateBody,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    return _admin_svc.update_user(
        db, uid=uid, admin_id=admin.id,
        name=body.name, role=body.role, department=body.department,
        is_active=body.is_active, password=body.password,
    )


@router.delete("/users/{uid}", status_code=204)
def delete_user(
    uid: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    _admin_svc.delete_user(db, uid=uid, admin_id=admin.id)


# ── 공종 관리 ──────────────────────────────────────────────────────────

@router.get("/industries")
def get_industry_filters(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """모든 공종 목록과 활성화 여부 반환."""
    return _admin_svc.get_industry_filters(db)


class IndustryFilterBody(BaseModel):
    active_ids: List[int]  # 활성화할 공종 ID 목록


@router.put("/industries/filters")
def update_industry_filters(
    body: IndustryFilterBody,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """활성 공종 목록 저장. active_ids 에 없는 공종은 비활성 처리."""
    return _admin_svc.update_industry_filters(db, body.active_ids)


@router.post("/ml/retrain")
def retrain_ml(
    _: User = Depends(require_role("admin")),
):
    """ML 모델 재학습 — assessment_rate_stats 집계 + Engine A+B 학습 (별도 스레드)."""
    import threading
    def _run():
        import traceback
        import pandas as pd
        from datetime import datetime, timedelta
        from ...database import SessionLocal
        from ...ml.assessment import compute_and_store_stats, train_srate_model
        from ...ml.engine import train_models, build_features, FEATURE_COLS, get_engine
        db = SessionLocal()
        results = {}
        try:
            # Engine A: 사정율 통계 및 모델
            try:
                n = compute_and_store_stats(db)
                results["srate_stats"] = n
                ok = train_srate_model(db)
                results["srate_model"] = "trained" if ok else "skipped_insufficient_data"
            except Exception as e:
                results["srate_error"] = str(e)

            # Engine B: 낙찰률 회귀 모델
            try:
                train_cutoff = datetime.now() - timedelta(days=36*30)
                rows = db.execute(text("""
                    SELECT b.id, b.agency_id, b.industry_id,
                           COALESCE(b.region_id, 0) AS region_id,
                           b.base_amount, b.bid_open_date,
                           COALESCE(b.region_restriction, false),
                           b.construction_period, r.bid_rate
                    FROM bids b
                    JOIN bid_results r ON r.bid_id = b.id AND r.is_winner = true
                    WHERE b.base_amount > 0
                      AND r.bid_rate BETWEEN 0.80 AND 1.00
                      AND b.bid_open_date >= :cutoff
                    ORDER BY b.bid_open_date
                    LIMIT 5000
                """), {"cutoff": train_cutoff}).fetchall()

                cutoff = datetime.now() - timedelta(days=24*30)
                hist_rows = db.execute(text("""
                    SELECT b.id, b.agency_id, b.industry_id,
                           COALESCE(b.region_id, 0), b.base_amount, b.bid_open_date,
                           r.bid_rate,
                           (SELECT COUNT(*) FROM bid_results r2 WHERE r2.bid_id = b.id)
                    FROM bids b
                    LEFT JOIN bid_results r ON r.bid_id = b.id AND r.is_winner = true
                    WHERE b.bid_open_date >= :cutoff AND b.base_amount > 0
                    LIMIT 10000
                """), {"cutoff": cutoff}).fetchall()

                hist_df = pd.DataFrame(hist_rows, columns=[
                    "id","agency_id","industry_id","region_id",
                    "base_amount","bid_open_date","winner_rate","competitor_count"
                ])
                for col in ["winner_rate","base_amount","competitor_count"]:
                    hist_df[col] = pd.to_numeric(hist_df[col], errors="coerce")
                hist_df["bid_open_date"] = pd.to_datetime(hist_df["bid_open_date"], errors="coerce")
                hist_df = hist_df.sort_values("bid_open_date").reset_index(drop=True)
                hist_dates = hist_df["bid_open_date"].values

                records = []
                for row in rows:
                    bid_id, agency_id, industry_id, region_id, base_amount, bid_open_date, region_restriction, construction_period, winner_rate = row
                    if winner_rate is None:
                        continue
                    if bid_open_date is not None:
                        import numpy as _np
                        _ts = pd.Timestamp(bid_open_date).to_datetime64()
                        _idx = int(_np.searchsorted(hist_dates, _ts, side="left"))
                        hist_before = hist_df.iloc[:_idx]
                    else:
                        hist_before = hist_df
                    try:
                        feats = build_features(
                            agency_id=int(agency_id) if agency_id else 0,
                            industry_id=int(industry_id) if industry_id else 0,
                            region_id=int(region_id),
                            base_amount=int(base_amount),
                            construction_period=int(construction_period) if construction_period else None,
                            region_restriction=bool(region_restriction),
                            bid_open_date=bid_open_date,
                            historical_df=hist_before,
                        )
                        feats["target_rate"] = float(winner_rate)
                        feats["is_winner"]   = True
                        records.append(feats)
                    except Exception:
                        pass

                # clf_df: inpo21c_participants에서 낙찰자+비낙찰자 추출 (win_model 학습용)
                clf_records = []
                try:
                    clf_rows = db.execute(text("""
                        SELECT b.agency_id, b.industry_id,
                               COALESCE(b.region_id, 0) AS region_id,
                               b.base_amount, b.bid_open_date,
                               COALESCE(b.region_restriction, false),
                               b.construction_period,
                               p.bid_rate, p.is_winner
                        FROM inpo21c_participants p
                        JOIN inpo21c_bids ib ON ib.inpo21c_bid_id = p.inpo21c_bid_id
                        JOIN bids b ON b.announcement_no = ib.announcement_no
                        WHERE b.agency_id IS NOT NULL AND b.industry_id IS NOT NULL
                          AND b.base_amount > 0
                          AND p.bid_rate BETWEEN 0.80 AND 1.00
                        ORDER BY b.bid_open_date DESC
                        LIMIT 3000
                    """)).fetchall()
                    import numpy as _np_clf
                    for crow in clf_rows:
                        c_agency, c_ind, c_reg, c_amt, c_dt, c_rr, c_cp, c_rate, c_win = crow
                        if c_rate is None:
                            continue
                        if c_dt is not None:
                            _ts2 = pd.Timestamp(c_dt).to_datetime64()
                            _idx2 = int(_np_clf.searchsorted(hist_dates, _ts2, side="left"))
                            hist_b = hist_df.iloc[:_idx2]
                        else:
                            hist_b = hist_df
                        try:
                            cf = build_features(
                                agency_id=int(c_agency) if c_agency else 0,
                                industry_id=int(c_ind) if c_ind else 0,
                                region_id=int(c_reg),
                                base_amount=int(c_amt),
                                construction_period=int(c_cp) if c_cp else None,
                                region_restriction=bool(c_rr),
                                bid_open_date=c_dt,
                                historical_df=hist_b,
                            )
                            cf["target_rate"] = float(c_rate)
                            cf["our_bid_rate"] = float(c_rate)
                            cf["is_winner"]    = bool(c_win)
                            clf_records.append(cf)
                        except Exception:
                            pass
                except Exception as _clf_err:
                    logger.warning("clf_df 빌드 실패: %s", _clf_err)

                logger.info("clf_records 빌드 완료: %d건 (pos=%d neg=%d)",
                            len(clf_records),
                            sum(1 for r in clf_records if r.get("is_winner")),
                            sum(1 for r in clf_records if not r.get("is_winner")))

                if len(records) >= 20:
                    train_df = pd.DataFrame(records)
                    for col in FEATURE_COLS:
                        if col not in train_df.columns:
                            train_df[col] = None
                    clf_df = None
                    if len(clf_records) >= 20:
                        clf_df = pd.DataFrame(clf_records)
                        for col in FEATURE_COLS:
                            if col not in clf_df.columns:
                                clf_df[col] = None
                        results["clf_df_size"] = len(clf_df)
                    res = train_models(train_df, clf_df=clf_df)
                    if res:
                        get_engine().reload()
                        results["engine_b"] = res
                    else:
                        results["engine_b"] = "failed"
                else:
                    results["engine_b"] = f"skipped_insufficient_data ({len(records)}건)"
            except Exception as e:
                results["engine_b_error"] = traceback.format_exc()

            # win_prob_model: inpo21c 실증 낙찰확률 모델
            try:
                from ...ml.win_prob_model import train as _wp_train
                wp_result = _wp_train(db)
                results["win_prob_model"] = wp_result
            except Exception as e:
                results["win_prob_model_error"] = str(e)

            # GMM 재피팅 (복수예가 필터 적용)
            try:
                from ...ml.competitor_cluster import fit_from_db as _gmm_fit
                _gmm_fit(db)
                results["gmm"] = "fitted"
            except Exception as e:
                results["gmm_error"] = str(e)

            logger.info("ML 재학습 완료: %s", results)
        except Exception as _outer_exc:
            import traceback as _tb
            logger.error("ML 재학습 외부 예외: %s", _tb.format_exc())
        finally:
            db.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"status": "started", "message": "ML 재학습 시작됨 (별도 스레드) — 완료까지 1~3분 소요"}


@router.post("/ml/train-win-prob")
def train_win_prob(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    inpo21c 실증 낙찰확률 모델(win_prob_model) 즉시 학습.
    31,579건 복수예가 참가자 데이터 → LightGBM 이진 분류.
    """
    import threading

    def _run():
        from ...database import SessionLocal
        from ...ml.win_prob_model import train as _wp_train
        _db = SessionLocal()
        try:
            result = _wp_train(_db)
            logger.info("win_prob_model 학습 결과: %s", result)
        finally:
            _db.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {
        "status": "started",
        "message": "win_prob_model 학습 시작 (약 30~60초 소요). /admin/ml/status에서 결과 확인.",
    }


@router.get("/ml/win-prob-status")
def win_prob_status(
    _: User = Depends(require_role("admin")),
):
    """win_prob_model 학습 현황 조회."""
    from ...ml.win_prob_model import model_info
    import datetime
    info = model_info()
    if info.get("trained_at"):
        info["trained_at_str"] = datetime.datetime.fromtimestamp(info["trained_at"]).strftime("%Y-%m-%d %H:%M:%S")
    return info


@router.get("/collector-status")
def get_collector_status(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """오늘 수집량·마지막/다음 수집 시각 실시간 조회."""
    return _admin_svc.get_collector_status(db)


@router.get("/system-status")
def system_status(db: Session = Depends(get_db), _: User = Depends(require_role("admin"))):
    return _admin_svc.get_system_status(db)


@router.get("/ml/status")
def ml_status_stub():
    """레거시 호환 stub — 인증 없이 200 반환해 구 클라이언트 캐시 폴링이 401 루프를 유발하지 않도록."""
    return {"status": "ok", "message": "Use /admin/system-status"}


@router.get("/ml/performance")
def ml_performance(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """bid_journal 기반 모델 성능 지표 실시간 계산 후 model_performance_log에 저장."""
    from datetime import date
    from ...models import ModelPerformanceLog
    from ...ml.engine import get_model_meta

    row = db.execute(text("""
        SELECT
            COUNT(*)                                                        AS total,
            COUNT(result)                                                   AS with_result,
            SUM(CASE WHEN result = '낙찰' THEN 1 ELSE 0 END)              AS wins,
            AVG(ABS(srate_error))                                           AS mae_srate,
            SQRT(AVG(POWER(srate_error, 2)))                                AS rmse_srate,
            AVG(ABS(rate_gap))                                              AS avg_rate_gap,
            AVG(CASE WHEN result != '낙찰' THEN ABS(rate_gap) ELSE NULL END) AS avg_rate_gap_loss,
            AVG(CASE WHEN result = '낙찰' THEN rate_delta ELSE NULL END)   AS avg_rate_delta_win,
            COUNT(CASE WHEN result IS NOT NULL AND submitted_rate IS NOT NULL THEN 1 END)::float
                / NULLIF(COUNT(CASE WHEN submitted_rate IS NOT NULL THEN 1 END)::float, 0)
                                                                            AS feedback_completeness
        FROM bid_journal
        WHERE submitted_rate IS NOT NULL
    """)).fetchone()

    meta = get_model_meta()
    today = date.today()

    total            = int(row[0] or 0)
    with_result      = int(row[1] or 0)
    wins             = int(row[2] or 0)
    mae_srate        = float(row[3]) if row[3] is not None else None
    rmse_srate       = float(row[4]) if row[4] is not None else None
    avg_rate_gap     = float(row[5]) if row[5] is not None else None
    avg_rate_gap_loss= float(row[6]) if row[6] is not None else None
    avg_delta_win    = float(row[7]) if row[7] is not None else None
    completeness     = float(row[8]) if row[8] is not None else 0.0

    win_rate = wins / with_result if with_result > 0 else None

    # model_performance_log에 오늘 기록 upsert
    try:
        existing = db.execute(text("""
            SELECT id FROM model_performance_log
            WHERE model_name = 'bid_journal_feedback' AND eval_date = :today
        """), {"today": today}).fetchone()

        if existing:
            db.execute(text("""
                UPDATE model_performance_log SET
                    sample_count = :sample_count,
                    mae          = :mae,
                    rmse         = :rmse,
                    win_rate_with_model = :win_rate,
                    model_version = :version
                WHERE id = :id
            """), {
                "sample_count": with_result,
                "mae": mae_srate,
                "rmse": rmse_srate,
                "win_rate": win_rate,
                "version": meta.get("version"),
                "id": existing[0],
            })
        else:
            db.execute(text("""
                INSERT INTO model_performance_log
                    (model_name, model_version, eval_date, sample_count, mae, rmse, win_rate_with_model)
                VALUES
                    ('bid_journal_feedback', :version, :today, :sample_count, :mae, :rmse, :win_rate)
            """), {
                "version": meta.get("version"),
                "today": today,
                "sample_count": with_result,
                "mae": mae_srate,
                "rmse": rmse_srate,
                "win_rate": win_rate,
            })
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("model_performance_log 저장 실패: %s", e)

    # 최근 30일 일별 낙찰 현황
    daily = db.execute(text("""
        SELECT DATE(created_at) AS day,
               COUNT(*)         AS total,
               SUM(CASE WHEN result = '낙찰' THEN 1 ELSE 0 END) AS wins
        FROM bid_journal
        WHERE result IS NOT NULL AND created_at >= NOW() - INTERVAL '30 days'
        GROUP BY day ORDER BY day DESC
    """)).fetchall()

    return {
        "model_version":       meta.get("version", "unknown"),
        "eval_date":           today.isoformat(),
        "total_journals":      total,
        "with_result":         with_result,
        "wins":                wins,
        "win_rate":            round(win_rate, 4) if win_rate is not None else None,
        "mae_srate":           round(mae_srate, 6) if mae_srate is not None else None,
        "rmse_srate":          round(rmse_srate, 6) if rmse_srate is not None else None,
        "avg_rate_gap":        round(avg_rate_gap, 6) if avg_rate_gap is not None else None,
        "avg_rate_gap_loss":   round(avg_rate_gap_loss, 6) if avg_rate_gap_loss is not None else None,
        "avg_rate_delta_win":  round(avg_delta_win, 6) if avg_delta_win is not None else None,
        "feedback_completeness": round(completeness, 4),
        "daily_results": [
            {"date": str(r[0]), "total": r[1], "wins": r[2]}
            for r in daily
        ],
    }


@router.get("/inpo21c/status")
def inpo21c_status(_: User = Depends(require_role("admin"))):
    """inpo21c 쿠키 유효성 및 수집 통계 조회."""
    from ...config import get_settings
    from ...collector.inpo21c import check_cookie_valid

    settings = get_settings()
    cookie      = getattr(settings, "inpo21c_cookie", "")
    has_id_pw   = bool(getattr(settings, "inpo21c_id", "") and getattr(settings, "inpo21c_pw", ""))

    has_cookie = bool(cookie)
    is_valid   = check_cookie_valid(cookie) if has_cookie else False

    # ID/PW 설정 시: 쿠키 없어도 자동 로그인으로 수집 가능
    can_collect = is_valid or has_id_pw

    if is_valid:
        status, message = "ok", "쿠키 정상"
    elif has_id_pw:
        status  = "autologin"
        message = "자동 로그인 가능 (INPO21C_ID/PW 설정됨) — 수집 시 자동 인증"
    elif has_cookie:
        status, message = "expired", "쿠키 만료 — INPO21C_COOKIE를 갱신하거나 INPO21C_ID/PW를 설정하세요"
    else:
        status  = "no_cookie"
        message = "INPO21C_COOKIE 미설정 — .env에 INPO21C_COOKIE 또는 INPO21C_ID/INPO21C_PW를 추가하세요"

    return {
        "has_cookie":   has_cookie,
        "cookie_valid": is_valid,
        "has_autologin": has_id_pw,
        "can_collect":  can_collect,
        "status":       status,
        "message":      message,
    }


@router.post("/journal/auto-fill")
def trigger_journal_auto_fill(
    background_tasks: BackgroundTasks,
    _: User = Depends(require_role("admin")),
):
    """투찰저널 개찰결과 자동 수집 즉시 실행 (스케줄 대기 없이)."""
    from ...collector.scheduler import run_journal_auto_fill_job
    background_tasks.add_task(run_journal_auto_fill_job)
    return {"status": "started", "message": "개찰결과 자동 수집 시작됨 (백그라운드)"}


@router.get("/ml/bias-report")
def ml_bias_report(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """기관별 사정율 예측 편향 리포트 — bid_journal.srate_error 기반."""
    rows = db.execute(text("""
        SELECT
            b.agency_id,
            a.name AS agency_name,
            COUNT(*)                         AS n,
            ROUND(AVG(j.srate_error)::numeric, 6)    AS bias_mean,
            ROUND(STDDEV(j.srate_error)::numeric, 6) AS bias_std,
            ROUND(AVG(ABS(j.srate_error))::numeric, 6) AS mae
        FROM bid_journal j
        JOIN bids b ON b.id = j.bid_id
        LEFT JOIN agencies a ON a.id = b.agency_id
        WHERE j.srate_error IS NOT NULL
        GROUP BY b.agency_id, a.name
        HAVING COUNT(*) >= 3
        ORDER BY ABS(AVG(j.srate_error)) DESC
        LIMIT 30
    """)).fetchall()

    global_row = db.execute(text("""
        SELECT COUNT(*), ROUND(AVG(srate_error)::numeric, 6), ROUND(AVG(ABS(srate_error))::numeric, 6)
        FROM bid_journal
        WHERE srate_error IS NOT NULL
    """)).fetchone()

    return {
        "global": {
            "n":    int(global_row[0] or 0),
            "bias": float(global_row[1]) if global_row[1] else None,
            "mae":  float(global_row[2]) if global_row[2] else None,
        },
        "by_agency": [
            {
                "agency_id":   r[0],
                "agency_name": r[1],
                "n":           int(r[2]),
                "bias_mean":   float(r[3]) if r[3] else None,
                "bias_std":    float(r[4]) if r[4] else None,
                "mae":         float(r[5]) if r[5] else None,
            }
            for r in rows
        ],
    }


@router.post("/ml/compute-frequency")
def compute_frequency_tables(
    _: User = Depends(require_role("admin")),
):
    """사정율 빈도 분포 v2 재구축 (0.001 버킷 × 발주처 × 12M/24M/48M)."""
    import threading
    def _run():
        from ...database import SessionLocal
        from ...ml.assessment import compute_srate_frequency_v2
        db = SessionLocal()
        try:
            cnt = compute_srate_frequency_v2(db)
            logger.info("사정율 빈도 v2 재구축 완료: %d rows", cnt)
        except Exception:
            import traceback
            logger.error("빈도 재구축 오류:\n%s", traceback.format_exc())
        finally:
            db.close()
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"status": "started", "message": "사정율 빈도 테이블 재구축 시작 (1~3분 소요)"}


_TRIGGER_COLLECT_TYPES = {"all", "notices", "results"}


@router.post("/ml/populate-features")
def populate_feature_store(
    background_tasks: BackgroundTasks,
    overwrite: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """feature_store 일괄 계산 — 모든 closed bids에 ML 피처를 사전 계산하여 저장.

    overwrite=true 이면 기존 레코드를 덮어씀 (ON CONFLICT UPDATE),
    overwrite=false 이면 없는 것만 추가.
    """
    background_tasks.add_task(_run_populate_features, overwrite)
    return {"message": "feature_store 계산 시작됨 (백그라운드)", "overwrite": overwrite}


_FEATURE_STORE_CTE = """
    WITH
    bucketed AS (
        SELECT
            b.id,
            b.agency_id,
            b.industry_id,
            COALESCE(b.region_id, 0) AS region_id,
            b.base_amount,
            b.bid_open_date,
            CASE
                WHEN b.base_amount < 100000000   THEN 1
                WHEN b.base_amount < 500000000   THEN 2
                WHEN b.base_amount < 1000000000  THEN 3
                WHEN b.base_amount < 5000000000  THEN 4
                ELSE 5
            END AS amount_bucket,
            wr.bid_rate  AS winner_rate,
            COALESCE(NULLIF(b.participant_count, 0), cnt.comp_cnt) AS competitor_count
        FROM bids b
        LEFT JOIN LATERAL (
            SELECT bid_rate FROM bid_results
            WHERE bid_id = b.id AND is_winner = true
            LIMIT 1
        ) wr ON true
        LEFT JOIN (
            SELECT bid_id, COUNT(*) AS comp_cnt
            FROM bid_results GROUP BY bid_id
        ) cnt ON cnt.bid_id = b.id
        WHERE b.base_amount > 0
    ),
    agency_agg AS (
        SELECT
            agency_id,
            AVG(winner_rate)                                              AS agency_avg_rate,
            AVG(CASE WHEN winner_rate IS NOT NULL THEN 1.0 ELSE 0.0 END) AS agency_win_rate,
            COUNT(*)                                                       AS agency_bid_count,
            AVG(competitor_count)                                          AS avg_competitors
        FROM bucketed GROUP BY agency_id
    ),
    region_agg AS (
        SELECT region_id, AVG(winner_rate) AS region_avg_rate
        FROM bucketed GROUP BY region_id
    ),
    industry_agg AS (
        SELECT industry_id, AVG(winner_rate) AS industry_avg_rate
        FROM bucketed GROUP BY industry_id
    ),
    similar_agg AS (
        SELECT
            industry_id, region_id, amount_bucket,
            COUNT(*)            AS similar_count,
            AVG(winner_rate)    AS similar_avg_rate,
            STDDEV(winner_rate) AS similar_std_rate
        FROM bucketed
        GROUP BY industry_id, region_id, amount_bucket
    )
    INSERT INTO feature_store (
        bid_id,
        agency_avg_rate_12m, agency_win_rate_12m, agency_bid_count_12m,
        region_avg_rate_12m, industry_avg_rate_12m,
        expected_competitor_count, competitor_strength_score,
        season_index, amount_log10, amount_bucket,
        similar_bid_count, similar_avg_rate, similar_std_rate,
        computed_at
    )
    SELECT
        bk.id,
        aa.agency_avg_rate,
        aa.agency_win_rate,
        aa.agency_bid_count::INT,
        ra.region_avg_rate,
        ia.industry_avg_rate,
        COALESCE(aa.avg_competitors::INT, 10),
        5.00,
        CASE WHEN bk.bid_open_date IS NULL THEN 2
             ELSE (EXTRACT(MONTH FROM bk.bid_open_date)::INT - 1) / 3 + 1
        END,
        LOG(GREATEST(bk.base_amount::NUMERIC, 1)),
        bk.amount_bucket,
        COALESCE(sa.similar_count::INT, 0),
        sa.similar_avg_rate,
        sa.similar_std_rate,
        NOW()
    FROM bucketed bk
    LEFT JOIN agency_agg aa   ON aa.agency_id   = bk.agency_id
    LEFT JOIN region_agg ra   ON ra.region_id   = bk.region_id
    LEFT JOIN industry_agg ia ON ia.industry_id = bk.industry_id
    LEFT JOIN similar_agg sa
        ON  sa.industry_id   = bk.industry_id
        AND sa.region_id     = bk.region_id
        AND sa.amount_bucket = bk.amount_bucket
"""

_SQL_POPULATE_UPSERT = text(_FEATURE_STORE_CTE + """
    ON CONFLICT (bid_id) DO UPDATE SET
        agency_avg_rate_12m       = EXCLUDED.agency_avg_rate_12m,
        agency_win_rate_12m       = EXCLUDED.agency_win_rate_12m,
        agency_bid_count_12m      = EXCLUDED.agency_bid_count_12m,
        region_avg_rate_12m       = EXCLUDED.region_avg_rate_12m,
        industry_avg_rate_12m     = EXCLUDED.industry_avg_rate_12m,
        expected_competitor_count = EXCLUDED.expected_competitor_count,
        competitor_strength_score = EXCLUDED.competitor_strength_score,
        season_index              = EXCLUDED.season_index,
        amount_log10              = EXCLUDED.amount_log10,
        amount_bucket             = EXCLUDED.amount_bucket,
        similar_bid_count         = EXCLUDED.similar_bid_count,
        similar_avg_rate          = EXCLUDED.similar_avg_rate,
        similar_std_rate          = EXCLUDED.similar_std_rate,
        computed_at               = NOW()
""")

_SQL_POPULATE_INSERT = text(_FEATURE_STORE_CTE + "    ON CONFLICT (bid_id) DO NOTHING\n")


def _run_populate_features(overwrite: bool):
    import logging
    from ...database import SessionLocal
    _log = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        _log.info("feature_store 일괄 계산 시작 (overwrite=%s)", overwrite)
        sql = _SQL_POPULATE_UPSERT if overwrite else _SQL_POPULATE_INSERT
        result = db.execute(sql)
        db.commit()
        inserted = result.rowcount
        _log.info("feature_store 계산 완료: %d건 저장", inserted)
    except Exception as exc:
        db.rollback()
        _log.error("feature_store 계산 오류: %s", exc, exc_info=True)
    finally:
        db.close()


@router.post("/collect/trigger")
def trigger_collection(
    collect_type: str = "all",
    background_tasks: BackgroundTasks = None,
    _: User = Depends(require_role("admin")),
):
    """즉시 수집 실행 — 백그라운드로 처리하고 즉시 응답 반환."""
    if collect_type not in _TRIGGER_COLLECT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"collect_type은 {sorted(_TRIGGER_COLLECT_TYPES)} 중 하나여야 합니다.",
        )
    from ...collector.scheduler import run_collection_job
    background_tasks.add_task(run_collection_job, collect_type)
    return {"message": "수집 시작됨"}


@router.get("/collection-logs", response_model=list[CollectionLogOut])
def collection_logs(
    days: int = 7,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    return _admin_svc.get_collection_logs(db, days=days)


@router.get("/collection-logs/{log_id}", response_model=CollectionLogOut)
def collection_log_detail(
    log_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    return _admin_svc.get_collection_log_detail(db, log_id)


@router.get("/scheduler-jobs")
def list_scheduler_jobs(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """스케줄 작업 목록 + 마지막/다음 실행 시각 반환.
    APScheduler 인스턴스에 직접 접근하는 대신 DB 수집 로그와 고정 스케줄 정보를 조합.
    (멀티워커 환경에서 master 워커만 스케줄러를 보유하므로 API 워커에서 직접 접근 불가)
    """
    from datetime import timezone

    # 고정 스케줄 정의 (scheduler.py create_scheduler()와 동기화)
    # KST = UTC+9, cron 트리거는 UTC 기준
    SCHEDULE_DEFS = [
        {"id": "collect_notices_daily",             "name": "공고 수집 (G2B)",          "hour_utc": 18, "minute": 0,  "types": ("notice_cnstwk", "notice_servc", "notice_thng")},
        {"id": "collect_results_and_sync_daily",    "name": "낙찰결과 수집 + 동기화",    "hour_utc": 19, "minute": 0,  "types": ("result",)},
        {"id": "collect_scsbid_daily",              "name": "입찰결과 수집 (SCSBID)",     "hour_utc": 19, "minute": 30, "types": ("scsbid",)},
        {"id": "collect_bid_notices_inpo21c_daily", "name": "inpo21c 공고 수집",          "hour_utc": 20, "minute": 0,  "types": ("inpo21c_notice",)},
        {"id": "collect_inpo21c_daily",             "name": "inpo21c 참여자 수집",        "hour_utc": 20, "minute": 30, "types": ("inpo21c", "inpo21c_region", "inpo21c_national")},
        {"id": "journal_auto_fill_daily",           "name": "저널 자동 채우기",           "hour_utc": 21, "minute": 0,  "types": ("journal_auto_fill",)},
    ]

    all_types = [t for s in SCHEDULE_DEFS for t in s["types"]]
    rows_last = db.execute(text("""
        SELECT collect_type, MAX(collected_at), SUM(success_count), SUM(fail_count)
        FROM collection_logs
        WHERE collect_type = ANY(:types)
        GROUP BY collect_type
    """), {"types": all_types}).fetchall()
    type_map: dict = {r[0]: {"last_run": r[1], "success": int(r[2] or 0), "fail": int(r[3] or 0)} for r in rows_last}

    from datetime import datetime, timedelta
    now_utc = datetime.now(timezone.utc)

    result = []
    for sched in SCHEDULE_DEFS:
        candidates = [type_map[t]["last_run"] for t in sched["types"] if t in type_map and type_map[t]["last_run"]]
        last_run = max(candidates) if candidates else None

        # 다음 실행 시각 계산 (고정 cron UTC)
        h, m = sched["hour_utc"], sched["minute"]
        today_run = now_utc.replace(hour=h, minute=m, second=0, microsecond=0)
        next_run = today_run if today_run > now_utc else today_run + timedelta(days=1)

        total_success = sum(type_map[t]["success"] for t in sched["types"] if t in type_map)
        total_fail    = sum(type_map[t]["fail"]    for t in sched["types"] if t in type_map)

        result.append({
            "id":           sched["id"],
            "name":         sched["name"],
            "next_run_at":  next_run.isoformat(),
            "last_run_at":  last_run.isoformat() if last_run else None,
            "total_success": total_success,
            "total_fail":    total_fail,
        })

    result.sort(key=lambda x: x["next_run_at"])
    return result


@router.get("/collection-stats")
def collection_stats(
    days: int = 30,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """수집 유형별 통계 (총 성공건수, 실패건수, 평균 소요시간, 마지막 수집일, 실행 횟수)."""
    rows = db.execute(text("""
        SELECT
            collect_type,
            SUM(success_count)              AS total_success,
            SUM(fail_count)                 AS total_fail,
            AVG(duration_sec)               AS avg_duration,
            MAX(collected_at)               AS last_run_at,
            COUNT(*)                        AS run_count
        FROM collection_logs
        WHERE collected_at >= NOW() - INTERVAL '1 day' * :days
        GROUP BY collect_type
        ORDER BY last_run_at DESC NULLS LAST
    """), {"days": days}).fetchall()

    return [
        {
            "collect_type":  r[0],
            "total_success": int(r[1] or 0),
            "total_fail":    int(r[2] or 0),
            "avg_duration":  float(r[3]) if r[3] is not None else None,
            "last_run_at":   r[4].isoformat() if r[4] else None,
            "run_count":     int(r[5] or 0),
        }
        for r in rows
    ]


class InpoCookieBody(BaseModel):
    cookie: str


@router.post("/inpo21c/update-cookie")
def update_inpo21c_cookie(
    body: InpoCookieBody,
    _: User = Depends(require_role("admin")),
):
    """inpo21c 세션 쿠키 갱신 (환경변수 INPO21C_COOKIE 런타임 업데이트)."""
    import os
    from ...config import get_settings
    os.environ["INPO21C_COOKIE"] = body.cookie
    # 캐시 무효화
    get_settings.cache_clear()
    return {"message": "inpo21c 쿠키 업데이트 완료"}


@router.get("/inpo21c/collect-progress")
def inpo21c_collect_progress(_: User = Depends(require_role("admin"))):
    """inpo21c 수집 진행 상태 폴링 엔드포인트 (프론트엔드 2초 간격 호출)."""
    from ...collector.inpo21c import get_collect_progress
    return get_collect_progress()


@router.post("/inpo21c/collect")
def trigger_inpo21c_collect(
    background_tasks: BackgroundTasks,
    max_pages: int = 100,
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """inpo21c 전 참여자 데이터 즉시 수집 (백그라운드)."""
    def _run():
        from ...database import SessionLocal
        from ...collector.inpo21c import collect_inpo21c
        from ...collector.scheduler import _trigger_ml_retrain
        _db = SessionLocal()
        try:
            result = collect_inpo21c(_db, max_pages=max_pages)
            if result.get("bids", 0) > 0:
                _trigger_ml_retrain("inpo21c 즉시 수집 완료")
        finally:
            _db.close()

    background_tasks.add_task(_run)
    return {"message": f"inpo21c 수집 시작됨 (최대 {max_pages}페이지)"}


@router.post("/collect/scsbid")
def trigger_scsbid_collect(
    background_tasks: BackgroundTasks,
    days_back: int = 30,
    _: User = Depends(require_role("admin")),
):
    """낙찰정보서비스(scsbid) 즉시 수집 — participant_count + 낙찰율 보강 (백그라운드)."""
    def _run():
        from ...database import SessionLocal
        from ...collector.service import collect_scsbid_results
        _db = SessionLocal()
        try:
            collect_scsbid_results(_db, days_back=days_back)
        finally:
            _db.close()

    background_tasks.add_task(_run)
    return {"message": f"scsbid 수집 시작됨 (최근 {days_back}일)"}


@router.post("/rebuild/competitor-stats")
def trigger_competitor_stats_rebuild(
    background_tasks: BackgroundTasks,
    _: User = Depends(require_role("admin")),
):
    """경쟁사 통계 재계산 + GMM 클러스터 재피팅 (백그라운드 실행)."""
    def _run():
        from ...database import SessionLocal
        from ...services.competitor import rebuild_competitor_stats
        from ...ml.competitor_cluster import fit_from_db
        _db = SessionLocal()
        try:
            result = rebuild_competitor_stats(_db)
            logger.info("경쟁사 통계 재계산(즉시): %s", result)
            fit_from_db(_db)
            logger.info("GMM 재피팅(즉시) 완료")
        finally:
            _db.close()

    background_tasks.add_task(_run)
    return {"message": "경쟁사 통계 재계산 + GMM 재피팅 시작됨"}


@router.post("/collect/yega")
def trigger_yega_collect(
    background_tasks: BackgroundTasks,
    days_back: int = 3,
    _: User = Depends(require_role("admin")),
):
    """복수예가 즉시 수집 — 개찰 완료 공고의 예가상세 수집 (백그라운드)."""
    def _run():
        from ...database import SessionLocal
        from ...collector.service import collect_g2b_yega_detail
        _db = SessionLocal()
        try:
            result = collect_g2b_yega_detail(_db, days_back=days_back)
            logger.info("yega 즉시 수집: %s", result)
        finally:
            _db.close()

    background_tasks.add_task(_run)
    return {"message": f"복수예가 수집 시작됨 (최근 {days_back}일)"}


@router.post("/collect/missing-results")
def trigger_missing_results_collect(
    background_tasks: BackgroundTasks,
    lookback_days: int = 90,
    max_bids: int = 200,
    _: User = Depends(require_role("admin")),
):
    """낙찰결과 누락 보완 수집 — bid_results 없는 건을 G2B API로 채우기 (백그라운드)."""
    def _run():
        from ...database import SessionLocal
        from ...collector.service import collect_results_for_missing_bids
        from ...collector.scheduler import _trigger_ml_retrain
        _db = SessionLocal()
        try:
            result = collect_results_for_missing_bids(_db, lookback_days=lookback_days, max_bids=max_bids)
            logger.info("missing-results 즉시 수집: %s", result)
            if result.get("filled", 0) > 0:
                _trigger_ml_retrain("낙찰결과 누락 보완(즉시) 완료")
        finally:
            _db.close()

    background_tasks.add_task(_run)
    return {"message": f"낙찰결과 누락 보완 수집 시작됨 (lookback={lookback_days}일, max={max_bids}건)"}


@router.post("/sync-my-bids")
def sync_my_bids(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """개찰 완료 공고와 투찰이력 즉시 연계."""
    from ...services import G2BSyncService
    result = G2BSyncService().sync(db)
    return result


@router.post("/sync-inpo21c-to-bids")
def sync_inpo21c_to_bids_endpoint(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """inpo21c_bids → bids 즉시 동기화 (base_amount, bid_open_date, participant_count)."""
    from ...collector.service import sync_inpo21c_to_bids
    result = sync_inpo21c_to_bids(db)
    return result


@router.post("/sync-inpo21c-notices-to-bids")
def sync_inpo21c_notices_to_bids_endpoint(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """inpo21c_bid_notices → bids 동기화 (bid_close_date, estimated_price, min_bid_rate, yega_method, registration_deadline)."""
    from ...collector.service import sync_inpo21c_notices_to_bids
    result = sync_inpo21c_notices_to_bids(db)
    return result


# ------------------------------------------------------------------ #
# G2B 백필                                                            #
# ------------------------------------------------------------------ #

@router.post("/backfill/start")
def start_backfill(
    background_tasks: BackgroundTasks,
    start_year: int = 2016,
    delay: float = 1.2,
    _: User = Depends(require_role("admin")),
):
    """G2B 과거 데이터 백필 시작 (백그라운드). start_year~오늘까지 30일 청크 수집."""
    from ...collector.backfill import run_backfill, get_status
    from ...database import SessionLocal

    db = SessionLocal()
    try:
        status = get_status(db)
    finally:
        db.close()

    if status.get("status") == "running":
        raise HTTPException(status_code=409, detail="백필이 이미 실행 중입니다")

    background_tasks.add_task(run_backfill, start_year, delay)
    return {"message": f"{start_year}년부터 백필 시작됨 (딜레이={delay}s)", "start_year": start_year}


@router.get("/backfill/status")
def backfill_status(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """백필 진행 상황 조회."""
    from ...collector.backfill import get_status
    return get_status(db)


@router.post("/backfill/stop")
def stop_backfill(
    _: User = Depends(require_role("admin")),
):
    """실행 중인 백필 중단 요청 (현재 청크 완료 후 멈춤)."""
    from ...collector.backfill import request_stop
    return {"message": request_stop()}

@router.post("/backfill/inpo21c")
def start_inpo21c_backfill(
    background_tasks: BackgroundTasks,
    max_pages: int = 500,
    _: User = Depends(require_role("admin")),
):
    """inpo21c 전 참여자 과거 데이터 대량 수집 (백그라운드). max_pages 페이지까지 순회."""
    def _run():
        from ...database import SessionLocal
        from ...collector.inpo21c import collect_inpo21c
        _db = SessionLocal()
        try:
            result = collect_inpo21c(_db, max_pages=max_pages)
            logger.info("inpo21c 백필 완료: %s", result)
        finally:
            _db.close()

    background_tasks.add_task(_run)
    return {"message": f"inpo21c 백필 시작됨 (최대 {max_pages}페이지)"}

@router.post("/inpo21c/collect-national")
def trigger_inpo21c_national(
    background_tasks: BackgroundTasks,
    max_pages: int = 500,
    _: User = Depends(require_role("admin")),
):
    """inpo21c 전국 낙찰 결과 즉시 수집 (division 비의존 — 맞춤설정 외 전국 커버리지 확보)."""
    def _run():
        from ...database import SessionLocal
        from ...collector.inpo21c import collect_inpo21c_national
        _db = SessionLocal()
        try:
            result = collect_inpo21c_national(_db, max_pages=max_pages)
            logger.info("inpo21c 전국 수집 완료: %s", result)
        finally:
            _db.close()

    background_tasks.add_task(_run)
    return {"message": f"inpo21c 전국 수집 시작됨 (최대 {max_pages}페이지)"}


@router.post("/inpo21c/collect-notices")
def trigger_inpo21c_bid_notices(
    background_tasks: BackgroundTasks,
    max_pages: int = 5,
    _: User = Depends(require_role("admin")),
):
    """inpo21c 입찰공고 사전정보 수집 + bids 자동 동기화 (백그라운드).

    G2B BidPublicInfoService02 대체: info21c 공고 → bids 테이블 자동 등록.
    """
    def _run():
        from ...database import SessionLocal
        from ...collector.inpo21c import collect_bid_notices_inpo21c
        from ...services import InpoNoticesSyncService
        _db = SessionLocal()
        try:
            result = collect_bid_notices_inpo21c(_db, max_pages=max_pages)
            logger.info("inpo21c 입찰공고 수집 완료: %s", result)
            sync = InpoNoticesSyncService().sync(_db)
            logger.info("inpo21c → bids 동기화: %s", sync)
        finally:
            _db.close()

    background_tasks.add_task(_run)
    return {"message": f"inpo21c 입찰공고 수집 + bids 동기화 시작됨 (최대 {max_pages}페이지)"}


@router.post("/inpo21c/rescrape-titles")
def trigger_inpo21c_rescrape_titles(
    background_tasks: BackgroundTasks,
    max_pages: int = 100,
    _: User = Depends(require_role("admin")),
):
    """inpo21c_bids 중 title이 없는 건을 목록 페이지 순회로 보완 + bids 신규 등록 (백그라운드)."""
    def _run():
        from ...database import SessionLocal
        from ...collector.inpo21c import rescrape_inpo21c_titles
        _db = SessionLocal()
        try:
            result = rescrape_inpo21c_titles(_db, max_pages=max_pages)
            logger.info("inpo21c title 재스크래핑 완료: %s", result)
        finally:
            _db.close()

    background_tasks.add_task(_run)
    return {"message": f"inpo21c title 재스크래핑 시작됨 (최대 {max_pages}페이지, 백그라운드)"}


@router.post("/inpo21c/sync-to-bids")
def sync_inpo21c_notices_to_bids(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """inpo21c_bid_notices → bids 즉시 동기화 (G2B API 대체 수동 트리거)."""
    from ...services import InpoNoticesSyncService
    result = InpoNoticesSyncService().sync(db)
    return result


@router.post("/inpo21c/fill-incomplete")
def fill_incomplete_participants(
    background_tasks: BackgroundTasks,
    min_parts: int = 3,
    max_bids: int = 500,
    _: User = Depends(require_role("admin")),
):
    """참가자 min_parts 미만인 입찰(낙찰자만 수집)의 전참여자 강제 재수집 — win_prob_model 학습 데이터 보강."""
    def _run():
        from ...database import SessionLocal
        from ...collector.inpo21c import collect_incomplete_participants
        from ...collector.scheduler import _trigger_ml_retrain
        _db = SessionLocal()
        try:
            result = collect_incomplete_participants(_db, min_parts=min_parts, max_bids=max_bids)
            logger.info("fill-incomplete 완료: %s", result)
            if result.get("filled", 0) > 0:
                _trigger_ml_retrain("incomplete 참가자 재수집 완료")
        finally:
            _db.close()

    background_tasks.add_task(_run)
    return {"message": f"참가자 재수집 시작됨 (대상최대 {max_bids}건, 최소참가자 {min_parts}명)"}


@router.post("/inpo21c/collect-by-region")
def collect_inpo21c_by_region(
    background_tasks: BackgroundTasks,
    region_code: int = 0,
    industry_code: str = "C002",
    max_pages: int = 30,
    _: User = Depends(require_role("admin")),
):
    """
    지역/업종 필터로 전참여자+복수예가 수집 (한글 인코딩 문제 회피를 위해 코드 사용).
    region_code: 0=전국 1=서울 2=부산 3=광주 4=대전 5=인천 6=대구 7=울산
                 8=경기 9=강원 10=충북 11=충남 12=경북 13=경남
    industry_code: C002=건축 C003=토건 C001=토목 C009=실내건축 C006=전기 (빈값=전체)
    """
    _REGION_NAMES = {
        0: "전국", 1: "서울", 2: "부산", 3: "광주", 4: "대전",
        5: "인천", 6: "대구", 7: "울산", 8: "경기", 9: "강원",
        10: "충북", 11: "충남", 12: "경북", 13: "경남",
    }
    region_name = _REGION_NAMES.get(region_code, "전국")

    def _run():
        from ...database import SessionLocal
        from ...collector.inpo21c import collect_inpo21c_by_region as _collect
        from ...collector.scheduler import _trigger_ml_retrain
        _db = SessionLocal()
        try:
            result = _collect(_db, region=region_name, industry=industry_code, max_pages=max_pages)
            logger.info("지역수집 완료 [%s/%s]: %s", region_name, industry_code or "전업종", result)
            if result.get("bids", 0) > 0:
                _trigger_ml_retrain(f"inpo21c 지역수집 완료 [{region_name}]")
        finally:
            _db.close()

    background_tasks.add_task(_run)
    return {"message": f"지역수집 시작됨 — {region_name}/{industry_code or '전업종'} 최대 {max_pages}페이지"}


@router.get("/inpo21c/stats")
def inpo21c_stats(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """inpo21c 수집 데이터 통계 조회."""
    row = db.execute(text("""
        SELECT
            (SELECT COUNT(*)                           FROM inpo21c_participants)           AS participants,
            (SELECT COUNT(DISTINCT inpo21c_bid_id)     FROM inpo21c_participants)           AS suc_bids,
            (SELECT COUNT(*)                           FROM inpo21c_bids)                  AS bids_with_header,
            (SELECT COUNT(*)                           FROM inpo21c_yega)                  AS yega_entries,
            (SELECT COUNT(DISTINCT inpo21c_bid_id)     FROM inpo21c_yega)                  AS bids_with_yega,
            (SELECT COUNT(*)                           FROM inpo21c_bid_notices)            AS bid_notices,
            (SELECT COUNT(*) FROM inpo21c_bids WHERE announcement_no != '')                AS linked_to_g2b
    """)).fetchone()

    if not row:
        return {}

    return {
        "participants":     row[0] or 0,
        "suc_bids":         row[1] or 0,
        "bids_with_header": row[2] or 0,
        "yega_entries":     row[3] or 0,
        "bids_with_yega":   row[4] or 0,
        "bid_notices":      row[5] or 0,
        "linked_to_g2b":    row[6] or 0,
    }


@router.get("/ml/calibration")
def ml_calibration(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """
    모델 캘리브레이션 통계.
    bid_journal의 pred_win_prob vs 실제 낙찰 결과로 ECE(Expected Calibration Error) 계산.
    예측 확률이 실제 낙찰률과 얼마나 일치하는지 측정.
    """
    rows = db.execute(text("""
        SELECT
            FLOOR(pred_win_prob * 10) / 10.0   AS prob_bucket,
            COUNT(*)                            AS n,
            AVG(CASE WHEN result = '낙찰' THEN 1.0 ELSE 0.0 END) AS actual_win_rate,
            AVG(pred_win_prob)                  AS avg_pred_prob,
            COUNT(CASE WHEN result = '낙찰' THEN 1 END) AS wins
        FROM bid_journal
        WHERE pred_win_prob IS NOT NULL
          AND result IN ('낙찰', '패찰')
        GROUP BY prob_bucket
        ORDER BY prob_bucket
    """)).fetchall()

    if not rows:
        return {
            "ece":              None,
            "total_samples":    0,
            "calibration_bins": [],
            "message":          "캘리브레이션 데이터 없음 (저널 결과 입력 필요)",
        }

    bins = []
    total_n = sum(int(r[1]) for r in rows)
    ece = 0.0

    for r in rows:
        bucket, n, actual, avg_pred, wins = r
        n = int(n)
        actual = float(actual) if actual is not None else 0.0
        avg_pred = float(avg_pred) if avg_pred is not None else 0.0
        ece += (n / total_n) * abs(actual - avg_pred)
        bins.append({
            "prob_bucket":    round(float(bucket), 1),
            "n":              n,
            "actual_win_rate": round(actual, 4),
            "avg_pred_prob":  round(avg_pred, 4),
            "wins":           int(wins),
            "calibration_gap": round(actual - avg_pred, 4),
        })

    srate_error_row = db.execute(text("""
        SELECT
            AVG(ABS(srate_error))  AS mae,
            STDDEV(srate_error)    AS std,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY srate_error) AS median_bias
        FROM bid_journal
        WHERE srate_error IS NOT NULL
    """)).fetchone()

    return {
        "ece":              round(ece, 4),
        "total_samples":    total_n,
        "calibration_bins": bins,
        "srate_mae":        round(float(srate_error_row[0]), 4) if srate_error_row[0] else None,
        "srate_std":        round(float(srate_error_row[1]), 4) if srate_error_row[1] else None,
        "srate_median_bias": round(float(srate_error_row[2]), 4) if srate_error_row[2] else None,
        "interpretation": (
            "잘 캘리브레이션됨 (ECE < 0.05)" if ece < 0.05 else
            "보통 (ECE 0.05~0.10)" if ece < 0.10 else
            "캘리브레이션 개선 필요 (ECE > 0.10)"
        ),
    }


# ---------------------------------------------------------------------------
# C-4: 담합 의심 탐지 API
# ---------------------------------------------------------------------------
@router.get("/ml/collusion-scan")
def collusion_scan(
    days: int = 30,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """최근 N일 수집 공고에서 담합 의심 건 스캔."""
    from ...ml.anomaly_detector import scan_recent_collusion
    results = scan_recent_collusion(db, days=min(days, 180), limit=min(limit, 500))
    return {"days": days, "flagged_count": len(results), "results": results}


@router.get("/ml/collusion-scan/{announcement_no}")
def collusion_scan_one(
    announcement_no: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """특정 공고번호의 담합 의심 분석."""
    from ...ml.anomaly_detector import detect_collusion
    rows = db.execute(
        text("""
            SELECT p.bid_rate FROM inpo21c_participants p
            JOIN inpo21c_bids b ON b.inpo21c_bid_id = p.inpo21c_bid_id
            WHERE b.announcement_no = :ano AND p.bid_rate BETWEEN 0.70 AND 1.05
        """),
        {"ano": announcement_no},
    ).fetchall()
    rates = [float(r[0]) for r in rows]
    return detect_collusion(rates, announcement_no=announcement_no)


@router.get("/ml/validation-results")
def get_validation_results(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """Walk-forward 검증 결과 최근 12회 조회."""
    try:
        rows = db.execute(text("""
            SELECT id, run_at, total, wins, actual_win_rate, srate_mae,
                   calibration, strategy_win_rates
            FROM ml_validation_results
            ORDER BY run_at DESC
            LIMIT 12
        """)).fetchall()
    except Exception:
        return {"results": [], "message": "검증 데이터 없음 (아직 실행 전)"}

    return {
        "results": [
            {
                "id":               r[0],
                "run_at":           r[1].isoformat() if r[1] else None,
                "total":            r[2],
                "wins":             r[3],
                "actual_win_rate":  float(r[4]) if r[4] is not None else None,
                "srate_mae":        float(r[5]) if r[5] is not None else None,
                "calibration":      r[6],
                "strategy_win_rates": r[7],
            }
            for r in rows
        ]
    }


@router.post("/ml/run-validation")
def run_validation_now(
    background_tasks: BackgroundTasks,
    _: User = Depends(require_role("admin")),
):
    """Walk-forward 검증 즉시 실행 (백그라운드)."""
    from ...collector.scheduler import run_validation_job
    background_tasks.add_task(run_validation_job)
    return {"status": "started", "message": "Walk-forward 검증 시작됨 (백그라운드 — 수초 소요)"}


@router.post("/journal/migrate-to-executions")
def migrate_journal_to_executions(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """
    bid_journal 이력 → bid_executions 일괄 변환.
    announcement_no 기준 중복 방지. source='journal' 태깅.
    """
    from ...models import BidExecution, BidJournal

    rows = db.execute(text("""
        SELECT j.id, j.bid_id, j.user_id, j.announcement_no,
               j.submitted_rate, j.floor_rate, j.submitted_at,
               j.result, j.total_bidders, j.winner_rate, j.our_rank,
               j.opened_at, j.actual_srate,
               b.title, b.agency_id, b.base_amount, b.bid_open_date,
               a.name AS agency_name, b.industry_id
        FROM bid_journal j
        JOIN bids b ON b.id = j.bid_id
        LEFT JOIN agencies a ON a.id = b.agency_id
        WHERE j.submitted_rate IS NOT NULL
        ORDER BY j.id
    """)).fetchall()

    created = 0
    skipped = 0

    for row in rows:
        (jid, bid_id, user_id, anno_no, sub_rate, floor_rate, sub_at,
         result, total_bidders, winner_rate, our_rank, opened_at, actual_srate,
         title, agency_id, base_amount, bid_open_date, agency_name, industry_id) = row

        # 중복 확인 (같은 announcement_no, user_id)
        exists = db.execute(text("""
            SELECT id FROM bid_executions
            WHERE user_id = :uid
              AND announcement_no = :ano
              AND source = 'journal'
        """), {"uid": user_id, "ano": anno_no}).fetchone()

        if exists:
            skipped += 1
            continue

        status_map = {"낙찰": "낙찰", "패찰": "패찰", "무효": "포기", "취소": "포기"}
        ex_status = status_map.get(result, "패찰") if result else "패찰"

        # winner_rate 0.97 초과는 사정율(assessment_rate) 오인 — 낙찰율 범위 0.80~0.97만 허용
        clean_winner_rate = float(winner_rate) if winner_rate and 0.80 <= float(winner_rate) <= 0.97 else None
        winner_gap = (
            round(clean_winner_rate - float(sub_rate), 6)
            if clean_winner_rate and sub_rate else None
        )

        ex = BidExecution(
            bid_id=bid_id,
            user_id=user_id,
            announcement_no=anno_no,
            title=title or f"공고 {anno_no}",
            agency_name=agency_name,
            base_amount=int(base_amount) if base_amount else 0,
            bid_open_date=bid_open_date,
            status=ex_status,
            submitted_rate=sub_rate,
            floor_rate=floor_rate,
            submitted_at=sub_at or opened_at,
            result_rank=int(our_rank) if our_rank else None,
            total_bidders=int(total_bidders) if total_bidders else None,
            winner_rate=clean_winner_rate,
            winner_gap=winner_gap,
            opened_at=opened_at,
            source="journal",
            note=f"bid_journal #{jid} 자동 이관",
        )
        db.add(ex)
        created += 1

    db.commit()
    logger.info("journal→executions 이관: created=%d skipped=%d", created, skipped)
    return {"status": "ok", "created": created, "skipped": skipped}


@router.post("/backfill/historical")
def trigger_historical_backfill(
    background_tasks: BackgroundTasks,
    date_from: str = "2022-01-01",
    date_to: str | None = None,
    _: User = Depends(require_role("admin")),
):
    """G2B 역사 낙찰 데이터 백필 (getScsbidListSttusCnstwkPPSSrch) — 백그라운드 실행."""
    def _run():
        from ...database import SessionLocal
        from ...collector.service import backfill_historical_bids
        _db = SessionLocal()
        try:
            result = backfill_historical_bids(_db, date_from=date_from, date_to=date_to)
            logger.info("역사 백필 완료: %s", result)
        except Exception as exc:
            logger.error("역사 백필 실패: %s", exc)
        finally:
            _db.close()

    background_tasks.add_task(_run)
    return {
        "message": f"역사 데이터 백필 시작됨 ({date_from} ~ {date_to or '오늘'})",
        "note": "백그라운드 실행 중. /admin/collection-logs 에서 진행 확인",
    }


@router.post("/rebuild/agency-budget-patterns")
def rebuild_agency_budget_patterns_endpoint(
    background_tasks: BackgroundTasks,
    _: User = Depends(require_role("admin")),
):
    """발주기관 예산 집행 패턴 재계산 — 백그라운드 실행."""
    def _run():
        from ...database import SessionLocal
        from ...services.agency import rebuild_agency_budget_patterns
        _db = SessionLocal()
        try:
            result = rebuild_agency_budget_patterns(_db)
            logger.info("agency_budget_patterns 즉시 재계산: %s", result)
        except Exception as exc:
            logger.error("agency_budget_patterns 즉시 재계산 실패: %s", exc)
        finally:
            _db.close()

    background_tasks.add_task(_run)
    return {"message": "발주기관 예산 집행 패턴 재계산 시작됨"}
