"""
Engine A — 사정율(예정가격/기초금액) 예측 엔진
Engine D — 시장 변동성 분석 엔진

학습 데이터: bids.estimated_price IS NOT NULL 레코드
폴백: 전국 평균 사정율 0.985 (데이터 부족 시)
"""
import logging
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import os

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)
MODEL_DIR = Path(os.getenv("ML_MODELS_PATH", "/app/ml_models"))
MODEL_DIR.mkdir(parents=True, exist_ok=True)

GLOBAL_SRATE_DEFAULT = 0.8850   # 복수예가 방식 실데이터 기반 평균 (실측 0.8813)

SRATE_FEATURE_COLS = [
    "agency_srate_mean", "agency_srate_std", "agency_srate_trend", "agency_srate_n",
    "industry_srate_mean", "industry_srate_std",
    "region_srate_mean",
    "global_srate_mean", "global_srate_std",
    "amount_log10", "amount_bucket",
    "month_of_year", "quarter", "is_q4",
    "inpo21c_srate_mean", "inpo21c_srate_std", "inpo21c_srate_n",
]


# ──────────────────────────────────────────────
# 통계 로더 (assessment_rate_stats 테이블 조회)
# ──────────────────────────────────────────────

def load_srate_stats(
    db: Session,
    agency_id: int,
    industry_id: int,
    region_id: int,
    base_amount: int,
    bid_date: Optional[datetime] = None,
) -> dict:
    dt = bid_date or datetime.now()

    def _q(group_type, group_id):
        row = db.execute(text("""
            SELECT srate_mean, srate_std, srate_trend, sample_count,
                   srate_p25, srate_p75
            FROM assessment_rate_stats
            WHERE group_type = :gt
              AND (group_id = :gid OR (:gid IS NULL AND group_id IS NULL))
              AND ABS(srate_mean - (10.0/11.0)) > 0.002
              AND sample_count >= 3
            ORDER BY updated_at DESC LIMIT 1
        """), {"gt": group_type, "gid": group_id}).fetchone()
        return row

    ag  = _q("agency",   agency_id)
    ind = _q("industry", industry_id)
    reg = _q("region",   region_id)
    glb = _q("global",   None)

    def _amount_bucket(amt):
        if amt < 1e8:    return 1
        elif amt < 3e8:  return 2
        elif amt < 1e9:  return 3
        elif amt < 5e9:  return 4
        else:            return 5

    # inpo21c 실측 사정율: 기관별 (agency_name 퍼지 매칭) + 전국 평균
    inpo_ag = db.execute(text("""
        SELECT AVG(ib.yega_ratio / 100.0), STDDEV(ib.yega_ratio / 100.0), COUNT(*)
        FROM inpo21c_bids ib
        JOIN agencies a ON TRIM(a.name) = TRIM(ib.agency_name)
                        OR TRIM(ib.agency_name) LIKE '%' || TRIM(a.name) || '%'
                        OR TRIM(a.name) LIKE '%' || TRIM(ib.agency_name) || '%'
        WHERE a.id = :aid
          AND ib.yega_ratio BETWEEN 87 AND 105
    """), {"aid": agency_id}).fetchone() if agency_id else None

    inpo_glb = db.execute(text("""
        SELECT AVG(yega_ratio / 100.0), STDDEV(yega_ratio / 100.0)
        FROM inpo21c_bids
        WHERE yega_ratio BETWEEN 87 AND 105
    """)).fetchone()

    # ── 경쟁업체 수 (inpo21c_participants 실측 — bid_results는 낙찰자만 저장) ──
    # 기관별: inpo21c_bids.agency_name ↔ agencies.name 매칭
    _comp_ag = None
    if agency_id:
        _comp_ag = db.execute(text("""
            SELECT ROUND(AVG(c)::numeric, 1)::float, COUNT(*) AS n_bids
            FROM (
                SELECT COUNT(*) AS c
                FROM inpo21c_participants ip
                JOIN inpo21c_bids ib ON ib.inpo21c_bid_id = ip.inpo21c_bid_id
                JOIN agencies a ON a.name = ib.agency_name
                WHERE a.id = :aid
                  AND ip.company_name != '유찰'
                GROUP BY ip.inpo21c_bid_id
                HAVING COUNT(*) >= 2
            ) t
        """), {"aid": agency_id}).fetchone()

    # 전국 평균 (inpo21c 전체 참여자 기준)
    _comp_glb = db.execute(text("""
        SELECT ROUND(AVG(c)::numeric, 1)::float
        FROM (
            SELECT COUNT(*) AS c
            FROM inpo21c_participants
            WHERE company_name != '유찰'
            GROUP BY inpo21c_bid_id
            HAVING COUNT(*) >= 2
        ) t
    """)).fetchone()

    return {
        "agency_srate_mean":   float(ag[0])   if ag  else None,
        "agency_srate_std":    float(ag[1])   if ag  else 0.012,
        "agency_srate_trend":  float(ag[2])   if ag  else 0.0,
        "agency_srate_n":      int(ag[3])      if ag  else 0,
        "agency_srate_p25":    float(ag[4])   if ag  else None,
        "agency_srate_p75":    float(ag[5])   if ag  else None,
        "industry_srate_mean": float(ind[0])  if ind else None,
        "industry_srate_std":  float(ind[1])  if ind else 0.012,
        "region_srate_mean":   float(reg[0])  if reg else None,
        "global_srate_mean":   float(glb[0])  if glb else GLOBAL_SRATE_DEFAULT,
        "global_srate_std":    float(glb[1])  if glb else 0.012,
        "amount_log10":        round(math.log10(max(base_amount, 1)), 4),
        "amount_bucket":       _amount_bucket(base_amount),
        "month_of_year":       dt.month,
        "quarter":             (dt.month - 1) // 3 + 1,
        "is_q4":               int(dt.month >= 10),
        # inpo21c 실측값 (복수예가 건설공사 기준)
        "inpo21c_srate_mean":  float(inpo_ag[0])  if inpo_ag and inpo_ag[0]  else None,
        "inpo21c_srate_std":   float(inpo_ag[1])  if inpo_ag and inpo_ag[1]  else 0.007,
        "inpo21c_srate_n":     int(inpo_ag[2])    if inpo_ag and inpo_ag[2]  else 0,
        "inpo21c_global_mean": float(inpo_glb[0]) if inpo_glb and inpo_glb[0] else None,
        # 경쟁업체 수 (inpo21c 전참여자 기반: 기관 실측 → 전국 평균 fallback)
        "expected_competitor_count": (
            float(_comp_ag[0]) if _comp_ag and _comp_ag[0] and int(_comp_ag[1]) >= 3
            else None
        ),
        "global_comp_count":  float(_comp_glb[0]) if _comp_glb and _comp_glb[0] else 8.0,
        # 데이터 품질 레벨 (assessment_rate_stats 가용 깊이)
        "data_quality_level": (
            "agency"   if ag  and int(ag[3])  >= 5  else
            "industry" if ind and ind[0]             else
            "region"   if reg and reg[0]             else
            "global"
        ),
        # Journal 피드백 편향 (실전 개찰 결과 기반)
        **_load_journal_bias(db, agency_id),
    }


