"""DefeatAnalysisService.get_gap_distribution 단위 테스트"""
import sys
from datetime import date
from unittest.mock import MagicMock

# ML 라이브러리 미설치 환경 대응
for _mod in ("joblib", "lightgbm", "xgboost", "sklearn",
             "sklearn.cluster", "sklearn.preprocessing", "sklearn.impute"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest
from app.services import DefeatAnalysisService


def _make_record(submitted_rate: float, actual_winner_rate: float, bid_date=None):
    rec = MagicMock()
    rec.submitted_rate = submitted_rate
    rec.actual_winner_rate = actual_winner_rate
    rec.rate_diff = None
    rec.bid_date = bid_date or date(2024, 6, 1)
    return rec


def _make_db(records=None):
    db = MagicMock()
    (
        db.query.return_value
        .filter.return_value
        .order_by.return_value
        .limit.return_value
        .all.return_value
    ) = records or []
    # PersonalBiasAnalyzer는 db.execute를 사용
    db.execute.return_value.fetchall.return_value = []
    return db


class TestGetGapDistribution:

    def test_empty_when_no_records(self):
        svc = DefeatAnalysisService(db=_make_db(records=[]))
        result = svc.get_gap_distribution(user_id=1)

        assert result["total_analyzed"] == 0
        assert result["buckets"] == []
        assert result["mean_diff"] is None
        assert result["median_diff"] is None
        assert result["win_if_lower_by"] is None
        assert result["consistent_direction"] == "mixed"
        assert "personal_bias" in result

    def test_too_high_direction_with_five_records(self):
        # submitted > winner → 내가 높게 투찰 → too_high
        records = [
            _make_record(0.8900, 0.8850),  # diff = +0.005
            _make_record(0.8910, 0.8860),  # diff = +0.005
            _make_record(0.8920, 0.8870),  # diff = +0.005
            _make_record(0.8930, 0.8880),  # diff = +0.005
            _make_record(0.8940, 0.8890),  # diff = +0.005
        ]
        svc = DefeatAnalysisService(db=_make_db(records=records))
        result = svc.get_gap_distribution(user_id=1)

        assert result["total_analyzed"] == 5
        assert result["consistent_direction"] == "too_high"
        assert result["mean_diff"] is not None
        assert abs(result["mean_diff"] - 0.005) < 1e-4
        assert result["win_if_lower_by"] is not None
        assert abs(result["win_if_lower_by"] - 0.005) < 1e-4
        assert len(result["buckets"]) > 0

    def test_too_low_direction(self):
        # submitted < winner → 내가 낮게 투찰 → too_low
        records = [
            _make_record(0.8850, 0.8900),  # diff = -0.005
            _make_record(0.8840, 0.8900),  # diff = -0.006
            _make_record(0.8850, 0.8910),  # diff = -0.006
            _make_record(0.8845, 0.8900),  # diff = -0.0055
            _make_record(0.8850, 0.8905),  # diff = -0.0055
        ]
        svc = DefeatAnalysisService(db=_make_db(records=records))
        result = svc.get_gap_distribution(user_id=1)

        assert result["consistent_direction"] == "too_low"
        assert result["win_if_lower_by"] is None
        assert result["mean_diff"] is not None
        assert result["mean_diff"] < 0
        assert result["total_analyzed"] == 5

    def test_buckets_structure(self):
        records = [
            _make_record(0.8900, 0.8850),
            _make_record(0.8905, 0.8855),
            _make_record(0.8800, 0.8820),  # diff = -0.002
        ]
        svc = DefeatAnalysisService(db=_make_db(records=records))
        result = svc.get_gap_distribution(user_id=1)

        for b in result["buckets"]:
            assert "range_lo" in b
            assert "range_hi" in b
            assert "count" in b
            assert b["count"] > 0
            assert round(b["range_hi"] - b["range_lo"], 4) == pytest.approx(0.005, abs=1e-4)

    def test_outlier_excluded(self):
        records = [
            _make_record(0.9500, 0.8900),  # diff = +0.060 → outlier (>5%)
            _make_record(0.8900, 0.8850),  # diff = +0.005 → 유효
        ]
        svc = DefeatAnalysisService(db=_make_db(records=records))
        result = svc.get_gap_distribution(user_id=1)

        # 아웃라이어 1건 제외 후 유효 1건
        assert result["total_analyzed"] == 1

    def test_personal_bias_included(self):
        svc = DefeatAnalysisService(db=_make_db(records=[]))
        result = svc.get_gap_distribution(user_id=42)

        bias = result["personal_bias"]
        assert "correction" in bias
        assert "direction" in bias
        assert "narrative" in bias
        assert "sample_count" in bias
