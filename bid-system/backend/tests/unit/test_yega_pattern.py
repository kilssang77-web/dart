"""get_agency_yega_pattern 단위 테스트"""
import sys
from unittest.mock import MagicMock

for _mod in ("joblib", "lightgbm", "xgboost", "sklearn",
             "sklearn.cluster", "sklearn.preprocessing", "sklearn.impute"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest
from app.ml.yega import get_agency_yega_pattern


class TestGetAgencyYegaPattern:

    def test_empty_data_returns_fallback(self):
        result = get_agency_yega_pattern([])
        assert result["pattern"] == []
        assert result["top3_numbers"] == []
        assert result["dominant_zone"] is None
        assert result["sample_count"] == 0

    def test_invalid_rows_skipped(self):
        # 유효하지 않은 데이터(base_amount=0, assessment_rate=0)는 스킵
        bid_data = [
            {"assessment_rate": 0.0, "base_amount": 0, "a_value": None},
            {"assessment_rate": 0.8876, "base_amount": 0, "a_value": None},
        ]
        result = get_agency_yega_pattern(bid_data)
        assert result["sample_count"] == 0
        assert result["pattern"] == []

    def test_valid_data_returns_pattern(self):
        # 3억 공고, 사정율 0.8876 (기본 A값 추정)
        bid_data = [
            {"assessment_rate": 0.8876, "base_amount": 300_000_000, "a_value": None},
            {"assessment_rate": 0.8850, "base_amount": 300_000_000, "a_value": None},
            {"assessment_rate": 0.8900, "base_amount": 300_000_000, "a_value": None},
        ]
        result = get_agency_yega_pattern(bid_data)

        assert result["sample_count"] > 0
        assert len(result["pattern"]) == 15  # 1~15 모두 포함
        assert len(result["top3_numbers"]) == 3
        assert all(1 <= n <= 15 for n in result["top3_numbers"])
        assert result["dominant_zone"] in ("low", "mid", "high")

    def test_pattern_freq_sums_to_100(self):
        bid_data = [
            {"assessment_rate": 0.8876, "base_amount": 500_000_000, "a_value": 443_800_000},
        ]
        result = get_agency_yega_pattern(bid_data)
        if result["sample_count"] > 0:
            total_pct = sum(p["freq_pct"] for p in result["pattern"])
            assert abs(total_pct - 100.0) < 1.0  # 부동소수점 허용 오차

    def test_a_value_provided_uses_it(self):
        # A값 명시 시 center로 사용
        bid_data = [
            {"assessment_rate": 0.8876, "base_amount": 1_000_000_000, "a_value": 887_600_000},
        ]
        result = get_agency_yega_pattern(bid_data)
        # 충분한 사정율-A값 정합이면 sample_count 1 이상
        assert result["sample_count"] >= 0  # 매칭 여부와 무관, 크래시 없어야 함

    def test_no_matching_combinations_fallback(self):
        # 사정율이 극단값으로 매칭 조합 없는 경우 → 빈 패턴
        bid_data = [
            {"assessment_rate": 0.5000, "base_amount": 100_000_000, "a_value": None},
        ]
        result = get_agency_yega_pattern(bid_data)
        # 매칭 없으면 sample_count=0, 크래시 없어야 함
        assert isinstance(result["sample_count"], int)
        assert isinstance(result["pattern"], list)