# ──────────────────────────────────────────────
# Journal 피드백 편향 계산 (내부 헬퍼)
# ──────────────────────────────────────────────

def _load_journal_bias(db: Session, agency_id: Optional[int]) -> dict:
    """
    bid_journal.srate_error(actual - predicted)로 기관별/전체 편향 계산.
    양수 = 우리 모델이 낮게 예측함(실제가 더 높음) → center 상향 보정 필요.
    """
    agency_row = None
    if agency_id:
        try:
            agency_row = db.execute(text("""
                SELECT AVG(j.srate_error), COUNT(*)
                FROM bid_journal j
                JOIN bids b ON b.id = j.bid_id
                WHERE b.agency_id = :aid
                  AND j.srate_error IS NOT NULL
                  AND j.created_at >= NOW() - INTERVAL '24 months'
            """), {"aid": agency_id}).fetchone()
        except Exception:
            agency_row = None

    try:
        global_row = db.execute(text("""
            SELECT AVG(srate_error), COUNT(*)
            FROM bid_journal
            WHERE srate_error IS NOT NULL
              AND created_at >= NOW() - INTERVAL '24 months'
        """)).fetchone()
    except Exception:
        global_row = None

    return {
        "journal_agency_bias":   float(agency_row[0]) if agency_row and agency_row[0] else None,
        "journal_agency_bias_n": int(agency_row[1])   if agency_row and agency_row[1] else 0,
        "journal_global_bias":   float(global_row[0]) if global_row and global_row[0] else None,
        "journal_global_bias_n": int(global_row[1])   if global_row and global_row[1] else 0,
    }


# ──────────────────────────────────────────────
# 배치: 사정율 집계 → assessment_rate_stats 저장
# ──────────────────────────────────────────────

