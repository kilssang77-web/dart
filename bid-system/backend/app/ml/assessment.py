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
                  "global_srate_mean","global_srate_std","srate"]
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