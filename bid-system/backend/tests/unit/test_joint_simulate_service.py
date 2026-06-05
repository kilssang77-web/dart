"""JointSimulateService.simulate 단위 테스트"""
import sys
from unittest.mock import MagicMock, patch

for _mod in ("joblib", "lightgbm", "xgboost", "sklearn",
             "sklearn.cluster", "sklearn.preprocessing", "sklearn.impute"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest
from app.services import JointSimulateService


def _make_bid(bid_id=1, base_amount=500_000_000, min_bid_rate=0.87745, title="테스트 공고"):
    bid = MagicMock()
    bid.id          = bid_id
    bid.title       = title
    bid.base_amount = base_amount
    bid.min_bid_rate = min_bid_rate
    return bid


def _make_competitor(cid, name, biz_reg_no=None):
    c = MagicMock()
    c.id         = cid
    c.name       = name
    c.biz_reg_no = biz_reg_no or f"123-45-{cid:05d}"
    return c


def _make_stats_row(total_bids, win_count, avg_rate=0.885):
    r = MagicMock()
    r.total_bids = total_bids
    r.win_count  = win_count
    r.avg_rate   = avg_rate
    return r


def _make_db(bid, competitor=None, stats_row=None):
    """bid 조회와 CompetitorStat 집계, Competitor 조회를 순서대로 반환하는 Mock DB."""
    db = MagicMock()

    # bid 조회
    db.query.return_value.filter.return_value.first.side_effect = [
        bid,
        competitor,  # Competitor 조회 (있을 경우)
    ]

    # CompetitorStat 집계 (.filter().first())
    db.query.return_value.filter.return_value.filter.return_value.first.return_value = stats_row

    return db


class TestJointSimulateService:

    def test_404_when_bid_not_found(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        svc = JointSimulateService(db=db)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            svc.simulate(bid_id=999, partners=[])
        assert exc.value.status_code == 404

    def test_user_partner_only(self):
        """귀사만 있는 단독 케이스 — 점수 계산 확인."""
        bid = _make_bid(base_amount=300_000_000)
        db  = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = bid

        svc    = JointSimulateService(db=db)
        result = svc.simulate(
            bid_id=1,
            partners=[{"user_track": 500_000_000, "participation_rate": 1.0}],
        )

        assert result["bid_id"] == 1
        assert len(result["partners"]) == 1
        p = result["partners"][0]
        assert p["name"] == "귀사"
        assert p["participation_rate"] == 1.0
        assert p["track_amount"] == 500_000_000
        assert p["qual_score"] > 0
        assert "joint_result" in result

    def test_threshold_by_base_amount(self):
        """기초금액 구간별 기준점수 검증."""
        cases = [
            (200_000_000,    12.0),  # 2억 → 3억 미만 구간
            (1_000_000_000,  14.0),  # 10억 → 30억 미만
            (5_000_000_000,  16.0),  # 50억 → 100억 미만
            (20_000_000_000, 18.0),  # 200억 → 100억 이상
        ]
        for base_amount, expected_threshold in cases:
            bid = _make_bid(base_amount=base_amount)
            db  = MagicMock()
            db.query.return_value.filter.return_value.first.return_value = bid

            svc    = JointSimulateService(db=db)
            result = svc.simulate(bid_id=1, partners=[{"user_track": 0, "participation_rate": 1.0}])
            assert result["joint_result"]["threshold"] == expected_threshold, (
                f"base_amount={base_amount} → expected threshold {expected_threshold}, "
                f"got {result['joint_result']['threshold']}"
            )

    def test_joint_passes_when_score_meets_threshold(self):
        """합산점수 >= 기준점수이면 passes=True."""
        bid = _make_bid(base_amount=200_000_000)  # threshold=12.0
        db  = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = bid

        svc    = JointSimulateService(db=db)
        # track_amount=20억 → perf_score=5+10*15=min(20, 5+(20억/2억)*15) → 20 → qual=20*1.0=20 >= 12
        result = svc.simulate(
            bid_id=1,
            partners=[{"user_track": 2_000_000_000, "participation_rate": 1.0}],
        )
        assert result["joint_result"]["passes"] is True

    def test_joint_fails_when_score_below_threshold(self):
        """합산점수 < 기준점수이면 passes=False."""
        bid = _make_bid(base_amount=200_000_000)  # threshold=12.0
        db  = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = bid

        svc    = JointSimulateService(db=db)
        # track_amount=0 → perf_score=5.0 → qual=5.0*0.3=1.5 < 12
        result = svc.simulate(
            bid_id=1,
            partners=[{"user_track": 0, "participation_rate": 0.3}],
        )
        assert result["joint_result"]["passes"] is False

    def test_min_bid_amount_matches_bid_rate(self):
        """min_bid_amount = base_amount * min_bid_rate."""
        base_amount  = 500_000_000
        min_bid_rate = 0.87745
        bid = _make_bid(base_amount=base_amount, min_bid_rate=min_bid_rate)
        db  = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = bid

        svc    = JointSimulateService(db=db)
        result = svc.simulate(bid_id=1, partners=[{"user_track": 0, "participation_rate": 1.0}])

        expected = int(base_amount * min_bid_rate)
        assert result["joint_result"]["min_bid_amount"] == expected
        assert result["bid_amount_required"] == expected

    def test_response_structure_keys(self):
        """응답 최상위 키와 joint_result 키 전체 존재 여부."""
        bid = _make_bid()
        db  = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = bid

        svc    = JointSimulateService(db=db)
        result = svc.simulate(bid_id=1, partners=[{"user_track": 0, "participation_rate": 1.0}])

        assert set(result.keys()) >= {"bid_id", "bid_amount_required", "partners", "joint_result"}
        jr = result["joint_result"]
        assert set(jr.keys()) >= {"passes", "total_qual_score", "threshold",
                                  "min_bid_amount", "min_bid_rate", "margin"}

    def test_partner_passes_flag_reflects_individual_score(self):
        """perf_score >= 8.0이면 partner.passes=True, 미만이면 False."""
        bid = _make_bid(base_amount=200_000_000)
        db  = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = bid

        svc = JointSimulateService(db=db)

        # 실적 없음 → perf_score=5.0 → passes=False
        result_fail = svc.simulate(
            bid_id=1, partners=[{"user_track": 0, "participation_rate": 0.5}]
        )
        assert result_fail["partners"][0]["passes"] is False

        # 실적 충분 (track=10억, base=2억 → ratio=5 → score=min(20, 5+75)=20) → passes=True
        result_pass = svc.simulate(
            bid_id=1, partners=[{"user_track": 1_000_000_000, "participation_rate": 0.5}]
        )
        assert result_pass["partners"][0]["passes"] is True

    def test_empty_partners_returns_valid_structure(self):
        """파트너 없이 호출해도 올바른 구조 반환."""
        bid = _make_bid()
        db  = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = bid

        svc    = JointSimulateService(db=db)
        result = svc.simulate(bid_id=1, partners=[])

        assert result["partners"] == []
        assert result["joint_result"]["total_qual_score"] == 0.0
        assert result["joint_result"]["passes"] is False
