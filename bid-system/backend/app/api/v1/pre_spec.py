"""사전규격 공고 API — Phase 2 (HrcspSsstndrdInfoService 수집 데이터)"""
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text

from ...database import get_db
from ...models import User
from ...common.security import get_current_user

router = APIRouter(prefix="/pre-spec", tags=["사전규격"])


@router.get("/list")
def list_pre_spec(
    order_agency: Optional[str] = Query(None, description="발주기관명 필터"),
    industry: Optional[str] = Query(None, description="업종명 필터"),
    days_back: int = Query(30, description="최근 N일 이내"),
    matched_only: bool = Query(False, description="공고 매핑된 건만"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """사전규격 목록 조회 — 필터·페이지네이션 지원."""
    conditions = ["ps.reg_date >= NOW() - (:days * INTERVAL '1 day')"]
    params: dict = {"days": days_back, "offset": (page - 1) * size, "limit": size}

    if order_agency:
        conditions.append("ps.order_agency ILIKE :agency")
        params["agency"] = f"%{order_agency}%"
    if industry:
        conditions.append("ps.industry_name ILIKE :industry")
        params["industry"] = f"%{industry}%"
    if matched_only:
        conditions.append("ps.bid_id IS NOT NULL")

    where = " AND ".join(conditions)
    rows = db.execute(text(f"""
        SELECT
            ps.id, ps.pre_spec_no, ps.title, ps.order_agency, ps.demand_agency,
            ps.estimated_amount, ps.industry_name,
            ps.reg_date, ps.end_date,
            ps.bid_announcement_no, ps.bid_id, ps.matched_at,
            b.title AS bid_title, b.bid_open_date
        FROM pre_spec_notices ps
        LEFT JOIN bids b ON b.id = ps.bid_id
        WHERE {where}
        ORDER BY ps.reg_date DESC
        LIMIT :limit OFFSET :offset
    """), params).fetchall()

    total = db.execute(text(f"""
        SELECT COUNT(*) FROM pre_spec_notices ps WHERE {where}
    """), params).scalar() or 0

    items = []
    for r in rows:
        items.append({
            "id": r[0],
            "pre_spec_no": r[1],
            "title": r[2],
            "order_agency": r[3],
            "demand_agency": r[4],
            "estimated_amount": r[5],
            "industry_name": r[6],
            "reg_date": r[7].isoformat() if r[7] else None,
            "end_date": r[8].isoformat() if r[8] else None,
            "bid_announcement_no": r[9],
            "bid_id": r[10],
            "matched_at": r[11].isoformat() if r[11] else None,
            "bid_title": r[12],
            "bid_open_date": r[13].isoformat() if r[13] else None,
            "is_matched": r[10] is not None,
        })

    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/summary")
def pre_spec_summary(
    days_back: int = Query(30),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """사전규격 요약 통계."""
    row = db.execute(text("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE bid_id IS NOT NULL) AS matched,
            COUNT(DISTINCT order_agency) AS agencies,
            SUM(estimated_amount) FILTER (WHERE estimated_amount > 0) AS total_amount
        FROM pre_spec_notices
        WHERE reg_date >= NOW() - (:days * INTERVAL '1 day')
    """), {"days": days_back}).fetchone()

    return {
        "total": row[0] if row else 0,
        "matched": row[1] if row else 0,
        "agencies": row[2] if row else 0,
        "total_amount": row[3] if row else 0,
        "days_back": days_back,
    }


@router.post("/collect", status_code=202)
def trigger_collect(
    background_tasks: BackgroundTasks,
    days_back: int = Query(7, description="수집 일수"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """사전규격 수동 수집 트리거 (admin 전용)."""
    if current_user.role != "admin":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="관리자 전용")

    def _collect():
        from app.database import SessionLocal
        from app.collector.service import collect_pre_spec_notices
        _db = SessionLocal()
        try:
            collect_pre_spec_notices(_db, days_back=days_back)
        finally:
            _db.close()

    background_tasks.add_task(_collect)
    return {"message": f"사전규격 수집 시작 (최근 {days_back}일)"}