def compute_and_store_stats(db: Session) -> int:
    """
    bids.estimated_price IS NOT NULL 레코드에서 사정율을 계산하고
    기관/공종/지역/전체 단위로 집계하여 assessment_rate_stats에 저장.
    returns: 처리된 행 수
    """
    rows = db.execute(text("""
        SELECT
            b.agency_id,
            b.industry_id,
            b.region_id,
            EXTRACT(YEAR  FROM b.bid_open_date)::int AS yr,
            EXTRACT(MONTH FROM b.bid_open_date)::int AS mo,
            (b.estimated_price::numeric / NULLIF(b.base_amount, 0)) AS srate
        FROM bids b
        WHERE b.estimated_price IS NOT NULL
          AND b.base_amount > 0
          AND b.bid_open_date >= NOW() - INTERVAL '24 months'
          -- 부가세 제외 고정비율(base×10/11≈0.9091) 공고 제거: 복수예가 랜덤 결과가 아님
          AND ABS(b.estimated_price::numeric / NULLIF(b.base_amount,0) - (10.0/11.0)) > 0.002
    """)).fetchall()

    if not rows:
        logger.warning("사정율 집계: 대상 데이터 없음 (estimated_price 미수집)")
        return 0

    df = pd.DataFrame(rows, columns=["agency_id","industry_id","region_id","yr","mo","srate"])
    df["srate"] = pd.to_numeric(df["srate"], errors="coerce")
    df = df[df["srate"].between(0.80, 1.05)]   # 이상치 제거 (복수예가 실범위)

    total = 0

    def _upsert(group_type, group_id, sub):
        nonlocal total
        rates = sub["srate"].dropna()
        if len(rates) < 3:
            return
        trend = 0.0
        if len(rates) >= 6:
            from scipy.stats import linregress
            slope, *_ = linregress(np.arange(len(rates)), rates.values)
            trend = float(slope)

        yr_val   = int(sub["yr"].max())
        gid_safe = group_id if group_id is not None else -1
        db.execute(text("""
            INSERT INTO assessment_rate_stats
                (group_type, group_id, group_id_safe, period_year, period_month, period_month_safe,
                 sample_count, srate_mean, srate_std,
                 srate_p10, srate_p25, srate_p50, srate_p75, srate_p90,
                 srate_trend, updated_at)
            VALUES
                (:gt, :gid, :gid_safe, :yr, NULL, -1,
                 :cnt, :mean, :std,
                 :p10, :p25, :p50, :p75, :p90,
                 :trend, NOW())
            ON CONFLICT (group_type, group_id_safe, period_year, period_month_safe)
            DO UPDATE SET
                sample_count = EXCLUDED.sample_count,
                srate_mean   = EXCLUDED.srate_mean,
                srate_std    = EXCLUDED.srate_std,
                srate_p10    = EXCLUDED.srate_p10,
                srate_p25    = EXCLUDED.srate_p25,
                srate_p50    = EXCLUDED.srate_p50,
                srate_p75    = EXCLUDED.srate_p75,
                srate_p90    = EXCLUDED.srate_p90,
                srate_trend  = EXCLUDED.srate_trend,
                updated_at   = NOW()
        """), {
            "gt": group_type, "gid": group_id, "gid_safe": gid_safe, "yr": yr_val,
            "cnt": int(len(rates)),
            "mean": float(rates.mean()),           "std":  float(rates.std()),
            "p10":  float(rates.quantile(0.10)),   "p25":  float(rates.quantile(0.25)),
            "p50":  float(rates.quantile(0.50)),   "p75":  float(rates.quantile(0.75)),
            "p90":  float(rates.quantile(0.90)),
            "trend": float(trend),
        })
        total += 1

    _upsert("global", None, df)
    for gid, grp in df.groupby("agency_id"):
        _upsert("agency", int(gid), grp)
    for gid, grp in df.groupby("industry_id"):
        _upsert("industry", int(gid), grp)
    for gid, grp in df.groupby("region_id"):
        _upsert("region", int(gid), grp)

    db.commit()
    logger.info(f"사정율 집계 완료: {total}개 그룹 업서트, 원본 {len(df)}건")
    return len(df)


# ──────────────────────────────────────────────
# Engine A: 사정율 예측
# ──────────────────────────────────────────────

def train_srate_model(db: Session) -> bool:
    """
    사정율 LightGBM Quantile 모델 학습.
    최소 50건 이상일 때 학습, 이하이면 False 반환.
    """
    import lightgbm as lgb
    from sklearn.model_selection import train_test_split
    from sklearn.impute import SimpleImputer

    rows = db.execute(text("""
        SELECT
            b.agency_id, b.industry_id, b.region_id,
            b.base_amount,
            EXTRACT(MONTH   FROM b.bid_open_date)::int  AS month_of_year,
            EXTRACT(QUARTER FROM b.bid_open_date)::int  AS quarter,
            CASE WHEN EXTRACT(MONTH FROM b.bid_open_date) >= 10 THEN 1 ELSE 0 END AS is_q4,
            ars_a.srate_mean   AS agency_srate_mean,
            ars_a.srate_std    AS agency_srate_std,
            ars_a.srate_trend  AS agency_srate_trend,
            ars_a.sample_count AS agency_srate_n,
            ars_i.srate_mean   AS industry_srate_mean,
            ars_i.srate_std    AS industry_srate_std,
            ars_r.srate_mean   AS region_srate_mean,
            ars_g.srate_mean   AS global_srate_mean,
            ars_g.srate_std    AS global_srate_std,
            inpo_ag.avg_srate  AS inpo21c_srate_mean,
            inpo_ag.std_srate  AS inpo21c_srate_std,
            inpo_ag.cnt        AS inpo21c_srate_n,
            (b.estimated_price::numeric / b.base_amount) AS srate
        FROM bids b
        LEFT JOIN assessment_rate_stats ars_a
               ON ars_a.group_type='agency'   AND ars_a.group_id=b.agency_id
        LEFT JOIN assessment_rate_stats ars_i
               ON ars_i.group_type='industry' AND ars_i.group_id=b.industry_id
        LEFT JOIN assessment_rate_stats ars_r
               ON ars_r.group_type='region'   AND ars_r.group_id=b.region_id
        LEFT JOIN assessment_rate_stats ars_g
               ON ars_g.group_type='global'   AND ars_g.group_id IS NULL
        LEFT JOIN (
            SELECT a.id AS agency_id,
                   AVG(ib.yega_ratio / 100.0)    AS avg_srate,
                   STDDEV(ib.yega_ratio / 100.0) AS std_srate,
                   COUNT(*)                       AS cnt
            FROM inpo21c_bids ib
            JOIN agencies a ON a.name = ib.agency_name
            WHERE ib.yega_ratio BETWEEN 87 AND 105
            GROUP BY a.id
        ) inpo_ag ON inpo_ag.agency_id = b.agency_id
        WHERE b.estimated_price IS NOT NULL
          AND b.base_amount > 0
          -- 부가세 제외 고정비율(base×10/11≈0.9091) 공고 제거
          AND ABS(b.estimated_price::numeric / NULLIF(b.base_amount,0) - (10.0/11.0)) > 0.002
    """)).fetchall()

    if len(rows) < 50:
        logger.warning(f"사정율 모델 학습 데이터 부족: {len(rows)}건 (최소 50건 필요)")
        return False

    df = pd.DataFrame(rows)
    df.columns = ["agency_id","industry_id","region_id","base_amount",
                  "month_of_year","quarter","is_q4",
                  "agency_srate_mean","agency_srate_std","agency_srate_trend","agency_srate_n",
                  "industry_srate_mean","industry_srate_std","region_srate_mean",
                  "global_srate_mean","global_srate_std",
                  "inpo21c_srate_mean","inpo21c_srate_std","inpo21c_srate_n",
                  "srate"]
    df["amount_log10"]  = df["base_amount"].apply(lambda x: math.log10(max(float(x),1)))
    df["amount_bucket"] = df["base_amount"].apply(lambda x: _bucket(float(x)))
    df["srate"] = pd.to_numeric(df["srate"], errors="coerce")
    # 복수예가 실범위(0.80~1.05) — 기존 0.90~1.05는 복수예가 데이터를 대부분 제외했음
    df = df[df["srate"].between(0.80, 1.05)]

    if len(df) < 50:
        return False

    X = df[SRATE_FEATURE_COLS].copy()
    y = df["srate"].astype(float)

    imputer = SimpleImputer(strategy="median")
    X_imp = imputer.fit_transform(X)
    X_tr, X_val, y_tr, y_val = train_test_split(X_imp, y, test_size=0.2, random_state=42)

    models = {}
    for q in [0.10, 0.25, 0.50, 0.75, 0.90]:
        m = lgb.LGBMRegressor(
            objective="quantile", alpha=q,
            n_estimators=300, num_leaves=31, learning_rate=0.03,
            min_child_samples=5, subsample=0.8, colsample_bytree=0.8,
            verbosity=-1, random_state=42,
        )
        m.fit(X_tr, y_tr,
              eval_set=[(X_val, y_val)],
              callbacks=[lgb.early_stopping(50, verbose=False),
                         lgb.log_evaluation(-1)])
        models[q] = m

    joblib.dump(models,  MODEL_DIR / "srate_models.pkl")
    joblib.dump(imputer, MODEL_DIR / "srate_imputer.pkl")
    logger.info(f"사정율 모델 학습 완료: {len(df)}건 사용")
    return True


