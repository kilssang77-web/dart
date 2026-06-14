"""
ML 피처 컬럼 단일 소스 (Single Source of Truth).
lgbm_predictor.py와 ml_client.py 모두 이 모듈에서 가져옵니다.
"""
import json
from pathlib import Path


# 기본 피처 컬럼 (feature_columns.json 없을 때 사용)
# lgbm_predictor.py의 FEATURE_COLUMNS와 동일
DEFAULT_FEATURE_COLUMNS: list[str] = [
    "return_1d", "return_3d", "return_5d",
    "ma5_ratio", "ma20_ratio", "ma60_ratio",
    "ma5_slope", "ma20_slope",
    "vol_ratio_5d", "vol_ratio_20d", "vol_surge",
    "amount_ratio",
    "atr_ratio",
    "rsi14", "rsi_oversold", "rsi_overbought",
    "macd_hist", "macd_golden_cross",
    "bb_pct", "bb_width", "bb_squeeze",
    "body_size", "is_bullish", "upper_wick", "lower_wick",
    "is_new_high_20d", "is_new_high_52d", "is_new_high_260d",
    "pos_52w",
    "foreign_cumnet_5d", "foreign_cumnet_20d",
    "inst_cumnet_5d", "inst_cumnet_20d",
    "dual_buy", "dual_buy_3d",
    "short_ratio", "short_increasing",
    "disclosure_sentiment", "has_favorable_disclosure",
    "kospi_return_1d", "kospi_return_5d",
    "rel_strength_5d",
    "market_vol_ratio",
    "return_10d", "return_20d",
    "price_accel",
    "gap_pct",
    "consec_up", "consec_down",
    "vol_up_down_ratio",
    "ma5_ma20_cross", "ma20_ma60_cross",
    "foreign_net_ratio", "inst_net_ratio",
    "dow_sin", "dow_cos",
    "month_sin", "month_cos",
    "news_sentiment_7d", "news_count_7d",
]


def get_feature_columns(model_dir: str = "/models/lgbm") -> list[str]:
    """feature_columns.json 우선, 없으면 DEFAULT_FEATURE_COLUMNS 반환."""
    path = Path(model_dir) / "feature_columns.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return list(DEFAULT_FEATURE_COLUMNS)


# 모듈 레벨에서 로드 (import 시 즉시 사용 가능)
FEATURE_COLUMNS = get_feature_columns()
