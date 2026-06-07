"""KPI 대시보드 API — E8 경영진 의사결정 엔진"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...database import get_db
from ...schemas import KPIDashboardResponse
from ...services import KpiService
from .auth import get_current_user

router = APIRouter(prefix="/kpi", tags=["KPI 대시보드"])
_svc = KpiService()


@router.get("/dashboard", response_model=KPIDashboardResponse)
def get_dashboard(
    period_type: str = Query("MONTHLY", regex="^(DAILY|WEEKLY|MONTHLY)$"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    수주율 KPI 대시보드.

    수주건수 / 수주율 / 월 목표 달성률 / 적격통과율 /
    사정율 예측 MAE / 낙찰확률 캘리브레이션 오차 / 경고 메시지 반환.
    """
    return _svc.get_dashboard(db, user.id, period_type)


@router.post("/snapshot")
def force_snapshot(
    period_type: str = Query("MONTHLY"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """KPI 스냅샷 강제 재계산 + 저장"""
    from datetime import date
    from ...ml.feedback import build_kpi_snapshot
    kpi = build_kpi_snapshot(db, user.id, date.today(), period_type)
    if kpi:
        kpi["user_id"]     = user.id
        kpi["period_type"] = period_type
        _svc.upsert_snapshot(db, kpi)
    return {"ok": True, "kpi": kpi}