def _bucket(amt: float) -> int:
    if amt < 1e8:   return 1
    elif amt < 3e8: return 2
    elif amt < 1e9: return 3
    elif amt < 5e9: return 4
    else:           return 5


def predict_srate(features_a: dict, base_amount: int) -> dict:
    """
    사정율 예측 → 예정가격 추정 반환.
    모델 없으면 통계 기반 규칙 폴백.
    """
    srate_models_path = MODEL_DIR / "srate_models.pkl"
    srate_imputer_path = MODEL_DIR / "srate_imputer.pkl"

    center = (features_a.get("agency_srate_mean")
              or features_a.get("industry_srate_mean")
              or features_a.get("global_srate_mean")
              or GLOBAL_SRATE_DEFAULT)
    std    = features_a.get("agency_srate_std") or 0.012
    trend  = features_a.get("agency_srate_trend") or 0.0
    n      = features_a.get("agency_srate_n") or 0
    is_q4  = features_a.get("is_q4", 0)

    # Q4 보정: 연말 예산 집행 → 사정율 미세 하락 경향
    center += trend * 0.5 + (is_q4 * -0.001)

    # 신뢰도: 샘플 수와 표준편차 기반
    confidence = min(0.95, (n / 60) * (1.0 - min(std * 15, 0.7)))
    confidence = max(0.10, confidence)

    if srate_models_path.exists() and srate_imputer_path.exists():
        try:
            models  = joblib.load(srate_models_path)
            imputer = joblib.load(srate_imputer_path)
            X = np.array([[features_a.get(c) for c in SRATE_FEATURE_COLS]], dtype=float)
            X_imp = imputer.transform(X)
            preds = {q: float(m.predict(X_imp)[0]) for q, m in models.items()}
            center = preds[0.50]
            lower  = preds[0.25]
            upper  = preds[0.75]
            p10    = preds[0.10]
            p90    = preds[0.90]
            # inpo21c 보정: G2B 역사 모델이 구 사정율로 훈련된 경우 global 통계로 보정
            _global = features_a.get('global_srate_mean')
            if _global and _global > 0.95 and center < 0.95:
                _delta = _global - center  # inpo21c 기준으로 전면 보정
                center += _delta
                lower  += _delta
                upper  += _delta
                p10    += _delta
                p90    += _delta
            # ML 사용 시 신뢰도 상향
            confidence = min(0.95, confidence + 0.2)
        except Exception as e:
            logger.warning(f"사정율 ML 예측 실패, 규칙 폴백: {e}")
            lower = center - std * 0.8
            upper = center + std * 0.8
            p10   = center - std * 1.5
            p90   = center + std * 1.5
    else:
        lower = center - std * 0.8
        upper = center + std * 0.8
        p10   = center - std * 1.5
        p90   = center + std * 1.5

    # inpo21c 실측 사정율로 보정 (복수예가 건설공사 기준)
    inpo_mean = features_a.get("inpo21c_srate_mean")
    inpo_n    = features_a.get("inpo21c_srate_n", 0) or 0
    inpo_std  = features_a.get("inpo21c_srate_std") or 0.007
    inpo_glb  = features_a.get("inpo21c_global_mean")
    srate_source = "lgbm" if srate_models_path.exists() else "global"

    if inpo_mean and inpo_n >= 3:
        # 기관별 실측값: Bayesian 블렌딩 (n=3→23%, n=10→50%, n=20→67%, n=50→83%)
        srate_source = "inpo21c"
        w = min(0.85, inpo_n / (inpo_n + 10))
        old_c  = center
        center = old_c * (1.0 - w) + inpo_mean * w
        delta  = center - old_c
        lower += delta;  upper += delta;  p10 += delta;  p90 += delta
        eff_std  = std * (1.0 - w) + inpo_std * w
        new_half = max(eff_std * 1.0, min((upper - lower) / 2, eff_std * 2.5))
        lower = center - new_half;  upper = center + new_half
        confidence = min(0.95, confidence + 0.25)
    elif inpo_glb:
        # 기관별 없음 — 전국 inpo21c 평균으로 가볍게 보정
        w      = 0.25
        old_c  = center
        center = old_c * (1.0 - w) + inpo_glb * w
        delta  = center - old_c
        lower += delta;  upper += delta;  p10 += delta;  p90 += delta
        confidence = min(0.95, confidence + 0.05)

    # Journal 피드백 편향 보정 — 실전 개찰 결과 기반 마지막 보정
    j_agency_bias = features_a.get("journal_agency_bias")
    j_agency_n    = int(features_a.get("journal_agency_bias_n") or 0)
    j_global_bias = features_a.get("journal_global_bias")
    j_global_n    = int(features_a.get("journal_global_bias_n") or 0)

    if j_agency_bias is not None and j_agency_n >= 5:
        # 기관별 실전 편향: n=5→38%, n=10→56%, n=20→71%, n=50→86%
        w = min(0.85, j_agency_n / (j_agency_n + 8))
        correction = float(j_agency_bias) * w
        center += correction; lower += correction; upper += correction
        p10    += correction; p90   += correction
        srate_source += "+journal_agency"
        confidence = min(0.95, confidence + 0.05)
    elif j_global_bias is not None and j_global_n >= 10:
        # 전체 편향 (약하게 — 기관별 데이터 없을 때만)
        correction = float(j_global_bias) * 0.3
        center += correction; lower += correction; upper += correction
        p10    += correction; p90   += correction
        srate_source += "+journal_global"

    # 사정율 범위 클램핑 (실제 데이터 기반: 0.87 ~ 1.05)
    lower  = max(0.87, lower)
    upper  = min(1.05, upper)
    center = max(lower, min(upper, center))

    return {
        "srate_range": {
            "p10":    round(p10,    4),
            "lower":  round(lower,  4),
            "center": round(center, 4),
            "upper":  round(upper,  4),
            "p90":    round(p90,    4),
        },
        "estimated_price_range": {
            "lower":  int(base_amount * lower),
            "center": int(base_amount * center),
            "upper":  int(base_amount * upper),
        },
        "confidence": round(confidence, 3),
        "used_model": srate_models_path.exists(),
        "sample_count": n,
        "srate_source": srate_source,
        "inpo21c_n": int(inpo_n),
    }


