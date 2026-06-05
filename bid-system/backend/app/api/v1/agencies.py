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
