"""관리자 전용 API — 사용자 관리 + 공종 필터 + 시스템 상태 모니터링."""
import os
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from ...database import get_db
from ...models import User, Industry, IndustryFilter
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
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    """ML 모델 재학습 — assessment_rate_stats 집계 + Engine A+B 학습."""
    import traceback
    from ...ml.assessment import compute_and_store_stats, train_srate_model
    from ...ml.engine import train_models, build_features, FEATURE_COLS, get_engine
    import pandas as pd
    import math
    from datetime import datetime, timedelta

    results = {}

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
            WHERE b.bid_open_date >= :cutoff AND b.status = 'closed'
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

    return {"status": "ok", "results": results}


@router.get("/system-status")
def system_status(db: Session = Depends(get_db), _: User = Depends(require_role("admin"))):
    counts = db.execute(text("""
        SELECT
            (SELECT COUNT(*) FROM bids)                                          AS total_bids,
            (SELECT COUNT(*) FROM bids WHERE source = 'g2b')                    AS g2b_bids,
            (SELECT COUNT(*) FROM bids WHERE created_at >= NOW() - INTERVAL '7 days') AS new_7d,
            (SELECT COUNT(*) FROM bid_results)                                   AS total_results,
            (SELECT COUNT(*) FROM competitors)                                   AS total_competitors,
            (SELECT COUNT(*) FROM users)                                         AS total_users,
            (SELECT COUNT(*) FROM watch_keywords WHERE is_active = true)         AS active_keywords
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