# ──────────────────────────────────────────────
# Engine D: 시장 변동성 분석
# ──────────────────────────────────────────────

def compute_market_trend(
    db: Session,
    agency_id: int,
    industry_id: int,
    bid_date: Optional[datetime] = None,
) -> dict:
    """최근 4주 vs 이전 4주 사정율·낙찰률·입찰건수 변화 계산."""
    dt = bid_date or datetime.now()
    w4 = dt - timedelta(weeks=4)
    w8 = dt - timedelta(weeks=8)

    def _stats(start, end):
        row = db.execute(text("""
            SELECT
                AVG(b.estimated_price::numeric / NULLIF(b.base_amount,0)) AS srate,
                AVG(r.bid_rate)   FILTER (WHERE r.is_winner)              AS win_rate,
                COUNT(DISTINCT b.id)                                      AS cnt
            FROM bids b
            LEFT JOIN bid_results r ON r.bid_id=b.id AND r.is_winner
            WHERE b.agency_id   = :aid
              AND b.industry_id = :iid
              AND b.bid_open_date BETWEEN :s AND :e
              AND b.status = 'closed'
              AND (b.estimated_price IS NULL OR ABS(b.estimated_price::numeric / NULLIF(b.base_amount,0) - (10.0/11.0)) > 0.002)
        """), {"aid": agency_id, "iid": industry_id, "s": start, "e": end}).fetchone()
        return row

    recent = _stats(w4, dt)
    prev   = _stats(w8, w4)

    def _chg(rv, pv):
        if rv and pv and float(pv) > 0:
            return round((float(rv) - float(pv)) / float(pv), 6)
        return 0.0

    srate_chg  = _chg(recent[0], prev[0]) if recent and prev else 0.0
    rate_chg   = _chg(recent[1], prev[1]) if recent and prev else 0.0
    volume_chg = _chg(recent[2], prev[2]) if recent and prev else 0.0

    # 변동성 지수: 사정율 표준편차 대용 (prev 사용)
    vol_idx = float(prev[0] or GLOBAL_SRATE_DEFAULT) * 0.01 if prev else 0.01

    # 트렌드 조정값: 사정율 상승 추세이면 추천 투찰률도 소폭 상향
    trend_adj = srate_chg * 0.3 + rate_chg * 0.1

    return {
        "srate_4w_change":  round(srate_chg,  6),
        "rate_4w_change":   round(rate_chg,   6),
        "volume_4w_change": round(volume_chg, 6),
        "volatility_index": round(vol_idx,    6),
        "trend_adjustment": round(trend_adj,  6),
        "has_recent_data":  bool(recent and recent[2] and int(recent[2]) > 0),
    }

