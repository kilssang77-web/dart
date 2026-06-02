from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from ...database import get_db
from ...models import User
from ...services import CompetitorService, CompetitorPatternService
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