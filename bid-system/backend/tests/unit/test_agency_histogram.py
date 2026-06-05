"""AgencyAnalysisService.srate_histogram / recent_results unit tests"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

for _mod in ("joblib", "lightgbm", "xgboost", "sklearn",
             "sklearn.cluster", "sklearn.preprocessing", "sklearn.impute"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest
from app.services import AgencyAnalysisService


def _mock_agency(agency_id: int = 1, name: str = "TestAgency"):
    a = MagicMock()
    a.id = agency_id
    a.name = name
    return a


def _mock_bid(bid_id: int, open_date: datetime = datetime(2026, 1, 15)):
    b = MagicMock()
    b.id = bid_id
    b.title = f"Bid{bid_id}"
    b.base_amount = Decimal("100000000")
    b.bid_open_date = open_date
    return b


def _mock_result(bid_id: int, assessment_rate: float, is_winner: bool = True):
    r = MagicMock()
    r.bid_id = bid_id
    r.assessment_rate = Decimal(str(assessment_rate))
    r.is_winner = is_winner
    return r


def _flexible_query_db(agency, bids, results, comp_count=3):
    from app.models import Agency, Bid, BidResult

    def query_fn(*args):
        model = args[0] if args else None
        q = MagicMock()

        if model is Agency:
            q.filter.return_value.first.return_value = agency
        elif model is Bid:
            fq = MagicMock()
            fq.all.return_value = bids
            fq.order_by.return_value.limit.return_value.all.return_value = bids
            q.filter.return_value = fq
        elif model is BidResult:
            fq = MagicMock()
            fq.all.return_value = results
            fq.first.return_value = results[0] if results else None
            fq.scalar.return_value = comp_count
            q.filter.return_value = fq
        else:
            fq = MagicMock()
            fq.scalar.return_value = comp_count
            q.filter.return_value = fq

        return q

    db = MagicMock()
    db.query.side_effect = query_fn
    return db


class TestSrateHistogram:
    def _build_svc(self, srate_values: list):
        agency = _mock_agency()
        bids = [_mock_bid(i + 1) for i in range(len(srate_values))]
        results = [_mock_result(i + 1, v) for i, v in enumerate(srate_values)]
        db = _flexible_query_db(agency, bids, results)
        return AgencyAnalysisService(db)

    def test_returns_expected_keys(self):
        svc = self._build_svc([0.885, 0.888, 0.890])
        result = svc.srate_histogram(1, months=12)
        for key in ("agency_id", "bins", "percentiles", "mean", "std", "sample_count"):
            assert key in result

    def test_bins_cover_floor_rate(self):
        svc = self._build_svc([0.885, 0.888, 0.890])
        result = svc.srate_histogram(1, months=12)
        floor = 0.87745
        bins = result["bins"]
        assert any(b["range_lo"] <= floor < b["range_hi"] for b in bins)

    def test_sample_count_matches(self):
        svc = self._build_svc([0.880, 0.885, 0.890, 0.895])
        result = svc.srate_histogram(1, months=12)
        assert result["sample_count"] == 4

    def test_percentiles_present(self):
        svc = self._build_svc([0.880, 0.885, 0.890, 0.895, 0.900])
        result = svc.srate_histogram(1, months=12)
        for key in ("p10", "p25", "p50", "p75", "p90"):
            assert key in result["percentiles"]
            assert result["percentiles"][key] is not None

    def test_empty_data_returns_zeros(self):
        svc = self._build_svc([])
        result = svc.srate_histogram(1, months=12)
        assert result["sample_count"] == 0
        assert result["mean"] is None
        assert result["std"] is None

    def test_bin_width_is_0_005(self):
        svc = self._build_svc([0.885])
        result = svc.srate_histogram(1, months=12)
        bin0 = result["bins"][0]
        assert abs((bin0["range_hi"] - bin0["range_lo"]) - 0.005) < 1e-9

    def test_not_found_raises_404(self):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        db.query.return_value = q
        svc = AgencyAnalysisService(db)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            svc.srate_histogram(999, months=12)
        assert exc.value.status_code == 404


class TestRecentResults:
    def test_returns_expected_keys(self):
        agency = _mock_agency()
        bids = [_mock_bid(1, datetime(2026, 5, 1))]
        results = [_mock_result(1, 0.888)]
        db = _flexible_query_db(agency, bids, results)
        svc = AgencyAnalysisService(db)
        result = svc.recent_results(1, limit=10)
        assert "items" in result
        assert "total" in result

    def test_respects_limit(self):
        agency = _mock_agency()
        base_date = datetime(2026, 5, 1)
        bids = [_mock_bid(i + 1, base_date - timedelta(days=30 * i)) for i in range(10)]
        results = [_mock_result(i + 1, 0.888) for i in range(10)]
        db = _flexible_query_db(agency, bids, results)
        svc = AgencyAnalysisService(db)
        result = svc.recent_results(1, limit=5)
        assert result["total"] <= 5

    def test_not_found_raises_404(self):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        db.query.return_value = q
        svc = AgencyAnalysisService(db)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            svc.recent_results(999, limit=10)
        assert exc.value.status_code == 404