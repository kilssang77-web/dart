from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from ...database import get_db
from ...models import User
from ...schemas import RecommendRequest, RecommendV2Request, BidRangeResponse, PrismResponse, AgencyYegaPattern
from ...services import RecommendationService, HybridRecommendService, AgencyYegaService
from ...common.security import get_current_user
from ...ml.assessment import load_srate_stats, predict_srate
from ...ml.a_value import calc_bid_range

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


@router.get("/bid-range", response_model=BidRangeResponse)
def bid_range(
    base_amount:  int           = Query(..., gt=0, description="기초금액 (원)"),
    industry_id:  Optional[int] = Query(None, description="공종 ID"),
    agency_id:    Optional[int] = Query(None, description="발주처 ID"),
    region_id:    Optional[int] = Query(None, description="지역 ID"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """A값·낙찰하한가 자동 계산 (기초금액 + 사정율 예측 기반)."""
    features_a = load_srate_stats(
        db,
        agency_id   or 0,
        industry_id or 0,
        region_id   or 0,
        base_amount,
    )
    ep = predict_srate(features_a, base_amount)
    srate_c   = ep["srate_range"]["center"]
    srate_std = (
        features_a.get("agency_srate_std")
        or features_a.get("global_srate_std")
        or 0.012
    )

    industry_name = ""
    if industry_id:
        row = db.execute(
            text("SELECT name FROM industries WHERE id = :id"),
            {"id": industry_id},
        ).fetchone()
        if row:
            industry_name = row[0]

    result = calc_bid_range(
        base_amount   = base_amount,
        srate_center  = srate_c,
        srate_std     = srate_std,
        industry_name = industry_name,
        srate_p10     = ep["srate_range"]["p10"],
        srate_p25     = ep["srate_range"]["lower"],
        srate_p75     = ep["srate_range"]["upper"],
        srate_p90     = ep["srate_range"]["p90"],
    )
    result["industry_name"] = industry_name
    return result


@router.post("/prism", response_model=PrismResponse)
def prism(
    body: RecommendV2Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    프리즘 2.0 — 0.860~0.930 구간을 0.001 단위로 스캔(70구간).
    inpo21c 실증 분포 기반 Monte Carlo 낙찰확률 계산, 상위 10개 구간 반환.
    """
    from ...ml.prism import scan_prism_zones, SCAN_START, SCAN_END, SCAN_STEP, TOP_N

    industry_name = ""
    if body.industry_id:
        row = db.execute(
            text("SELECT name FROM industries WHERE id = :id"),
            {"id": body.industry_id},
        ).fetchone()
        if row:
            industry_name = row[0]

    all_zones, top10 = scan_prism_zones(
        base_amount   = body.base_amount,
        industry_name = industry_name,
        agency_id     = body.agency_id,
        industry_id   = body.industry_id,
        db            = db,
    )

    return {
        "zones": all_zones,
        "top10": top10,
        "scan_meta": {
            "scan_start":      SCAN_START,
            "scan_end":        SCAN_END,
            "scan_step":       SCAN_STEP,
            "total_zones":     len(all_zones),
            "floor_ok_count":  sum(1 for z in all_zones if z["floor_ok"]),
            "top_n":           TOP_N,
            "industry_name":   industry_name,
        },
    }


@router.get("/yega-frequency")
def yega_frequency(
    base_amount: int = Query(..., description="기초금액 (원)", gt=0),
    a_value: Optional[int] = Query(None, description="A값/예비가격 기초금액 (원). 미입력 시 기초금액 기반 추정"),
    agency_id: Optional[int] = Query(None, description="발주처 ID. 입력 시 발주처 특화 패턴 포함"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    복수예가 예비가격 C(15,4) 조합 빈도 분석 (Prism형).

    A값 ±2% 범위의 15개 예비가격 후보에서 4개를 추첨할 때
    나올 수 있는 1,365가지 평균(예정가격)의 빈도 분포를 반환.
    agency_id 입력 시 발주처 과거 낙찰 패턴을 추가 분석.
    """
    from ...ml.yega import calc_yega_frequency
    result = calc_yega_frequency(base_amount=base_amount, a_value=a_value)

    if agency_id:
        agency_pattern = AgencyYegaService(db).get_pattern(agency_id)
        result["agency_pattern"] = agency_pattern

    return result