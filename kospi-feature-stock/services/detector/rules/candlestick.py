import logging

logger = logging.getLogger(__name__)


class CandlestickDetector:

    LONG_WHITE_BODY_RATIO = 0.65
    LONG_WHITE_MIN_CHANGE = 3.0   # %

    def detect_long_white_candle(self, bar: dict) -> bool:
        o = int(bar.get("open",  0))
        h = int(bar.get("high",  0))
        l = int(bar.get("low",   0))
        c = int(bar.get("close", 0))
        if not all([o, h, l, c]) or c <= o:
            return False
        total = h - l
        if total == 0:
            return False
        body_ratio  = (c - o) / total
        change_rate = (c - o) / o * 100
        return body_ratio >= self.LONG_WHITE_BODY_RATIO and change_rate >= self.LONG_WHITE_MIN_CHANGE

    def long_white_score(self, bar: dict) -> float:
        """봉 크기와 거래량 비율 기반 동적 점수 (0.50~0.92)."""
        o = int(bar.get("open",  0))
        h = int(bar.get("high",  0))
        l = int(bar.get("low",   0))
        c = int(bar.get("close", 0))
        if not all([o, h, l, c]) or c <= o or (h - l) == 0:
            return 0.55
        body_ratio  = (c - o) / (h - l)
        change_rate = (c - o) / o * 100
        vol_ratio   = float(bar.get("volume_ratio", 1.0))

        base = 0.50 + (body_ratio - 0.65) * 0.5 + (change_rate - 3.0) * 0.02
        vol_bonus = min(0.10, (vol_ratio - 1.0) * 0.02) if vol_ratio > 1.0 else 0.0
        return round(min(0.92, max(0.50, base + vol_bonus)), 3)

    def detect_hammer(self, bar: dict) -> bool:
        o = int(bar.get("open",  0))
        h = int(bar.get("high",  0))
        l = int(bar.get("low",   0))
        c = int(bar.get("close", 0))
        if not all([o, h, l, c]):
            return False
        body         = abs(c - o)
        lower_shadow = min(o, c) - l
        upper_shadow = h - max(o, c)
        return body > 0 and lower_shadow >= 2 * body and upper_shadow <= 0.1 * body

    def hammer_score(self, bar: dict) -> float:
        """하단 꼬리 길이 기반 동적 점수 (0.45~0.72)."""
        o = int(bar.get("open", 0))
        l = int(bar.get("low",  0))
        c = int(bar.get("close", 0))
        body = abs(c - o)
        lower_shadow = min(o, c) - l
        ratio = lower_shadow / body if body > 0 else 0.0
        base = 0.45 + min(0.15, (ratio - 2.0) * 0.03)
        return round(min(0.72, max(0.45, base)), 3)

    def detect_morning_star(self, bars: list[dict]) -> bool:
        """
        모닝스타 3봉 패턴:
        - b1: 명확한 음봉
        - b2: 작은 몸통(도지/소형봉)
        - b3: b1 몸통의 50% 이상인 양봉
        """
        if len(bars) < 3:
            return False
        b1, b2, b3 = bars[-3], bars[-2], bars[-1]

        o1, c1 = int(b1.get("open", 0)), int(b1.get("close", 0))
        o3, c3 = int(b3.get("open", 0)), int(b3.get("close", 0))
        body1 = o1 - c1  # 음봉: open > close
        body3 = c3 - o3  # 양봉: close > open

        if body1 <= 0 or body3 <= 0:
            return False

        # b3가 b1 몸통의 50% 이상
        if body3 < body1 * 0.5:
            return False

        # b2: 몸통이 전체 범위의 40% 이하 (도지/소형봉 조건)
        o2, h2, l2, c2 = (
            int(b2.get("open", 0)), int(b2.get("high", 0)),
            int(b2.get("low",  0)), int(b2.get("close", 0)),
        )
        range2 = h2 - l2
        body2  = abs(c2 - o2)
        if range2 > 0 and body2 / range2 > 0.40:
            return False

        # 갭 조건: b2 고가 < b1 종가, b3 시가 > b2 고가
        if h2 >= c1 or o3 <= h2:
            return False

        return True
