"""OpportunityScoreService.get_top_recommended 단위 테스트"""
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

for _mod in ("joblib", "lightgbm", "xgboost", "sklearn",
             "sklearn.cluster", "sklearn.preprocessing", "sklearn.impute"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest
from app.services import OpportunityScoreService


def _make_bid(bid_id: int, title: str, base_amount: int = 100_000_000,
              bid_open_date: datetime = None, agency_name: str = "테스트발주처") -> MagicMock:
    bid = MagicMock()
    bid.id = bid_id
    bid.title = title
    bid.base_amount = base_amount
    bid.bid_open_date = bid_open_date or (datetime.now() + timedelta(days=3))
    agency = MagicMock()
    agency.name = agency_name
    bid.agency = agency
    return bid


def _make_db_with_bids(bids: list) -> MagicMock:
    db = MagicMock()
    # IndustryFilter 쿼리: 필터 없음(전체 허용)
    industry_filter_query = MagicMock()
    industry_filter_query.all.return_value = []

    # Bid 쿼리 체인
    bid_query = MagicMock()
    bid_query.filter.return_value = bid_query
    bid_query.all.return_value = bids

    def query_side_effect(model):
        from app.models import IndustryFilter
        if model is IndustryFilter:
            return industry_filter_query
        return bid_query

    db.query.side_effect = query_side_effect
    return db


class TestGetTopRecommended:

    def test_empty_db_returns_empty_list(self):
        db = _make_db_with_bids([])
        svc = OpportunityScoreService(db)
        result = svc.get_top_recommended(user_id=1)
        assert result == []

    def test_normal_case_returns_sorted_by_score(self):
        bids = [
            _make_bid(1, "공고A", base_amount=50_000_000),
            _make_bid(2, "공고B", base_amount=200_000_000),
            _make_bid(3, "공고C", base_amount=100_000_000),
        ]
        db = _make_db_with_bids(bids)
        svc = OpportunityScoreService(db)

        scores = {1: 45.0, 2: 80.0, 3: 60.0}

        def mock_score(bid_id: int, user_id: int) -> dict:
            return {
                "bid_id": bid_id,
                "score": scores[bid_id],
                "grade": "A" if scores[bid_id] >= 75 else "B",
                "breakdown": {
                    "competition":    {"pts": 30, "max": 40, "note": "테스트"},
                    "personal_track": {"pts": 20, "max": 30, "note": "테스트"},
                    "market_trend":   {"pts": 10, "max": 15, "note": "테스트"},
                    "amount_fit":     {"pts": 15, "max": 15, "note": "테스트"},
                },
            }

        with patch.object(svc, "score", side_effect=mock_score):
            result = svc.get_top_recommended(user_id=1, limit=5)

        assert len(result) == 3
        assert result[0]["bid_id"] == 2  # score 80
        assert result[1]["bid_id"] == 3  # score 60
        assert result[2]["bid_id"] == 1  # score 45

    def test_limit_respected(self):
        bids = [_make_bid(i, f"공고{i}") for i in range(1, 8)]
        db = _make_db_with_bids(bids)
        svc = OpportunityScoreService(db)

        def mock_score(bid_id: int, user_id: int) -> dict:
            return {"bid_id": bid_id, "score": float(bid_id * 10), "grade": "B", "breakdown": None}

        with patch.object(svc, "score", side_effect=mock_score):
            result = svc.get_top_recommended(user_id=1, limit=3)

        assert len(result) == 3

    def test_error_scored_bids_excluded(self):
        bids = [
            _make_bid(1, "정상공고"),
            _make_bid(2, "오류공고"),
        ]
        db = _make_db_with_bids(bids)
        svc = OpportunityScoreService(db)

        def mock_score(bid_id: int, user_id: int) -> dict:
            if bid_id == 2:
                return {"error": "공고를 찾을 수 없습니다."}
            return {"bid_id": bid_id, "score": 70.0, "grade": "B", "breakdown": None}

        with patch.object(svc, "score", side_effect=mock_score):
            result = svc.get_top_recommended(user_id=1)

        assert len(result) == 1
        assert result[0]["bid_id"] == 1
