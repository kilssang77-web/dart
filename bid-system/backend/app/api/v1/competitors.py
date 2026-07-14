from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from ...database import get_db
from ...models import User
from ...services import CompetitorService, CompetitorPatternService, CompetitorZoneService, CompetitorPredictService
from ...common.security import get_current_user

router = APIRouter(prefix="/competitors", tags=["경쟁사"])
svc = CompetitorService()


@router.get("")
def list_competitors(
    keyword: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.list_competitors(db, keyword=keyword, page=page, size=size, risk_level=risk_level)


@router.get("/compare")
def compare_competitors(
    ids: str = Query(..., description="쉼표 구분 경쟁사 ID (최대 2개)"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    id_list = [int(i.strip()) for i in ids.split(",") if i.strip()][:2]
    return CompetitorPatternService(db).compare(id_list)


@router.get("/{competitor_id}")
def get_competitor(
    competitor_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = svc.get_detail(db, competitor_id)
    if not result:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="경쟁사를 찾을 수 없습니다.")
    return result


@router.get("/{competitor_id}/timeline")
def competitor_timeline(
    competitor_id: int,
    months: int = Query(12, ge=3, le=36),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc._monthly_trend(db, competitor_id, months)


@router.get("/{competitor_id}/wins")
def competitor_wins(
    competitor_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return svc.get_win_history(db, competitor_id, limit)


@router.get("/{competitor_id}/pattern")
def competitor_pattern(
    competitor_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return CompetitorPatternService(db).get_pattern(competitor_id)


@router.get("/{competitor_id}/zones")
def competitor_zones(
    competitor_id: int,
    days: int = Query(90, ge=30, le=365),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return CompetitorZoneService().get_recent_zones(db, competitor_id, days)


@router.get("/{competitor_id}/predict")
def competitor_predict(
    competitor_id: int,
    bid_id: int = Query(..., description="분석 대상 공고 ID"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """경쟁사의 특정 공고 참여 확률 및 투찰 구간 분포 예측."""
    return CompetitorPredictService().predict(db, competitor_id, bid_id)


@router.get("/{competitor_id}/kiscon-profile")
def competitor_kiscon_profile(
    competitor_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """경쟁사 KISCON 프로필 조회.

    - license_types / license_names: 보유 면허 업종 목록
    - capacity_eval_amount: 시공능력평가액 합계 (KISCON API 수집 시)
    - top_agencies: 주력 발주기관 top5
    - risk_agencies: 강점 기관 (낙찰률 30%+, 회피 전략 대상)
    - bid_count_2y / win_count_2y / win_rate_2y: 최근 2년 실적
    """
    from app.collector.kiscon_service import get_kiscon_profile
    from fastapi import HTTPException

    profile = get_kiscon_profile(db, competitor_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="KISCON 프로필이 없습니다. 수집 후 다시 조회하세요.")
    return profile


@router.post("/{competitor_id}/kiscon-refresh")
def competitor_kiscon_refresh(
    competitor_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """경쟁사 실적 프로필 즉시 재집계."""
    from app.collector.kiscon_service import collect_kiscon_profiles
    from app.models import Competitor
    from fastapi import HTTPException

    comp = db.query(Competitor).filter(Competitor.id == competitor_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="경쟁사를 찾을 수 없습니다.")
    if not comp.biz_reg_no:
        raise HTTPException(status_code=400, detail="사업자등록번호가 없는 경쟁사입니다.")

    result = collect_kiscon_profiles(db, limit=1, force_refresh=True)
    return {"ok": True, **result}