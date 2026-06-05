"""SrateTrendService 단위 테스트 — 상승/하락/안정 3케이스"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

# ML 라이브러리 미설치 환경 대응 — services.py 임포트 전에 반드시 선행
for _mod in ("joblib", "lightgbm", "xgboost", "sklearn",
             "sklearn.cluster", "sklearn.preprocessing", "sklearn.impute"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from datetime import datetime

import pytest

from app.services import SrateTrendService

svc = SrateTrendService()
FIXED_NOW = datetime(2026, 6, 5)


def _rows(prev_mean: float, recent_mean: float, count: int = 100) -> list:
    """최근 3개월(Apr-Jun 2026) vs 이전 3개월(Jan-Mar 2026) 가상 데이터."""
    return [
        # 이전 3개월 (months_ago 3, 4, 5)
        {"period_year": 2026, "period_month": 1, "srate_mean": prev_mean, "sample_count": count},
        {"period_year": 2026, "period_month": 2, "srate_mean": prev_mean, "sample_count": count},
        {"period_year": 2026, "period_month": 3, "srate_mean": prev_mean, "sample_count": count},
        # 최근 3개월 (months_ago 0, 1, 2)
        {"period_year": 2026, "period_month": 4, "srate_mean": recent_mean, "sample_count": count},
        {"period_year": 2026, "period_month": 5, "srate_mean": recent_mean, "sample_count": count},
        {"period_year": 2026, "period_month": 6, "srate_mean": recent_mean, "sample_count": count},
    ]


class TestBuildResult:
    def test_up(self):
        result = svc._build_result(_rows(0.885, 0.890), FIXED_NOW)
        assert result["direction"] == "up"
        assert result["delta"] > SrateTrendService.THRESHOLD
        assert "상승" in result["signal"]
        assert result["recent_mean"] == pytest.approx(0.890, abs=1e-4)
        assert result["prev_mean"] == pytest.approx(0.885, abs=1e-4)

    def test_down(self):
        result = svc._build_result(_rows(0.890, 0.885), FIXED_NOW)
        assert result["direction"] == "down"
        assert result["delta"] < -SrateTrendService.THRESHOLD
        assert "하락" in result["signal"]

    def test_stable(self):
        result = svc._build_result(_rows(0.887, 0.8874), FIXED_NOW)
        assert result["direction"] == "stable"
        assert abs(result["delta"]) < SrateTrendService.THRESHOLD

    def test_empty_rows(self):
        result = svc._build_result([], FIXED_NOW)
        assert result["direction"] == "stable"
        assert result["sample_count"] == 0

    def test_weighted_average(self):
        rows = [
            {"period_year": 2026, "period_month": 3, "srate_mean": 0.880, "sample_count": 200},
            {"period_year": 2026, "period_month": 3, "srate_mean": 0.890, "sample_count": 0},
            {"period_year": 2026, "period_month": 5, "srate_mean": 0.895, "sample_count": 100},
            {"period_year": 2026, "period_month": 6, "srate_mean": 0.895, "sample_count": 100},
        ]
        result = svc._build_result(rows, FIXED_NOW)
        # prev: only month 3 with count=200 (count=0 row ignored in weighted avg)
        assert result["prev_mean"] == pytest.approx(0.880, abs=1e-4)
        assert result["direction"] == "up"


def _make_mock_db(rows_as_tuples):
    db = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = rows_as_tuples
    db.execute.return_value = mock_result
    return db


class TestGetTrend:
    def test_uses_assessment_stats(self):
        db = _make_mock_db([
            (2026, 1, 0.885, 100),
            (2026, 2, 0.885, 100),
            (2026, 3, 0.885, 100),
            (2026, 4, 0.892, 100),
            (2026, 5, 0.892, 100),
            (2026, 6, 0.892, 100),
        ])
        result = svc.get_trend(db, agency_id=1, industry_id=None)
        assert result["direction"] == "up"

    def test_fallback_to_bid_results(self):
        """assessment_rate_stats 비어있으면 bid_results 폴백."""
        call_count = 0
        empty_result = MagicMock()
        empty_result.fetchall.return_value = []
        fallback_result = MagicMock()
        fallback_result.fetchall.return_value = [
            (2026, 1, 0.890, 50),
            (2026, 2, 0.890, 50),
            (2026, 3, 0.890, 50),
            (2026, 4, 0.884, 50),
            (2026, 5, 0.884, 50),
            (2026, 6, 0.884, 50),
        ]

        db = MagicMock()
        db.execute.side_effect = [empty_result, fallback_result]

        result = svc.get_trend(db, agency_id=1, industry_id=None)
        assert result["direction"] == "down"
