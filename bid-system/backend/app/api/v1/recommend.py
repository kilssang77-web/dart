from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import User
from ...schemas import RecommendRequest, RecommendV2Request
from ...services import RecommendationService, HybridRecommendService
from ...common.security import get_current_user

router = APIRouter(prefix="/recommend", tags=["AI 추천"])
svc    = RecommendationService()
svc_v2 = HybridRecommendService()


@router.post("")
def recommend(
    body: RecommendRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """기존 v1 추천 (역사 패턴 기반 XGBoost)."""
    return svc.recommend(db, body, user_id=user.id)


@router.post("/v2")
def recommend_v2(
    body: RecommendV2Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    하이브리드 추천 v2:
    Engine A(사정율) + Engine B(역사패턴) + Engine C(경쟁강도) + Engine D(변동성) 앙상블.
    전략별(공격적/균형/안정적) 투찰률 + 예정가격 추정 + 경쟁사 분석 제공.
    """
    return svc_v2.recommend_v2(db, body, user_id=user.id)


@router.post("/v2/retrain-assessment")
def retrain_assessment(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """사정율 통계 재집계 + Engine A 모델 재학습 (관리자 전용)."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="관리자만 재학습할 수 있습니다.")
    from ...ml.assessment import compute_and_store_stats, train_srate_model
    cnt = compute_and_store_stats(db)
    trained = train_srate_model(db)
    return {
        "message":    "사정율 집계 완료",
        "data_count": cnt,
        "model_trained": trained,
    }


@router.post("/retrain")
def retrain(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Engine B 재학습 (기존 유지)."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="관리자만 재학습할 수 있습니다.")
    from ...seed import _train_initial_model
    from ...ml.engine import get_engine
    _train_initial_model(db)
    get_engine().reload()
    return {"message": "모델 재학습 완료"}


@router.get("/history")
def recommendation_history(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from ...models import PredictionLog
    from sqlalchemy import desc
    logs = db.query(PredictionLog).filter(
        PredictionLog.user_id == user.id
    ).order_by(desc(PredictionLog.created_at)).limit(20).all()
    return [
        {
            "id": l.id,
            "rate_center":   float(l.rate_center)   if l.rate_center   else None,
            "win_prob":      float(l.win_prob_center) if l.win_prob_center else None,
            "risk_level":    l.risk_level,
            "model_version": l.model_version,
            "created_at":    l.created_at,
        }
        for l in logs
    ]


@router.get("/v2/srate-stats")
def srate_stats(
    agency_id:   int = None,
    industry_id: int = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """기관/공종별 사정율 통계 조회."""
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT group_type, group_id, sample_count,
               srate_mean, srate_std, srate_p25, srate_p50, srate_p75,
               srate_trend, updated_at
        FROM assessment_rate_stats
        WHERE (group_type='agency'   AND group_id=:aid)
           OR (group_type='industry' AND group_id=:iid)
           OR  group_type='global'
        ORDER BY group_type
    """), {"aid": agency_id, "iid": industry_id}).fetchall()
    return [
        {
            "group_type":   r[0],  "group_id":    r[1],
            "sample_count": r[2],  "srate_mean":  float(r[3]) if r[3] else None,
            "srate_std":    float(r[4]) if r[4] else None,
            "srate_p25":    float(r[5]) if r[5] else None,
            "srate_p50":    float(r[6]) if r[6] else None,
            "srate_p75":    float(r[7]) if r[7] else None,
            "srate_trend":  float(r[8]) if r[8] else None,
            "updated_at":   r[9],
        }
        for r in rows
    ]