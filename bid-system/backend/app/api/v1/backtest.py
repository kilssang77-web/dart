"""
백테스트 엔진 API
- 과거 투찰 이력 vs 시스템 추천 결과 비교
- 수주율 개선 시뮬레이션
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...database import get_db
from ...common.security import get_current_user
from ...models import User

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("", response_model=dict)
def run_backtest(
    months: int = Query(60, ge=6, le=120),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    과거 투찰 실행 결과(bid_executions) 기반 백테스트.
    추천율 vs 실제 투찰율 vs 낙찰율 3-way 비교.
    """
    from ...services import BacktestService
    svc = BacktestService(db)
    return svc.run(user_id=current_user.id, months=months)
