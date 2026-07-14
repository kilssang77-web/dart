import sys, os, logging
sys.path.insert(0, "/app")
os.chdir("/app")
logging.basicConfig(level=logging.INFO)

from app.ml.engine import get_engine
engine = get_engine()
print("ver:", engine._version)
print("rate:", engine._rate_models is not None)
print("win:", engine._win_model is not None)

sample = {
    "agency_avg_rate_12m": 0.9071, "agency_win_rate_12m": 0.5,
    "agency_bid_count_12m": 20, "region_avg_rate_12m": 0.9070,
    "industry_avg_rate_12m": 0.9074, "expected_competitor_count": 8,
    "competitor_strength_score": 4.5, "season_index": 2,
    "amount_log10": 8.2, "amount_bucket": 2,
    "similar_bid_count": 10, "similar_avg_rate": 0.9068,
    "similar_std_rate": 0.003, "month_of_year": 5,
    "is_q4": 0, "has_region_restriction": 0, "srate_pred_center": 0.985,
}
rec = engine.recommend(sample)
rr = rec["rate_range"]
print("lower:", rr["lower"], "center:", rr["center"], "upper:", rr["upper"])
print("win_prob:", rec["win_probabilities"])
print("model:", rec["model_version"])
