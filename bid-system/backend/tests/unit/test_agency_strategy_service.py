"""AgencyStrategyService unit tests"""
from __future__ import annotations

import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

for _mod in ("joblib", "lightgbm", "xgboost", "sklearn",
             "sklearn.cluster", "sklearn.preprocessing", "sklearn.impute"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest
import numpy as np
from app.services import AgencyStrategyService


# ── helpers ─────────────────────────────────────────────────────────────────

def _make_strategy_row(
    agency_id=1,
    industry_code="ALL",
    period_months=48,
    avg_win_rate=0.9009,
    p10=0.8900,
    p25=0.8950,
    p50=0.9010,
    p75=0.9050,
    p90=0.9100,
    total_bids=50,
    trend_direction="stable",
    aggression_index=0.12,
    volatility_30d=0.002,
    recommended_range_lo=0.8990,
    recommended_range_hi=0.9040,
    freq_table=None,
    histogram_data=None,
):
    row = MagicMock()
    row.agency_id = agency_id
    row.industry_code = industry_code
    row.period_months = period_months
    row.avg_win_rate = avg_win_rate
    row.p10_win_rate = p10
    row.p25_win_rate = p25
    row.p50_win_rate = p50
    row.p75_win_rate = p75
    row.p90_win_rate = p90
    row.total_bids = total_bids
    row.trend_direction = trend_direction
    row.aggression_index = aggression_index
    row.volatility_30d = volatility_30d
    row.recommended_range_lo = recommended_range_lo
    row.recommended_range_hi = recommended_range_hi
    row.freq_table = freq_table or []
    row.histogram_data = histogram_data or []
    row.avg_competitors = 8.5
    return row


def _db_with_strategy(row):
    """DB mock that returns `row` on agency_strategies query."""
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value.first.return_value = row
    db.query.return_value = q
    return db


def _db_without_strategy():
    """DB mock that returns None (no existing row)."""
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value.first.return_value = None
    db.query.return_value = q
    return db


# ── AgencyStrategyService.get ────────────────────────────────────────────────

class TestAgencyStrategyGet:
    def test_returns_serialized_dict_when_found(self):
        row = _make_strategy_row()
        svc = AgencyStrategyService(_db_with_strategy(row))
        result = svc.get(1)
        assert result is not None
        assert isinstance(result, dict)
        assert result["agency_id"] == 1

    def test_returns_none_when_not_found(self):
        svc = AgencyStrategyService(_db_without_strategy())
        result = svc.get(999)
        assert result is None

    def test_filters_by_industry_code(self):
        row = _make_strategy_row(industry_code="12345")
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.first.return_value = row
        db.query.return_value = q
        svc = AgencyStrategyService(db)
        result = svc.get(1, industry_code="12345")
        assert result is not None

    def test_filters_by_period_months(self):
        row = _make_strategy_row(period_months=12)
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.first.return_value = row
        db.query.return_value = q
        svc = AgencyStrategyService(db)
        result = svc.get(1, period_months=12)
        assert result is not None


# ── AgencyStrategyService.get_or_build ──────────────────────────────────────

class TestAgencyStrategyGetOrBuild:
    def test_returns_existing_without_build(self):
        row = _make_strategy_row()
        svc = AgencyStrategyService(_db_with_strategy(row))
        with patch.object(svc, "_build_one") as mock_build:
            result = svc.get_or_build(1)
            mock_build.assert_not_called()
        assert result["agency_id"] == 1

    def test_triggers_build_when_not_found(self):
        call_count = {"n": 0}
        row = _make_strategy_row()

        db = MagicMock()
        q = MagicMock()

        def first_side_effect():
            call_count["n"] += 1
            # 1st call: not found; 2nd call (after build): found
            return None if call_count["n"] == 1 else row

        q.filter.return_value.first.side_effect = first_side_effect
        db.query.return_value = q

        svc = AgencyStrategyService(db)
        with patch.object(svc, "_build_one") as mock_build:
            result = svc.get_or_build(1)
            mock_build.assert_called_once_with(1, "ALL", 48)
        assert result["agency_id"] == 1

    def test_returns_fallback_when_build_produces_nothing(self):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        db.query.return_value = q

        svc = AgencyStrategyService(db)
        with patch.object(svc, "_build_one"):
            result = svc.get_or_build(1)
        assert result["agency_id"] == 1
        assert result.get("total_bid_count") == 0 or "message" in result


# ── AgencyStrategyService._serialize ────────────────────────────────────────

class TestAgencyStrategySerialize:
    def test_serialize_includes_required_keys(self):
        row = _make_strategy_row(
            avg_win_rate=0.9009,
            p50=0.9010,
            trend_direction="up",
            recommended_range_lo=0.8990,
            recommended_range_hi=0.9040,
        )
        # add fields _serialize actually reads
        row.total_bid_count = 50
        row.std_win_rate = None
        row.min_win_rate = None
        row.max_win_rate = None
        row.win_rate_p10 = 0.88
        row.win_rate_p25 = 0.89
        row.win_rate_p50 = 0.90
        row.win_rate_p75 = 0.91
        row.win_rate_p90 = 0.92
        row.avg_competitor_cnt = 8.5
        row.qual_difficulty = None
        row.updated_at = None

        svc = AgencyStrategyService(MagicMock())
        result = svc._serialize(row)
        for key in ("agency_id", "avg_win_rate", "win_rate_p50",
                    "trend_direction", "recommended_range_lo",
                    "recommended_range_hi", "freq_table", "total_bid_count"):
            assert key in result, f"missing key: {key}"

    def test_serialize_trend_direction_values(self):
        for direction in ("up", "down", "stable"):
            row = _make_strategy_row(trend_direction=direction)
            svc = AgencyStrategyService(MagicMock())
            result = svc._serialize(row)
            assert result["trend_direction"] == direction

    def test_serialize_percentile_range(self):
        row = _make_strategy_row(p10=0.88, p90=0.92)
        row.total_bid_count = 50
        row.std_win_rate = None
        row.min_win_rate = None
        row.max_win_rate = None
        row.win_rate_p10 = 0.88
        row.win_rate_p25 = 0.89
        row.win_rate_p50 = 0.90
        row.win_rate_p75 = 0.91
        row.win_rate_p90 = 0.92
        row.avg_competitor_cnt = 8.5
        row.qual_difficulty = None
        row.updated_at = None

        svc = AgencyStrategyService(MagicMock())
        result = svc._serialize(row)
        assert result["win_rate_p10"] == pytest.approx(0.88)
        assert result["win_rate_p90"] == pytest.approx(0.92)


# ── AgencyStrategyService.rebuild_all ───────────────────────────────────────

class TestAgencyStrategyRebuildAll:
    def test_rebuild_all_returns_summary_keys(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = [(1,), (2,), (3,)]

        svc = AgencyStrategyService(db)
        with patch.object(svc, "_build_one"):
            result = svc.rebuild_all()

        assert "built" in result
        assert "skipped" in result
        assert "agencies" in result

    def test_rebuild_all_counts_correctly(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = [(1,), (2,), (3,)]

        svc = AgencyStrategyService(db)
        with patch.object(svc, "_build_one"):
            result = svc.rebuild_all()

        assert result["built"] == 3
        assert result["skipped"] == 0
        assert result["agencies"] == 3

    def test_rebuild_all_counts_skipped_on_exception(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = [(1,), (2,), (3,)]

        svc = AgencyStrategyService(db)
        with patch.object(svc, "_build_one", side_effect=[None, RuntimeError("fail"), None]):
            result = svc.rebuild_all()

        assert result["built"] == 2
        assert result["skipped"] == 1

    def test_rebuild_all_skips_all_on_exception(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = [(1,), (2,)]

        svc = AgencyStrategyService(db)
        with patch.object(svc, "_build_one", side_effect=RuntimeError("fail")):
            result = svc.rebuild_all()

        assert result["built"] == 0
        assert result["skipped"] == 2

    def test_rebuild_all_empty_agencies(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []

        svc = AgencyStrategyService(db)
        result = svc.rebuild_all()

        assert result["built"] == 0
        assert result["agencies"] == 0
