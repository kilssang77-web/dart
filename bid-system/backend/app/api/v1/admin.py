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

router = APIRouter(prefix="/admin", tags=["관리자"])


class UserUpdateBody(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_role("admin"))):
    users = db.query(User).order_by(User.id).all()
    return [
        {
            "id": u.id, "email": u.email, "name": u.name,
            "role": u.role, "department": u.department,
            "is_active": u.is_active,
            "last_login": u.last_login,
            "created_at": u.created_at,
        }
        for u in users
    ]


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
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="이미 사용 중인 이메일입니다.")
    if body.role not in ("admin", "analyst", "viewer"):
        raise HTTPException(status_code=400, detail="유효하지 않은 역할입니다.")
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        name=body.name,
        role=body.role,
        department=body.department,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}


@router.put("/users/{uid}")
def update_user(
    uid: int,
    body: UserUpdateBody,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    if uid == admin.id and body.is_active is False:
        raise HTTPException(status_code=400, detail="자신의 계정을 비활성화할 수 없습니다.")
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    if body.name is not None:       user.name       = body.name
    if body.role is not None:       user.role       = body.role
    if body.department is not None: user.department = body.department
    if body.is_active is not None:  user.is_active  = body.is_active
    if body.password:               user.hashed_password = hash_password(body.password)
    db.commit()
    return {
        "id": user.id, "email": user.email, "name": user.name,
        "role": user.role, "is_active": user.is_active,
    }


@router.delete("/users/{uid}", status_code=204)
def delete_user(
    uid: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    if uid == admin.id:
        raise HTTPException(status_code=400, detail="자신의 계정은 삭제할 수 없습니다.")
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    db.delete(user)
    db.commit()


# ── 공종 관리 ──────────────────────────────────────────────────────────

@router.get("/industries")
def get_industry_filters(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """모든 공종 목록과 활성화 여부 반환."""
    all_industries = db.query(Industry).order_by(Industry.name).all()
    filter_map = {
        f.industry_id: f.is_active
        for f in db.query(IndustryFilter).all()
    }
    no_config = len(filter_map) == 0  # 설정 없음 = 전체 활성
    return [
        {
            "industry_id": ind.id,
            "name": ind.name,
            "code": ind.code,
            "is_active": filter_map.get(ind.id, True) if not no_config else True,
            "is_configured": ind.id in filter_map,
        }
        for ind in all_industries
    ]


class IndustryFilterBody(BaseModel):
    active_ids: List[int]  # 활성화할 공종 ID 목록


@router.put("/industries/filters")
def update_industry_filters(
    body: IndustryFilterBody,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """활성 공종 목록 저장. active_ids 에 없는 공종은 비활성 처리."""
    all_industries = db.query(Industry).all()
    active_set = set(body.active_ids)

    # 전체 공종이 선택된 경우 = 필터 없음 (테이블 전체 삭제)
    if len(active_set) == len(all_industries):
        db.query(IndustryFilter).delete()
        db.commit()
        return {"status": "cleared", "active_count": len(all_industries), "message": "전체 공종 활성 (필터 없음)"}

    # 공종별 upsert
    existing = {f.industry_id: f for f in db.query(IndustryFilter).all()}
    for ind in all_industries:
        is_active = ind.id in active_set
        if ind.id in existing:
            existing[ind.id].is_active = is_active
        else:
            db.add(IndustryFilter(industry_id=ind.id, is_active=is_active))

    db.commit()
    return {
        "status": "saved",
        "active_count": len(active_set),
        "total_count": len(all_industries),
    }


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
                rows = db.execute(text("""
                    SELECT b.id, b.agency_id, b.industry_id,
                           COALESCE(b.region_id, 0) AS region_id,
                           b.base_amount, b.bid_open_date,
                           COALESCE(b.region_restriction, false),
                           b.construction_period, r.bid_rate
                    FROM bids b
                    JOIN bid_results r ON r.bid_id = b.id AND r.is_winner = true
                    WHERE b.industry_id = ANY(ARRAY[20,24,31])
                      AND b.base_amount > 0
                      AND r.bid_rate BETWEEN 0.80 AND 1.00
                    ORDER BY b.bid_open_date
                """)).fetchall()

                cutoff = datetime.now() - timedelta(days=24*30)
                hist_rows = db.execute(text("""
                    SELECT b.id, b.agency_id, b.industry_id,
                           COALESCE(b.region_id, 0), b.base_amount, b.bid_open_date,
                           r.bid_rate,
                           (SELECT COUNT(*) FROM bid_results r2 WHERE r2.bid_id = b.id)
                    FROM bids b
                    LEFT JOIN bid_results r ON r.bid_id = b.id AND r.is_winner = true
                    WHERE b.bid_open_date >= :cutoff AND b.base_amount > 0
                """), {"cutoff": cutoff}).fetchall()

                hist_df = pd.DataFrame(hist_rows, columns=[
                    "id","agency_id","industry_id","region_id",
                    "base_amount","bid_open_date","winner_rate","competitor_count"
                ])
                for col in ["winner_rate","base_amount","competitor_count"]:
                    hist_df[col] = pd.to_numeric(hist_df[col], errors="coerce")

                records = []
                for row in rows:
                    bid_id, agency_id, industry_id, region_id, base_amount, bid_open_date, region_restriction, construction_period, winner_rate = row
                    if winner_rate is None:
                        continue
                    hist_before = hist_df[hist_df["bid_open_date"] < bid_open_date].copy() if bid_open_date else hist_df.copy()
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

                if len(records) >= 20:
                    train_df = pd.DataFrame(records)
                    for col in FEATURE_COLS:
                        if col not in train_df.columns:
                            train_df[col] = None
                    res = train_models(train_df)
                    if res:
                        get_engine().reload()
                        results["engine_b"] = res
                    else:
                        results["engine_b"] = "failed"
                else:
                    results["engine_b"] = f"skipped_insufficient_data ({len(records)}건)"
            except Exception as e:
                results["engine_b_error"] = traceback.format_exc()

            logger.info("ML 재학습 완료: %s", results)
        finally:
            db.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"status": "started", "message": "ML 재학습 시작됨 (별도 스레드) — 완료까지 1~3분 소요"}


@router.get("/collector-status")
def get_collector_status(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """오늘 수집량·마지막/다음 수집 시각 실시간 조회."""
    from datetime import datetime, timedelta, timezone

    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    today_start_utc = now_kst.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

    row = db.execute(text("""
        SELECT
            COALESCE(SUM(CASE WHEN collect_type LIKE 'notice%' THEN success_count ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN collect_type LIKE 'result%' THEN success_count ELSE 0 END), 0)
        FROM collection_logs
        WHERE collected_at >= :today_start
    """), {"today_start": today_start_utc}).fetchone()

    last_run = db.execute(text("SELECT MAX(collected_at) FROM collection_logs")).scalar()

    # 다음 수집 예정: 06:00 또는 18:00 KST
    next_runs = []
    for hour in (6, 18):
        candidate = now_kst.replace(hour=hour, minute=0, second=0, microsecond=0)
        if candidate <= now_kst:
            candidate += timedelta(days=1)
        next_runs.append(candidate)
    next_run_at = min(next_runs)

    return {
        "today_notices": int(row[0]),
        "today_results": int(row[1]),
        "last_run_at": last_run,
        "next_run_at": next_run_at.isoformat(),
    }


@router.get("/system-status")
def system_status(db: Session = Depends(get_db), _: User = Depends(require_role("admin"))):
    counts = db.execute(text("""
        SELECT
            (SELECT COUNT(*) FROM bids)                                              AS total_bids,
            (SELECT COUNT(*) FROM bids WHERE source = 'g2b')                        AS g2b_bids,
            (SELECT COUNT(*) FROM bids WHERE created_at >= NOW() - INTERVAL '7 days') AS new_7d,
            (SELECT COUNT(*) FROM bid_results)                                       AS total_results,
            (SELECT COUNT(*) FROM competitors)                                       AS total_competitors,
            (SELECT COUNT(*) FROM users)                                             AS total_users,
            (SELECT COUNT(*) FROM watch_keywords WHERE is_active = true)             AS active_keywords,
            (SELECT COUNT(*) FROM feature_store)                                     AS feature_store_count
    """)).fetchone()

    last_g2b = db.execute(text(
        "SELECT MAX(created_at) FROM bids WHERE source = 'g2b'"
    )).scalar()

    daily = db.execute(text("""
        SELECT DATE(created_at) AS day, COUNT(*) AS cnt
        FROM bids
        WHERE created_at >= NOW() - INTERVAL '14 days'
        GROUP BY day
        ORDER BY day DESC
        LIMIT 14
    """)).fetchall()

    pred_count = db.execute(text(
        "SELECT COUNT(*) FROM prediction_logs WHERE created_at >= NOW() - INTERVAL '7 days'"
    )).scalar()

    return {
        "db_stats": {
            "total_bids":         counts[0] or 0,
            "g2b_bids":           counts[1] or 0,
            "new_bids_7d":        counts[2] or 0,
            "total_results":      counts[3] or 0,
            "total_competitors":  counts[4] or 0,
            "total_users":        counts[5] or 0,
            "active_keywords":    counts[6] or 0,
            "feature_store":      counts[7] or 0,
        },
        "collector": {
            "enabled": os.getenv("COLLECT_ENABLED", "false").lower() == "true",
            "last_g2b_collect": last_g2b,
        },
        "ml_stats": {
            "predictions_7d": pred_count or 0,
        },
        "daily_collection": [
            {"date": str(r[0]), "count": r[1]} for r in daily
        ],
    }


@router.get("/ml/status")
def ml_status_stub():
    """레거시 호환 stub — 인증 없이 200 반환해 구 클라이언트 캐시 폴링이 401 루프를 유발하지 않도록."""
    return {"status": "ok", "message": "Use /admin/system-status"}


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
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=days)
    return (
        db.query(CollectionLog)
        .filter(CollectionLog.collected_at >= cutoff)
        .order_by(CollectionLog.collected_at.desc())
        .limit(200)
        .all()
    )


@router.get("/collection-logs/{log_id}", response_model=CollectionLogOut)
def collection_log_detail(
    log_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    log = db.query(CollectionLog).filter(CollectionLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="수집 로그를 찾을 수 없습니다.")
    return log


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
    max_pages: int = 4,
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


@router.post("/sync-my-bids")
def sync_my_bids(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """개찰 완료 공고와 투찰이력 즉시 연계."""
    from ...services import G2BSyncService
    result = G2BSyncService().sync(db)
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


@router.post("/inpo21c/sync-to-bids")
def sync_inpo21c_notices_to_bids(
    _: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """inpo21c_bid_notices → bids 즉시 동기화 (G2B API 대체 수동 트리거)."""
    from ...services import InpoNoticesSyncService
    result = InpoNoticesSyncService().sync(db)
    return result


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