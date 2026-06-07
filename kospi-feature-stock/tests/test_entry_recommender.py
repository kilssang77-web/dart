import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/recommender"))

import pytest
from unittest.mock import MagicMock
from entry_recommender import EntryRecommender, EntryRecommendation


def _mock_ml(prob=0.60, risk=0.30, hold=5, exp_ret=5.0):
    m = MagicMock()
    m.success_prob = prob
    m.risk_score   = risk
    m.hold_days    = hold
    m.expected_return = exp_ret
    m.atr_ratio = None  # MagicMock 자동 속성 생성 방지
    return m


def _event(price=10000, vol_ratio=3.0, change_rate=5.0, event_type="VOLUME_SURGE"):
    return {
        "code": "005930",
        "price": price,
        "volume_ratio": vol_ratio,
        "change_rate": change_rate,
        "event_type": event_type,
    }


def _sim_stats(success_rate=0.60, count=10, avg_return=6.0):
    return {"success_rate": success_rate, "count": count, "avg_return_5d": avg_return}


@pytest.fixture
def rec():
    return EntryRecommender()


# ── 진입 판단 ──────────────────────────────────────────────────────────────
class TestDecision:

    def test_high_risk_returns_skip(self, rec):
        # 거래량 25배 → risk += 0.25, 급등 20% → +0.30, ML 0.8×0.45 → +0.36 = 0.91 → SKIP
        result = rec.recommend(_event(vol_ratio=25, change_rate=20), _mock_ml(risk=0.80), _sim_stats(), [])
        assert result.action == "SKIP"

    def test_low_prob_returns_wait(self, rec):
        # ML prob 0.40 < 0.55 → WAIT
        result = rec.recommend(_event(), _mock_ml(prob=0.40, risk=0.10), _sim_stats(success_rate=0.40, count=0), [])
        assert result.action == "WAIT"

    def test_rr_always_at_least_two(self, rec):
        # target_dist = max(10%, stop_dist×2) 이므로 rr는 항상 ≥ 2.0
        result = rec.recommend(_event(), _mock_ml(prob=0.70, risk=0.10, exp_ret=0.0), _sim_stats(), [])
        assert result.risk_reward_ratio >= 2.0

    def test_good_conditions_returns_buy(self, rec):
        # prob 높고, risk 낮고, rr 충분
        result = rec.recommend(_event(vol_ratio=3, change_rate=5), _mock_ml(prob=0.70, risk=0.10, exp_ret=15.0), _sim_stats(), [])
        assert result.action == "BUY"

    def test_no_price_returns_skip(self, rec):
        result = rec.recommend({**_event(), "price": 0}, _mock_ml(), _sim_stats(), [])
        assert result.action == "SKIP"


# ── 가격 계산 ──────────────────────────────────────────────────────────────
class TestPriceCalculation:

    def test_stop_loss_below_entry(self, rec):
        result = rec.recommend(_event(price=10000), _mock_ml(prob=0.70, risk=0.10, exp_ret=15.0), _sim_stats(), [])
        assert result.stop_loss_price < result.entry_price

    def test_stop_loss_at_least_5_pct_down(self, rec):
        result = rec.recommend(_event(price=10000), _mock_ml(prob=0.70, risk=0.10, exp_ret=5.0), _sim_stats(), [])
        actual_stop_pct = (result.entry_price - result.stop_loss_price) / result.entry_price
        assert actual_stop_pct >= 0.04  # 반올림 허용

    def test_target_above_entry(self, rec):
        result = rec.recommend(_event(price=10000), _mock_ml(prob=0.70, risk=0.10, exp_ret=15.0), _sim_stats(), [])
        assert result.target_price > result.entry_price

    def test_rr_at_least_two(self, rec):
        result = rec.recommend(_event(price=10000), _mock_ml(prob=0.70, risk=0.10, exp_ret=15.0), _sim_stats(), [])
        if result.action == "BUY":
            assert result.risk_reward_ratio >= 2.0

    def test_entry_band_symmetric(self, rec):
        result = rec.recommend(_event(price=10000), _mock_ml(prob=0.70, risk=0.10, exp_ret=15.0), _sim_stats(), [])
        assert result.entry_price_low  <= result.entry_price
        assert result.entry_price_high >= result.entry_price


# ── 확률 계산 ──────────────────────────────────────────────────────────────
class TestProbabilityBlending:

    def test_prob_between_ml_and_sim(self, rec):
        ml = _mock_ml(prob=0.60, risk=0.10, exp_ret=15.0)
        result = rec.recommend(_event(), ml, _sim_stats(success_rate=0.80, count=25), [])
        # blended prob는 0.60~0.80 사이
        assert 0.60 <= result.success_prob <= 0.80

    def test_zero_sim_cases_uses_ml_prob(self, rec):
        ml = _mock_ml(prob=0.65, risk=0.10, exp_ret=15.0)
        result = rec.recommend(_event(), ml, _sim_stats(success_rate=0.90, count=0), [])
        assert abs(result.success_prob - 0.65) < 0.01
