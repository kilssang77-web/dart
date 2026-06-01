from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from ...database import get_db
from ...models import User
from ...services import StatisticsService
from ...schemas import SrateDistributionResponse
from ...common.security import get_current_user

router = APIRouter(prefix="/stats", tags=["통계"])
svc = StatisticsService()


@router.get("/overview")
def overview(
    months: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.overview(db, months)


@router.get("/agencies")
def agency_stats(
    months: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.agency_stats(db, months)


@router.get("/regions")
def region_stats(
    months: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.region_stats(db, months)


@router.get("/industries")
def industry_stats(
    months: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.industry_stats(db, months)


@router.get("/rate-distribution")
def rate_distribution(
    industry_id: Optional[int] = Query(None),
    months: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.rate_distribution(db, industry_id, months)


@router.get("/heatmap")
def heatmap(
    months: int = Query(24, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.heatmap(db, months)


@router.get("/cluster")
def cluster_analysis(
    industry_id: Optional[int] = Query(None),
    months: int = Query(24, ge=3, le=60),
    k: int = Query(4, ge=2, le=8),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.cluster_analysis(db, industry_id=industry_id, months=months, k=k)


@router.get("/srate-distribution")
def srate_distribution(
    agency_id:   Optional[int] = Query(None),
    industry_id: Optional[int] = Query(None),
    months: int = Query(24, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.srate_distribution_detail(db, agency_id=agency_id, industry_id=industry_id, months=months)


@router.get("/model-info")
def model_info(
    months: int = Query(12, ge=1, le=60),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.model_info(db, months)