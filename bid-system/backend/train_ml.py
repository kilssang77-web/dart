"""
Engine B 학습 스크립트 v2
- region_id NULL 안전 처리
- 461 낙찰 레코드 기반 XGBoost quantile 회귀 학습
"""
import sys, os, logging
sys.path.insert(0, '/app')
os.chdir('/app')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

import math
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy import text

from app.database import SessionLocal
from app.ml.engine import build_features, train_models, FEATURE_COLS, MODEL_DIR

db = SessionLocal()

# ── Step 3: Engine B 학습 데이터 구성
logger.info('=== Engine B 학습 데이터 구성 ===')

rows = db.execute(text("""
    SELECT
        b.id, b.agency_id, b.industry_id,
        COALESCE(b.region_id, 0) AS region_id,
        b.base_amount, b.bid_open_date,
        COALESCE(b.region_restriction, false) AS region_restriction,
        b.construction_period,
        r.bid_rate AS winner_rate
    FROM bids b
    JOIN bid_results r ON r.bid_id = b.id AND r.is_winner = true
    WHERE b.industry_id = ANY(ARRAY[20,24,31])
      AND b.base_amount > 0
      AND r.bid_rate BETWEEN 0.80 AND 1.00
    ORDER BY b.bid_open_date
""")).fetchall()
logger.info(f'낙찰 레코드: {len(rows)}건')

# 히스토리 로드
cutoff = datetime.now() - timedelta(days=24*30)
hist_rows = db.execute(text("""
    SELECT b.id, b.agency_id, b.industry_id,
           COALESCE(b.region_id, 0) AS region_id,
           b.base_amount, b.bid_open_date,
           r.bid_rate AS winner_rate,
           (SELECT COUNT(*) FROM bid_results r2 WHERE r2.bid_id = b.id) AS competitor_count
    FROM bids b
    LEFT JOIN bid_results r ON r.bid_id = b.id AND r.is_winner = true
    WHERE b.bid_open_date >= :cutoff AND b.status = 'closed'
"""), {"cutoff": cutoff}).fetchall()

hist_df = pd.DataFrame(hist_rows, columns=[
    "id","agency_id","industry_id","region_id",
    "base_amount","bid_open_date","winner_rate","competitor_count"
])
hist_df["winner_rate"]      = pd.to_numeric(hist_df["winner_rate"],      errors="coerce")
hist_df["base_amount"]      = pd.to_numeric(hist_df["base_amount"],      errors="coerce")
hist_df["competitor_count"] = pd.to_numeric(hist_df["competitor_count"], errors="coerce")
logger.info(f'히스토리 데이터: {len(hist_df)}건')

# 피처 생성
records = []
errors = []
for i, row in enumerate(rows):
    bid_id, agency_id, industry_id, region_id, base_amount, bid_open_date, region_restriction, construction_period, winner_rate = row
    if winner_rate is None:
        continue

    hist_before = hist_df[hist_df["bid_open_date"] < bid_open_date].copy() if bid_open_date else hist_df.copy()

    try:
        feats = build_features(
            agency_id=int(agency_id) if agency_id else 0,
            industry_id=int(industry_id) if industry_id else 0,
            region_id=int(region_id),
            base_amount=int(base_amount),
            construction_period=int(construction_period) if construction_period else None,
            region_restriction=bool(region_restriction),
            bid_open_date=bid_open_date,
            historical_df=hist_before,
        )
        feats["target_rate"] = float(winner_rate)
        feats["is_winner"]   = True
        records.append(feats)
    except Exception as e:
        errors.append(str(e))

    if (i+1) % 100 == 0:
        logger.info(f'  피처 생성: {i+1}/{len(rows)} 완료 ({len(records)} 성공, {len(errors)} 실패)')

if errors:
    logger.warning(f'에러 샘플: {errors[:3]}')
logger.info(f'피처 생성 완료: {len(records)}건')

if len(records) < 20:
    logger.error(f'학습 데이터 부족: {len(records)}건 < 20건')
    db.close()
    sys.exit(1)

train_df = pd.DataFrame(records)
for col in FEATURE_COLS:
    if col not in train_df.columns:
        train_df[col] = None

logger.info(f'학습 데이터: {train_df.shape}')
logger.info(f'target_rate: mean={train_df["target_rate"].mean():.4f}, std={train_df["target_rate"].std():.4f}')
logger.info(f'  범위: [{train_df["target_rate"].min():.4f}, {train_df["target_rate"].max():.4f}]')

# 피처별 유효값 비율
valid_pct = (train_df[FEATURE_COLS].notna().mean() * 100).round(1)
logger.info('피처 유효값 비율:')
for feat, pct in valid_pct.items():
    logger.info(f'  {feat}: {pct}%')

# ── Step 4: 모델 학습
logger.info('=== Engine B 모델 학습 ===')
result = train_models(train_df)
if result:
    logger.info(f'학습 완료: {result}')
else:
    logger.warning('학습 실패')

# ── Step 5: 검증
logger.info('=== 모델 검증 ===')
import json
from app.ml.engine import get_engine, RecommendEngine

engine = RecommendEngine()
if engine._rate_models:
    logger.info(f'모델 버전: {engine._version}')
    # 실제 데이터로 검증
    sample = records[len(records)//2]
    sample_feats = {k: sample.get(k) for k in FEATURE_COLS}
    rec = engine._ml_based(sample_feats)
    logger.info(f'검증 샘플 예측:')
    logger.info(f'  실제 낙찰률: {sample["target_rate"]:.4f}')
    logger.info(f'  예측 center: {rec["rate_range"]["center"]:.4f}')
    logger.info(f'  예측 범위:   [{rec["rate_range"]["lower"]:.4f}, {rec["rate_range"]["upper"]:.4f}]')
else:
    logger.warning('모델 로드 실패')

meta_path = MODEL_DIR / 'meta.json'
if meta_path.exists():
    with open(meta_path) as f:
        meta = json.load(f)
    logger.info(f'저장된 모델 메타: {meta}')

db.close()
logger.info('=== 완료 ===')