# ──────────────────────────────────────────────
# 사정률 이동평균 (최근 20건 기준)
# ──────────────────────────────────────────────

def compute_srate_moving_average(
    db: Session,
    agency_id: int,
    industry_id: int,
    window: int = 20,
) -> dict:
    """
    동일 기관+공종 최근 window건의 사정률 이동평균 계산.

    Returns:
        srate_ma     : 이동평균값 (None: 데이터 부족)
        srate_ma_std : 이동평균 구간 표준편차
        sample_count : 사용된 샘플 수
        trend        : 전반부/후반부 평균 차이 (양수=상승 추세)
        is_reliable  : window >= sample_count * 0.8 여부
    """
    rows = db.execute(text("""
        SELECT (b.estimated_price::numeric / NULLIF(b.base_amount, 0)) AS srate
        FROM bids b
        WHERE b.agency_id   = :aid
          AND b.industry_id = :iid
          AND b.estimated_price IS NOT NULL
          AND b.base_amount > 0
          AND b.bid_open_date IS NOT NULL
          AND ABS(b.estimated_price::numeric / NULLIF(b.base_amount,0) - (10.0/11.0)) > 0.002
        ORDER BY b.bid_open_date DESC
        LIMIT :win
    """), {"aid": agency_id, "iid": industry_id, "win": window}).fetchall()

    # 복수예가 실범위(0.80~1.05)로 확장 — 기존 0.90 기준은 복수예가 데이터를 제외했음
    srates = [float(r[0]) for r in rows if r[0] and 0.80 <= float(r[0]) <= 1.05]
    n = len(srates)
    if n < 3:
        return {
            "srate_ma":     None,
            "srate_ma_std": None,
            "sample_count": n,
            "trend":        0.0,
            "is_reliable":  False,
        }

    arr = np.array(srates)
    ma  = float(arr.mean())
    std = float(arr.std())

    mid = n // 2
    trend = float(arr[:mid].mean() - arr[mid:].mean()) if n >= 6 else 0.0

    return {
        "srate_ma":     round(ma,    5),
        "srate_ma_std": round(std,   5),
        "sample_count": n,
        "trend":        round(trend, 6),
        "is_reliable":  n >= max(3, window // 2),
    }


# ──────────────────────────────────────────────
# ① 사정율 빈도 분포 v2 (소수점 3자리 × 발주처별)
# ──────────────────────────────────────────────

def compute_srate_frequency_v2(db: Session) -> int:
    """
    inpo21c_participants 실증 데이터로 rate_frequency_tables 재구축.

    - 버킷: ROUND(assessment_rate, 3) = 0.001 단위
    - 기간: 12M / 24M / 48M
    - 기관: inpo21c_bids.agency_name → agencies 테이블 매칭
    - 기존 0.005 버킷 데이터 전량 삭제 후 재삽입

    Returns: upserted row count
    """
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    cutoffs = {
        "12M": now - timedelta(days=365),
        "24M": now - timedelta(days=730),
        "48M": now - timedelta(days=1460),
    }

    # 기존 데이터 전량 삭제 (0.005 버킷 포함 전부)
    db.execute(text("DELETE FROM rate_frequency_tables"))
    db.commit()

    total_upserted = 0

    for period_label, cutoff_dt in cutoffs.items():
        rows = db.execute(text("""
            SELECT a.id                                             AS agency_id,
                   ROUND(ip.assessment_rate::numeric, 3)           AS srate_bucket,
                   COUNT(*)                                        AS total_cnt,
                   SUM(CASE WHEN ip.is_winner THEN 1 ELSE 0 END)  AS win_cnt
            FROM inpo21c_participants ip
            JOIN inpo21c_bids ib ON ib.inpo21c_bid_id = ip.inpo21c_bid_id
            JOIN agencies a ON (
                TRIM(a.name) = TRIM(ib.agency_name)
                OR TRIM(ib.agency_name) LIKE '%%' || TRIM(a.name) || '%%'
                OR TRIM(a.name) LIKE '%%' || TRIM(ib.agency_name) || '%%'
            )
            WHERE ip.assessment_rate BETWEEN 0.750 AND 1.100
              AND ib.open_datetime >= :cutoff
            GROUP BY a.id, srate_bucket
            ORDER BY a.id, srate_bucket
        """), {"cutoff": cutoff_dt}).fetchall()

        for r in rows:
            agency_id, bucket, total_cnt, win_cnt = r
            win_rate = round(win_cnt / total_cnt, 4) if total_cnt > 0 else 0.0
            db.execute(text("""
                INSERT INTO rate_frequency_tables
                    (agency_id, industry_code, period_type, bucket_from, bucket_to,
                     bucket_width, count, win_count, win_rate)
                VALUES (:ag, 'ALL', :pt, :bf, :bt, 0.001, :cnt, :wcnt, :wr)
                ON CONFLICT (agency_id, industry_code, period_type, bucket_from)
                DO UPDATE SET
                    count      = EXCLUDED.count,
                    win_count  = EXCLUDED.win_count,
                    win_rate   = EXCLUDED.win_rate,
                    updated_at = now()
            """), {
                "ag":   agency_id,
                "pt":   period_label,
                "bf":   float(bucket),
                "bt":   float(bucket) + 0.001,
                "cnt":  int(total_cnt),
                "wcnt": int(win_cnt),
                "wr":   win_rate,
            })
            total_upserted += 1

        db.commit()
        logger.info("사정율 빈도 v2 [%s]: %d rows", period_label, len(rows))

    return total_upserted


# ──────────────────────────────────────────────
# ② A값 비율 조회 (발주처 실적 기반)
# ──────────────────────────────────────────────

def get_agency_a_ratio(db: Session, agency_id: int | None) -> float:
    """
    inpo21c 실측 데이터에서 발주처별 예정가격/기초금액 비율 반환.
    데이터 없으면 전국 평균(0.910) 반환.
    """
    NATIONAL_AVG = 0.9100

    if agency_id:
        row = db.execute(text("""
            SELECT AVG(ib.estimated_amount::float / NULLIF(ib.base_amount, 0))
            FROM inpo21c_bids ib
            JOIN agencies a ON (
                TRIM(a.name) = TRIM(ib.agency_name)
                OR TRIM(ib.agency_name) LIKE '%%' || TRIM(a.name) || '%%'
                OR TRIM(a.name) LIKE '%%' || TRIM(ib.agency_name) || '%%'
            )
            WHERE a.id = :ag
              AND ib.estimated_amount IS NOT NULL
              AND ib.base_amount > 0
              AND ib.estimated_amount::float / ib.base_amount BETWEEN 0.70 AND 1.10
        """), {"ag": agency_id}).scalar()

        if row and 0.70 < float(row) < 1.10:
            return round(float(row), 4)

    # 전국 평균
    row = db.execute(text("""
        SELECT AVG(estimated_amount::float / NULLIF(base_amount, 0))
        FROM inpo21c_bids
        WHERE estimated_amount IS NOT NULL AND base_amount > 0
          AND estimated_amount::float / base_amount BETWEEN 0.70 AND 1.10
    """)).scalar()

    return round(float(row), 4) if row else NATIONAL_AVG


# ──────────────────────────────────────────────
# ③ 프리즘형 TOP 구간 추출 (빈도 기반)
# ──────────────────────────────────────────────

def get_prism_zones(
    db: Session,
    agency_id: int | None,
    period_type: str = "24M",
    top_n: int = 10,
) -> dict:
    """
    rate_frequency_tables 기반 프리즘 분석.

    Returns:
        histogram : 전체 빈도 히스토그램 (0.001 버킷)
        top_zones : 낙찰 확률 상위 top_n 구간
        a_ratio   : 발주처 A값 비율 (예정가/기초금액)
        data_source: agency | national
    """
    # 발주처 전용 데이터
    source = "national"
    if agency_id:
        hist_rows = db.execute(text("""
            SELECT bucket_from, count, win_count, win_rate
            FROM rate_frequency_tables
            WHERE agency_id = :ag AND period_type = :pt AND industry_code = 'ALL'
            ORDER BY bucket_from
        """), {"ag": agency_id, "pt": period_type}).fetchall()

        if hist_rows:
            source = "agency"

    # 발주처 데이터 없으면 전국 집계
    if source == "national":
        hist_rows = db.execute(text("""
            SELECT bucket_from,
                   SUM(count)     AS count,
                   SUM(win_count) AS win_count,
                   CASE WHEN SUM(count) > 0
                        THEN ROUND(SUM(win_count)::numeric / SUM(count), 4)
                        ELSE 0 END AS win_rate
            FROM rate_frequency_tables
            WHERE period_type = :pt AND industry_code = 'ALL'
            GROUP BY bucket_from
            ORDER BY bucket_from
        """), {"pt": period_type}).fetchall()

    histogram = [
        {
            "srate":     round(float(r[0]), 3),
            "count":     int(r[1]),
            "win_count": int(r[2]),
            "win_rate":  round(float(r[3]), 4),
        }
        for r in hist_rows
    ]

    # 통계적으로 유의한 구간만 TOP 선정 (count >= 5)
    eligible = [h for h in histogram if h["count"] >= 5]

    # 점수: win_rate × log(win_count+1)  — 절대 승수와 확률 균형
    def _score(h):
        import math
        return h["win_rate"] * math.log(h["win_count"] + 1)

    top_zones = sorted(eligible, key=_score, reverse=True)[:top_n]

    # 각 구간에 실제 투찰금액 계산용 메타 추가 (rank 포함)
    for idx, z in enumerate(top_zones, 1):
        z["rank"] = idx

    a_ratio = get_agency_a_ratio(db, agency_id)

    return {
        "histogram":   histogram,
        "top_zones":   top_zones,
        "a_ratio":     a_ratio,
        "data_source": source,
        "period_type": period_type,
        "total_bids":  sum(h["count"] for h in histogram),
        "total_wins":  sum(h["win_count"] for h in histogram),
    }


# ──────────────────────────────────────────────
# B-4: 기관별 사정율 세분화 프로파일 + 계절 패턴
# ──────────────────────────────────────────────

def load_agency_srate_profile(
    db: Session,
    agency_id: int,
    industry_id: int = 0,
    bid_date: Optional[datetime] = None,
) -> dict:
    """
    기관별 사정율 세분화 프로파일.

    단순 평균 대신:
      · 최근 12개월 monthly 이동평균 (트렌드)
      · 월별 계절지수 (당월 편향)
      · 공종 교차 효과 (기관 × 공종 평균)
      · Bayesian 블렌드 (기관 ← 공종 ← 전국 순)

    Returns:
        blended_center : 최종 추천 사정율 중심
        seasonal_adj   : 당월 계절 보정값
        trend_slope    : 최근 트렌드 기울기 (월 단위)
        confidence     : 데이터 신뢰도 0~1
        raw            : 세부 raw 수치 dict
    """
    dt = bid_date or datetime.now()
    month = dt.month

    # ── 1. 기관별 월간 사정율 이력 (24개월)
    monthly = db.execute(text("""
        SELECT
            TO_CHAR(b.bid_open_date, 'YYYY-MM')                          AS ym,
            AVG(b.estimated_price::numeric / NULLIF(b.base_amount, 0))   AS srate_mean,
            COUNT(*)                                                       AS cnt
        FROM bids b
        WHERE b.agency_id = :aid
          AND b.estimated_price IS NOT NULL
          AND b.base_amount > 0
          AND b.bid_open_date >= NOW() - INTERVAL '24 months'
          AND ABS(b.estimated_price::numeric / NULLIF(b.base_amount, 0) - (10.0/11.0)) > 0.002
        GROUP BY ym
        ORDER BY ym
    """), {"aid": agency_id}).fetchall()

    # ── 2. 기관 × 공종 교차 평균
    cross_row = None
    if industry_id:
        cross_row = db.execute(text("""
            SELECT AVG(b.estimated_price::numeric / NULLIF(b.base_amount, 0)),
                   COUNT(*)
            FROM bids b
            WHERE b.agency_id   = :aid
              AND b.industry_id = :iid
              AND b.estimated_price IS NOT NULL
              AND b.base_amount > 0
              AND b.bid_open_date >= NOW() - INTERVAL '36 months'
        """), {"aid": agency_id, "iid": industry_id}).fetchone()

    # ── 3. 계절지수 (같은 월의 역대 평균 편차)
    seasonal = db.execute(text("""
        SELECT
            EXTRACT(MONTH FROM b.bid_open_date)::int                    AS mo,
            AVG(b.estimated_price::numeric / NULLIF(b.base_amount, 0))  AS srate_mean,
            COUNT(*)                                                      AS cnt
        FROM bids b
        WHERE b.agency_id = :aid
          AND b.estimated_price IS NOT NULL
          AND b.base_amount > 0
          AND b.bid_open_date >= NOW() - INTERVAL '48 months'
          AND ABS(b.estimated_price::numeric / NULLIF(b.base_amount, 0) - (10.0/11.0)) > 0.002
        GROUP BY mo
    """), {"aid": agency_id}).fetchall()

    # ── 4. 전국 평균 (폴백)
    global_row = db.execute(text("""
        SELECT AVG(yega_ratio / 100.0), STDDEV(yega_ratio / 100.0)
        FROM inpo21c_bids WHERE yega_ratio BETWEEN 87 AND 105
    """)).fetchone()
    global_mean = float(global_row[0]) if global_row and global_row[0] else GLOBAL_SRATE_DEFAULT
    global_std  = float(global_row[1]) if global_row and global_row[1] else 0.012

    # ── 계산
    monthly_means = [float(r[1]) for r in monthly if r[1] is not None]
    monthly_counts = [int(r[2]) for r in monthly]
    n_months = len(monthly_means)

    # 트렌드 (선형 회귀)
    trend_slope = 0.0
    if n_months >= 4:
        try:
            from scipy.stats import linregress
            x = np.arange(n_months)
            slope, _, _, _, _ = linregress(x, monthly_means)
            trend_slope = float(slope)
        except Exception:
            pass

    # 최근 3개월 가중평균 (트렌드 반영)
    agency_recent = None
    if monthly_means:
        recent = monthly_means[-3:]
        w = np.arange(1, len(recent) + 1, dtype=float)
        agency_recent = float(np.average(recent, weights=w))

    # 계절 보정
    seasonal_dict = {int(r[0]): float(r[1]) for r in seasonal if r[1] is not None}
    all_season_vals = list(seasonal_dict.values())
    season_overall = float(np.mean(all_season_vals)) if all_season_vals else global_mean
    seasonal_adj = seasonal_dict.get(month, season_overall) - season_overall

    # 교차 기관×공종 평균
    cross_mean = float(cross_row[0]) if cross_row and cross_row[0] else None
    cross_n    = int(cross_row[1])   if cross_row and cross_row[1] else 0

    # Bayesian 블렌드: 기관 → 공종×기관 → 전국
    total_n = sum(monthly_counts)
    if agency_recent is not None and total_n >= 10:
        w_agency = min(0.8, total_n / (total_n + 20))
        if cross_mean and cross_n >= 5:
            blended = agency_recent * w_agency + cross_mean * (1 - w_agency) * 0.6 + global_mean * (1 - w_agency) * 0.4
        else:
            blended = agency_recent * w_agency + global_mean * (1 - w_agency)
        confidence = min(1.0, total_n / 30)
    elif cross_mean and cross_n >= 5:
        blended = cross_mean * 0.7 + global_mean * 0.3
        confidence = min(0.5, cross_n / 20)
    else:
        blended = global_mean
        confidence = 0.1

    # 계절 보정 적용 (신뢰도 가중)
    blended_with_season = blended + seasonal_adj * confidence * 0.5

    return {
        "blended_center":  round(blended_with_season, 5),
        "seasonal_adj":    round(seasonal_adj, 5),
        "trend_slope":     round(trend_slope, 6),
        "confidence":      round(confidence, 3),
        "raw": {
            "agency_recent":  round(agency_recent, 5) if agency_recent else None,
            "cross_mean":     round(cross_mean, 5)    if cross_mean else None,
            "global_mean":    round(global_mean, 5),
            "n_months":       n_months,
            "total_records":  total_n,
        },
    }
