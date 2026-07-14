"""계약정보 API — Phase 3 (CntrctInfoService 수집 데이터)"""
from typing import Optional
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text

from ...database import get_db
from ...models import User
from ...common.security import get_current_user

router = APIRouter(prefix="/contracts", tags=["계약정보"])


@router.get("/list")
def list_contracts(
    agency_name: Optional[str] = Query(None, description="계약기관명 필터"),
    days_back: int = Query(90, description="최근 N일 이내"),
    joint_only: bool = Query(False, description="공동계약만"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """계약정보 목록 조회."""
    conditions = ["bc.contract_date >= NOW() - (:days * INTERVAL '1 day')"]
    params: dict = {"days": days_back, "offset": (page - 1) * size, "limit": size}

    if agency_name:
        conditions.append("bc.agency_name ILIKE :agency")
        params["agency"] = f"%{agency_name}%"
    if joint_only:
        conditions.append("bc.joint_contract = 'Y'")

    where = " AND ".join(conditions)
    rows = db.execute(text(f"""
        SELECT
            bc.id, bc.unty_cntrct_no, bc.dcsn_cntrct_no, bc.announcement_no,
            bc.contract_name, bc.agency_name,
            bc.total_amount, bc.this_amount,
            bc.contract_date, bc.start_date, bc.completion_date, bc.final_completion_date,
            bc.joint_contract, bc.contract_method, bc.bid_id,
            bc.company_list
        FROM bid_contracts bc
        WHERE {where}
        ORDER BY bc.contract_date DESC
        LIMIT :limit OFFSET :offset
    """), params).fetchall()

    total = db.execute(text(f"""
        SELECT COUNT(*) FROM bid_contracts bc WHERE {where}
    """), params).scalar() or 0

    items = []
    for r in rows:
        items.append({
            "id": r[0],
            "unty_cntrct_no": r[1],
            "dcsn_cntrct_no": r[2],
            "announcement_no": r[3],
            "contract_name": r[4],
            "agency_name": r[5],
            "total_amount": r[6],
            "this_amount": r[7],
            "contract_date": str(r[8]) if r[8] else None,
            "start_date": str(r[9]) if r[9] else None,
            "completion_date": str(r[10]) if r[10] else None,
            "final_completion_date": str(r[11]) if r[11] else None,
            "joint_contract": r[12],
            "contract_method": r[13],
            "bid_id": r[14],
            "company_list": r[15] or [],
        })

    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/summary")
def contracts_summary(
    days_back: int = Query(90),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """계약정보 요약 통계."""
    row = db.execute(text("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE bid_id IS NOT NULL) AS matched_bids,
            COUNT(*) FILTER (WHERE joint_contract = 'Y') AS joint_count,
            SUM(total_amount) AS total_amount,
            AVG(
                CASE WHEN completion_date IS NOT NULL AND start_date IS NOT NULL
                THEN (completion_date - start_date) END
            ) AS avg_duration_days
        FROM bid_contracts
        WHERE contract_date >= NOW() - (:days * INTERVAL '1 day')
    """), {"days": days_back}).fetchone()

    return {
        "total": row[0] if row else 0,
        "matched_bids": row[1] if row else 0,
        "joint_count": row[2] if row else 0,
        "total_amount": row[3] if row else 0,
        "avg_duration_days": float(row[4]) if row and row[4] else None,
        "days_back": days_back,
    }


@router.post("/collect", status_code=202)
def trigger_collect(
    background_tasks: BackgroundTasks,
    days_back: int = Query(7),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """계약정보 수동 수집 트리거 (admin 전용)."""
    if current_user.role != "admin":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="관리자 전용")

    def _collect():
        from app.database import SessionLocal
        from app.collector.service import collect_bid_contracts
        _db = SessionLocal()
        try:
            collect_bid_contracts(_db, days_back=days_back)
        finally:
            _db.close()

    background_tasks.add_task(_collect)
    return {"message": f"계약정보 수집 시작 (최근 {days_back}일)"}
