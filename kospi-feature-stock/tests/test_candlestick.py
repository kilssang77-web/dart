import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../services/detector"))

import pytest
from rules.candlestick import CandlestickDetector


@pytest.fixture
def det():
    return CandlestickDetector()


def _bar(o, h, l, c, vol_ratio=1.0, change_rate=None):
    if change_rate is None:
        change_rate = (c - o) / o * 100 if o else 0
    return {"open": o, "high": h, "low": l, "close": c,
            "volume_ratio": vol_ratio, "change_rate": change_rate}


# ── 장대양봉 ──────────────────────────────────────────────────────────────
class TestLongWhiteCandle:

    def test_valid_long_white(self, det):
        # 몸통 80%, 5% 상승
        assert det.detect_long_white_candle(_bar(1000, 1060, 990, 1055)) is True

    def test_body_too_small(self, det):
        # 몸통 50% (< 65%)
        assert det.detect_long_white_candle(_bar(1000, 1050, 990, 1030)) is False

    def test_change_too_small(self, det):
        # 몸통 비율 충분하지만 상승폭 1% (< 3%)
        assert det.detect_long_white_candle(_bar(1000, 1015, 999, 1010)) is False

    def test_bearish_candle(self, det):
        # 음봉
        assert det.detect_long_white_candle(_bar(1050, 1060, 990, 1000)) is False

    def test_score_in_range(self, det):
        score = det.long_white_score(_bar(1000, 1060, 990, 1055, vol_ratio=3.0))
        assert 0.50 <= score <= 0.92


# ── 망치형 ────────────────────────────────────────────────────────────────
class TestHammer:

    def test_valid_hammer(self, det):
        # 몸통=10(1010→1000), 하단꼬리=20(1000-980), 상단꼬리=1(1011-1010)
        # 조건: 하단≥2×몸통(20≥20), 상단≤0.1×몸통(1≤1) → True
        assert det.detect_hammer(_bar(1010, 1011, 980, 1000)) is True

    def test_upper_wick_too_large(self, det):
        # 상단꼬리 5 (> 0.1×10)
        assert det.detect_hammer(_bar(1010, 1020, 985, 1005)) is False

    def test_lower_wick_too_small(self, det):
        # 하단꼬리 5 (< 2×몸통=20)
        assert det.detect_hammer(_bar(1000, 1001, 995, 1020)) is False

    def test_score_in_range(self, det):
        score = det.hammer_score(_bar(1010, 1011, 985, 1000))
        assert 0.45 <= score <= 0.72


# ── 모닝스타 ──────────────────────────────────────────────────────────────
class TestMorningStar:

    def _make_star_bars(self):
        b1 = _bar(1100, 1110, 1050, 1060)   # 음봉, 몸통=40
        b2 = _bar(1055, 1065, 1040, 1058)   # 도지 (몸통 3, 범위 25 → 12%)
        b3 = _bar(1060, 1090, 1055, 1085)   # 양봉, 몸통=25 (≥ 40×0.5=20)
        return [b1, b2, b3]

    def test_valid_morning_star(self, det):
        assert det.detect_morning_star(self._make_star_bars()) is True

    def test_b2_body_too_large(self, det):
        b1 = _bar(1100, 1110, 1050, 1060)
        b2 = _bar(1050, 1070, 1040, 1068)   # 몸통 18 / 범위 30 → 60% (> 40%)
        b3 = _bar(1060, 1090, 1055, 1085)
        assert det.detect_morning_star([b1, b2, b3]) is False

    def test_b3_body_too_small(self, det):
        b1 = _bar(1100, 1110, 1050, 1060)   # 음봉 몸통 40
        b2 = _bar(1055, 1065, 1040, 1058)
        b3 = _bar(1060, 1090, 1055, 1075)   # 양봉 몸통 15 (< 20)
        assert det.detect_morning_star([b1, b2, b3]) is False

    def test_insufficient_bars(self, det):
        bars = self._make_star_bars()
        assert det.detect_morning_star(bars[:2]) is False

    def test_empty_bars(self, det):
        assert det.detect_morning_star([]) is False

    def test_b1_not_bearish(self, det):
        b1 = _bar(1000, 1110, 990, 1090)    # 양봉 (open < close)
        b2, b3 = self._make_star_bars()[1:]
        assert det.detect_morning_star([b1, b2, b3]) is False
