"""CompetitorPredictService + predict_participation/predict_bid_zone unit tests"""
import sys
from unittest.mock import MagicMock

for _mod in ("joblib", "lightgbm", "xgboost", "sklearn",
             "sklearn.cluster", "sklearn.preprocessing", "sklearn.impute"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest


class TestPredictParticipation:

    def _db(self, total: int, participated: int):
        row = MagicMock()
        row.__getitem__ = lambda self, i: [total, participated][i]
        row.__bool__ = lambda self: True
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = row
        db.execute.return_value.scalar.return_value = 1
        return db

    def test_agency_and_industry_match(self):
        from app.ml.competitor_predict import predict_participation
        db = self._db(total=10, participated=4)
        result = predict_participation(
            competitor_id=1,
            bid={"agency_id": 10, "industry_id": 5, "base_amount": 5_000_000},
            db=db,
        )
        assert 0.0 <= result["probability"] <= 1.0
        assert "confidence" in result
        assert "basis" in result

    def test_probability_calculation(self):
        from app.ml.competitor_predict import predict_participation
        db = self._db(total=20, participated=10)
        result = predict_participation(
            competitor_id=1,
            bid={"agency_id": 10, "industry_id": None, "base_amount": 100},
            db=db,
        )
        assert result["probability"] == pytest.approx(0.5, abs=0.01)

    def test_confidence_high_when_large_sample(self):
        from app.ml.competitor_predict import predict_participation
        db = self._db(total=30, participated=15)
        result = predict_participation(
            competitor_id=1,
            bid={"agency_id": 10, "industry_id": 5, "base_amount": 100},
            db=db,
        )
        assert result["confidence"] == "high"

    def test_confidence_medium_when_mid_sample(self):
        from app.ml.competitor_predict import predict_participation
        db = self._db(total=8, participated=4)
        result = predict_participation(
            competitor_id=1,
            bid={"agency_id": 10, "industry_id": 5, "base_amount": 100},
            db=db,
        )
        assert result["confidence"] == "medium"

    def test_confidence_low_when_small_sample(self):
        from app.ml.competitor_predict import predict_participation
        db = self._db(total=3, participated=1)
        result = predict_participation(
            competitor_id=1,
            bid={"agency_id": 10, "industry_id": 5, "base_amount": 100},
            db=db,
        )
        assert result["confidence"] == "low"

    def test_fallback_when_no_agency_id(self):
        from app.ml.competitor_predict import predict_participation
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = MagicMock(
            __getitem__=lambda self, i: 5
        )
        db.execute.return_value.scalar.return_value = 100
        result = predict_participation(
            competitor_id=1,
            bid={"agency_id": None, "industry_id": None, "base_amount": 100},
            db=db,
        )
        assert result["confidence"] == "low"

    def test_probability_capped_at_1(self):
        from app.ml.competitor_predict import predict_participation
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = MagicMock(
            __getitem__=lambda self, i: 500
        )
        db.execute.return_value.scalar.return_value = 10
        result = predict_participation(
            competitor_id=1,
            bid={"agency_id": None, "industry_id": None, "base_amount": 100},
            db=db,
        )
        assert result["probability"] <= 1.0


class TestPredictBidZone:

    def _make_db(self, competitor=None, rows=None):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = competitor
        db.execute.return_value.fetchall.return_value = rows or []
        return db

    def test_empty_when_no_competitor(self):
        from app.ml.competitor_predict import predict_bid_zone
        db = self._make_db(competitor=None)
        result = predict_bid_zone(competitor_id=999, base_amount=5_000_000, db=db)
        assert result["zones"] == []
        assert result["peak_zone"] is None
        assert result["sample_count"] == 0

    def test_empty_when_no_biz_reg_no(self):
        from app.ml.competitor_predict import predict_bid_zone
        c = MagicMock()
        c.biz_reg_no = None
        db = self._make_db(competitor=c)
        result = predict_bid_zone(competitor_id=1, base_amount=5_000_000, db=db)
        assert result["zones"] == []

    def test_empty_when_no_inpo21c_data(self):
        from app.ml.competitor_predict import predict_bid_zone
        c = MagicMock()
        c.biz_reg_no = "123-45-67890"
        db = self._make_db(competitor=c, rows=[])
        result = predict_bid_zone(competitor_id=1, base_amount=5_000_000, db=db)
        assert result["zones"] == []
        assert result["sample_count"] == 0

    def test_zones_bucketed_correctly(self):
        from app.ml.competitor_predict import predict_bid_zone
        c = MagicMock()
        c.biz_reg_no = "111-22-33333"
        rows = [(0.870,), (0.870,), (0.875,), (0.880,), (0.890,),
                (0.890,), (0.900,), (0.900,), (0.900,), (0.910,)]
        db = self._make_db(competitor=c, rows=rows)
        result = predict_bid_zone(competitor_id=1, base_amount=5_000_000, db=db)
        assert result["sample_count"] == 10
        assert len(result["zones"]) > 0
        total_pct = sum(z["pct"] for z in result["zones"])
        assert abs(total_pct - 100.0) < 0.6

    def test_peak_zone_is_highest_pct(self):
        from app.ml.competitor_predict import predict_bid_zone
        c = MagicMock()
        c.biz_reg_no = "111-22-33333"
        rows = [(0.900,)] * 6 + [(0.870,)] * 2 + [(0.880,)] * 2
        db = self._make_db(competitor=c, rows=rows)
        result = predict_bid_zone(competitor_id=1, base_amount=5_000_000, db=db)
        assert result["peak_zone"] is not None
        assert result["peak_zone"]["range_lo"] == pytest.approx(0.900)

    def test_zones_have_required_fields(self):
        from app.ml.competitor_predict import predict_bid_zone
        c = MagicMock()
        c.biz_reg_no = "999-88-77777"
        rows = [(0.900,), (0.905,), (0.905,)]
        db = self._make_db(competitor=c, rows=rows)
        result = predict_bid_zone(competitor_id=1, base_amount=5_000_000, db=db)
        for z in result["zones"]:
            assert "range_lo" in z
            assert "range_hi" in z
            assert "pct" in z
            assert z["range_hi"] == pytest.approx(z["range_lo"] + 0.005, abs=0.001)


class TestCompetitorPredictService:

    def _setup(self, bid_base_amount=5_000_000):
        competitor = MagicMock()
        competitor.id = 1
        competitor.name = "TestCompany"
        competitor.biz_reg_no = "123-45-67890"

        bid = MagicMock()
        bid.id = 100
        bid.agency_id = 10
        bid.industry_id = 5
        bid.base_amount = bid_base_amount

        db = MagicMock()
        # service: competitor, bid / predict_bid_zone: competitor again
        db.query.return_value.filter.return_value.first.side_effect = [competitor, bid, competitor]
        db.execute.return_value.fetchone.return_value = MagicMock(
            __getitem__=lambda self, i: [5, 2][i]
        )
        db.execute.return_value.fetchall.return_value = [(0.900,)] * 3
        db.execute.return_value.scalar.return_value = 100
        return db, competitor, bid

    def test_returns_required_fields(self):
        from app.services import CompetitorPredictService
        db, _, _ = self._setup()
        svc = CompetitorPredictService()
        result = svc.predict(db, competitor_id=1, bid_id=100)
        assert result["competitor_id"] == 1
        assert result["competitor_name"] == "TestCompany"
        assert result["bid_id"] == 100
        assert "participation" in result
        assert "bid_zone" in result

    def test_raises_404_when_competitor_missing(self):
        from fastapi import HTTPException
        from app.services import CompetitorPredictService
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        svc = CompetitorPredictService()
        with pytest.raises(HTTPException) as exc_info:
            svc.predict(db, competitor_id=999, bid_id=1)
        assert exc_info.value.status_code == 404

    def test_raises_404_when_bid_missing(self):
        from fastapi import HTTPException
        from app.services import CompetitorPredictService
        competitor = MagicMock()
        competitor.name = "Co"
        db = MagicMock()
        db.query.return_value.filter.return_value.first.side_effect = [competitor, None]
        svc = CompetitorPredictService()
        with pytest.raises(HTTPException) as exc_info:
            svc.predict(db, competitor_id=1, bid_id=999)
        assert exc_info.value.status_code == 404