"""WinPatternService 단위 테스트"""
import sys
from datetime import date
from unittest.mock import MagicMock

for _mod in ("joblib", "lightgbm", "xgboost", "sklearn",
             "sklearn.cluster", "sklearn.preprocessing", "sklearn.impute"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest
from app.services import WinPatternService


def _make_record(
    result: str,
    submitted_rate: float,
    actual_winner_rate: float | None = None,
    agency_name: str | None = "기관A",
    bid_date: date | None = None,
    bid_id: int | None = None,
    rate_diff: float | None = None,
):
    rec = MagicMock()
    rec.result = result
    rec.submitted_rate = submitted_rate
    rec.actual_winner_rate = actual_winner_rate
    rec.agency_name = agency_name
    rec.bid_date = bid_date or date(2024, 6, 1)
    rec.bid_id = bid_id
    rec.rate_diff = rate_diff
    return rec


def _svc_with_records(records, total=None):
    """DB 모킹: db.query(M).filter(...).count() / .all()"""
    db = MagicMock()
    db.query.return_value.filter.return_value.count.return_value = (
        total if total is not None else len(records)
    )
    db.query.return_value.filter.return_value.all.return_value = records
    return WinPatternService(db)


class TestWinPatternBias:

    def test_above_bias_detected(self):
        records = [
            _make_record("lost", 0.8950, 0.8900),  # diff=+0.005
            _make_record("lost", 0.8950, 0.8900),  # diff=+0.005
            _make_record("lost", 0.8950, 0.8900),  # diff=+0.005
            _make_record("won",  0.8900, 0.8900),   # diff=0
        ]
        svc = _svc_with_records(records, total=4)
        result = svc.analyze(user_id=1)

        assert result["bias"]["direction"] == "above"
        assert result["bias"]["rate_diff_mean"] is not None
        assert result["bias"]["rate_diff_mean"] > WinPatternService.BIAS_THRESHOLD
        assert "높게" in result["bias"]["signal"]
        assert "낮게 조정" in result["bias"]["signal"]

    def test_below_bias_detected(self):
        records = [
            _make_record("lost", 0.8850, 0.8900),  # diff=-0.005
            _make_record("lost", 0.8840, 0.8900),  # diff=-0.006
            _make_record("lost", 0.8845, 0.8895),  # diff=-0.005
        ]
        svc = _svc_with_records(records, total=3)
        result = svc.analyze(user_id=1)

        assert result["bias"]["direction"] == "below"
        assert result["bias"]["rate_diff_mean"] < -WinPatternService.BIAS_THRESHOLD
        assert "낮게" in result["bias"]["signal"]

    def test_balanced_no_bias(self):
        records = [
            _make_record("lost", 0.8901, 0.8900),  # diff=+0.0001
            _make_record("lost", 0.8899, 0.8900),  # diff=-0.0001
        ]
        svc = _svc_with_records(records, total=2)
        result = svc.analyze(user_id=1)

        assert result["bias"]["rate_diff_mean"] is not None
        assert abs(result["bias"]["rate_diff_mean"]) <= WinPatternService.BIAS_THRESHOLD
        assert "편향 없음" in result["bias"]["signal"]

    def test_no_records_returns_balanced(self):
        svc = _svc_with_records([], total=0)
        result = svc.analyze(user_id=1)

        assert result["bias"]["rate_diff_mean"] is None
        assert result["bias"]["direction"] == "balanced"


class TestWinPatternStats:

    def test_overall_win_rate(self):
        records = [
            _make_record("won",  0.89, 0.89),
            _make_record("lost", 0.89, 0.87),
            _make_record("lost", 0.89, 0.87),
            _make_record("lost", 0.89, 0.87),
        ]
        svc = _svc_with_records(records, total=10)
        result = svc.analyze(user_id=1)

        assert result["total"] == 10
        assert result["won"] == 1
        assert result["lost"] == 3
        assert abs(result["overall_win_rate"] - 25.0) < 0.1

    def test_response_keys_present(self):
        svc = _svc_with_records([], total=0)
        result = svc.analyze(user_id=1)

        for key in ("total", "won", "lost", "overall_win_rate", "bias",
                    "by_agency", "by_industry", "by_year", "loss_reasons"):
            assert key in result

    def test_loss_reasons_keys(self):
        svc = _svc_with_records([], total=0)
        result = svc.analyze(user_id=1)

        for key in ("above_winner", "below_floor", "below_winner"):
            assert key in result["loss_reasons"]


class TestLossReasons:

    def test_above_winner_counted(self):
        records = [
            _make_record("lost", 0.8910, 0.8870),  # diff=+0.004 → above
            _make_record("lost", 0.8910, 0.8870),  # diff=+0.004 → above
            _make_record("lost", 0.8850, 0.8900),  # diff=-0.005 → below_winner
        ]
        svc = _svc_with_records(records, total=3)
        result = svc.analyze(user_id=1)

        assert result["loss_reasons"]["above_winner"] == 2
        assert result["loss_reasons"]["below_winner"] == 1
        assert result["loss_reasons"]["below_floor"] == 0

    def test_null_actual_winner_rate_skipped(self):
        rec = _make_record("lost", 0.89, None)
        svc = _svc_with_records([rec], total=1)
        result = svc.analyze(user_id=1)

        total_loss = sum(result["loss_reasons"].values())
        assert total_loss == 0


class TestByAgency:

    def test_by_agency_groups_correctly(self):
        records = [
            _make_record("won",  0.89, 0.89, agency_name="기관A"),
            _make_record("lost", 0.89, 0.87, agency_name="기관A"),
            _make_record("lost", 0.89, 0.87, agency_name="기관B"),
        ]
        svc = _svc_with_records(records, total=3)
        result = svc.analyze(user_id=1)

        by_agency = {a["agency_name"]: a for a in result["by_agency"]}
        assert "기관A" in by_agency
        assert by_agency["기관A"]["total"] == 2
        assert by_agency["기관A"]["won"] == 1
        assert abs(by_agency["기관A"]["win_rate"] - 50.0) < 0.1

    def test_agency_without_name_excluded(self):
        records = [
            _make_record("lost", 0.89, 0.87, agency_name=None),
        ]
        svc = _svc_with_records(records, total=1)
        result = svc.analyze(user_id=1)

        assert result["by_agency"] == []


class TestByYear:

    def test_by_year_sorted(self):
        records = [
            _make_record("lost", 0.89, 0.87, bid_date=date(2023, 3, 1)),
            _make_record("lost", 0.89, 0.87, bid_date=date(2022, 6, 1)),
            _make_record("won",  0.89, 0.89, bid_date=date(2023, 9, 1)),
        ]
        svc = _svc_with_records(records, total=3)
        result = svc.analyze(user_id=1)

        years = [y["year"] for y in result["by_year"]]
        assert years == sorted(years)

    def test_by_year_win_rate(self):
        records = [
            _make_record("won",  0.89, 0.89, bid_date=date(2024, 1, 1)),
            _make_record("won",  0.89, 0.89, bid_date=date(2024, 2, 1)),
            _make_record("lost", 0.89, 0.87, bid_date=date(2024, 3, 1)),
            _make_record("lost", 0.89, 0.87, bid_date=date(2024, 4, 1)),
        ]
        svc = _svc_with_records(records, total=4)
        result = svc.analyze(user_id=1)

        by_year = {y["year"]: y for y in result["by_year"]}
        assert abs(by_year[2024]["win_rate"] - 50.0) < 0.1
