"""JointQualService.find_matching_partners 단위 테스트"""
import sys
from unittest.mock import MagicMock

# ML 라이브러리 미설치 환경 대응
for _mod in ("joblib", "lightgbm", "xgboost", "sklearn",
             "sklearn.cluster", "sklearn.preprocessing", "sklearn.impute"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest
from app.services import JointQualService


def _make_bid(bid_id=1, base_amount=500_000_000, min_bid_rate=0.87745, title="테스트 공고"):
    bid = MagicMock()
    bid.id = bid_id
    bid.title = title
    bid.base_amount = base_amount
    bid.min_bid_rate = min_bid_rate
    bid.license_codes = ["10000"]
    return bid


def _make_competitor(cid, name, biz_reg_no=None):
    c = MagicMock()
    c.id = cid
    c.name = name
    c.biz_reg_no = biz_reg_no or f"123-45-{cid:05d}"
    return c


def _make_stats(total_bids, win_count, avg_rate=0.885):
    s = MagicMock()
    s.total_bids = total_bids
    s.win_count = win_count
    s.avg_rate = avg_rate
    return s


def _make_db(bid=None, competitor_rows=None):
    db = MagicMock()

    # Bid query
    bid_mock = bid or _make_bid()
    db.query.return_value.filter.return_value.first.return_value = bid_mock

    # CompetitorStat subquery + Competitor join
    rows = competitor_rows if competitor_rows is not None else []
    (
        db.query.return_value
        .filter.return_value
        .group_by.return_value
        .subquery.return_value
    )
    (
        db.query.return_value
        .outerjoin.return_value
        .limit.return_value
        .all.return_value
    ) = rows

    return db


class TestFindMatchingPartners:

    def test_returns_empty_when_no_competitors(self):
        bid = _make_bid()
        db = MagicMock()
        # Bid 조회 성공
        db.query.return_value.filter.return_value.first.return_value = bid
        # 경쟁사 목록 없음
        db.query.return_value.outerjoin.return_value.limit.return_value.all.return_value = []

        svc = JointQualService(db=db)
        result = svc.find_matching_partners(bid_id=1, user_track_amount=0, participation_rate=0.6)

        assert result["partners"] == []
        assert result["bid_title"] == bid.title
        assert result["base_amount"] == bid.base_amount
        assert "threshold_note" in result

    def test_returns_partners_with_correct_structure(self):
        bid = _make_bid(base_amount=300_000_000)
        competitor = _make_competitor(cid=10, name="(주)테스트건설")
        stats = _make_stats(total_bids=20, win_count=5, avg_rate=0.882)
        rows = [(competitor, stats)]

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = bid
        db.query.return_value.outerjoin.return_value.limit.return_value.all.return_value = rows

        svc = JointQualService(db=db)
        result = svc.find_matching_partners(bid_id=1, user_track_amount=100_000_000, participation_rate=0.6)

        assert len(result["partners"]) == 1
        p = result["partners"][0]
        assert p["competitor_id"] == 10
        assert p["name"] == "(주)테스트건설"
        assert p["qualification_ok"] is True   # win_count=5, total_bids=20 → 적격
        assert p["joint_min_rate"] == pytest.approx(0.40, abs=0.01)  # 1 - 0.6 = 0.4
        assert p["win_rate"] == pytest.approx(0.25, abs=0.01)        # 5/20
        assert p["total_bids"] == 20
        assert p["compat_score"] > 0

    def test_qualification_ok_false_when_no_win(self):
        bid = _make_bid()
        competitor = _make_competitor(cid=20, name="신생업체")
        stats = _make_stats(total_bids=2, win_count=0, avg_rate=0.88)
        rows = [(competitor, stats)]

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = bid
        db.query.return_value.outerjoin.return_value.limit.return_value.all.return_value = rows

        svc = JointQualService(db=db)
        result = svc.find_matching_partners(bid_id=1, user_track_amount=0, participation_rate=0.5)

        p = result["partners"][0]
        assert p["qualification_ok"] is False

    def test_partner_rate_minimum_30pct(self):
        """참여지분율 80%로도 파트너 최소 지분은 30% 이상."""
        bid = _make_bid()
        competitor = _make_competitor(cid=30, name="협력사")
        stats = _make_stats(total_bids=10, win_count=3)
        rows = [(competitor, stats)]

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = bid
        db.query.return_value.outerjoin.return_value.limit.return_value.all.return_value = rows

        svc = JointQualService(db=db)
        result = svc.find_matching_partners(bid_id=1, user_track_amount=0, participation_rate=0.8)

        p = result["partners"][0]
        assert p["joint_min_rate"] >= 0.30   # 최소 30% 보장

    def test_sorted_qualified_first(self):
        """적격 업체가 비적격 업체보다 앞에 위치해야 한다."""
        bid = _make_bid()
        c_ok = _make_competitor(cid=1, name="적격업체")
        s_ok = _make_stats(total_bids=30, win_count=5)
        c_no = _make_competitor(cid=2, name="비적격업체")
        s_no = _make_stats(total_bids=1, win_count=0)
        rows = [(c_no, s_no), (c_ok, s_ok)]  # 의도적으로 비적격 먼저

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = bid
        db.query.return_value.outerjoin.return_value.limit.return_value.all.return_value = rows

        svc = JointQualService(db=db)
        result = svc.find_matching_partners(bid_id=1, user_track_amount=0, participation_rate=0.6)

        assert result["partners"][0]["name"] == "적격업체"
        assert result["partners"][1]["name"] == "비적격업체"
