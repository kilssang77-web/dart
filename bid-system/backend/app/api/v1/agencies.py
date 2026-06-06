from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from ...database import get_db
from ...models import User
from ...services import AgencyAnalysisService
from ...common.security import get_current_user

router = APIRouter(prefix="/agencies", tags=["발주기관"])


@router.get("")
def list_agencies(
    q:    Optional[str] = Query(None),
    page: int           = Query(1, ge=1),
    size: int           = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User     = Depends(get_current_user),
):
    return AgencyAnalysisService(db).list_agencies(q=q, page=page, size=size)


@router.get("/{agency_id}/analysis")
def agency_analysis(
    agency_id: int,
    db: Session = Depends(get_db),
    _: User     = Depends(get_current_user),
):
    return AgencyAnalysisService(db).analyze(agency_id)


@router.get("/{agency_id}/srate-histogram")
def agency_srate_histogram(
    agency_id: int,
    months: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User     = Depends(get_current_user),
):
    return AgencyAnalysisService(db).srate_histogram(agency_id, months)


@router.get("/{agency_id}/recent-results")
def agency_recent_results(
    agency_id: int,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User    = Depends(get_current_user),
):
    return AgencyAnalysisService(db).recent_results(agency_id, limit)


@router.get("/{agency_id}/yega-pattern")
def agency_yega_pattern(
    agency_id: int,
    db: Session = Depends(get_db),
    _: User     = Depends(get_current_user),
):
    """inpo21c 실측 예가 위치 패턴 (위치별 추첨 가중치 + spread)."""
    from ...ml.yega import load_inpo21c_yega_stats
    from sqlalchemy import text as _text

    stats = load_inpo21c_yega_stats(db, agency_id)
    row   = db.execute(_text("SELECT name FROM agencies WHERE id = :id"), {"id": agency_id}).fetchone()
    name  = row[0] if row else ""

    return {
        "agency_id":   agency_id,
        "agency_name": name,
        "sample_n":    stats.get("sample_n", 0),
        "spread_half": stats.get("spread_half", 0.028),
        "pos_weights": stats.get("pos_weights"),
        "has_data":    stats.get("pos_weights") is not None,
    }