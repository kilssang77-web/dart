"""단일 최적 전략 추천 API — E5 엔진"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...database import get_db
from ...schemas import SingleRecommendRequest, SingleRecommendResponse
from ...services import SingleRecommendService
from .auth import get_current_user

router = APIRouter(prefix="/strategy", tags=["전략 추천"])
_svc = SingleRecommendService()


@router.post("/recommend", response_model=SingleRecommendResponse)
def single_recommend(
    body: SingleRecommendRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    단일 최적 투찰률 추천.

    기존 4전략 대신 "이렇게 투찰하십시오" 1개를 반환합니다.
    적격심사 통과 + 낙찰 유효 + 경쟁사 최소 투찰률 분포를 통합해
    기대 수주건수를 최대화하는 최적 투찰률을 제시합니다.
    """
    return _svc.recommend(db, user.id, body.model_dump())
