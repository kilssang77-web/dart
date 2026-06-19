"""
패턴 임베더 — 256차원 벡터.

정식 구현체는 services/recommender/pattern_vector.py (v3).
이 파일은 ml 서비스 내부에서 동일한 인터페이스를 제공하는 래퍼입니다.
벡터 구조 변경 시 두 파일을 함께 업데이트해야 합니다.
"""
import numpy as np
import pandas as pd

PATTERN_DIM = 256


class PatternEmbedder:
    """
    특징주 패턴 → 256차원 벡터.
    외부 API 없이 순수 numpy 계산.
    """

    def embed(self, df: pd.DataFrame, window: int = 20) -> np.ndarray:
        if len(df) < window:
            return np.zeros(PATTERN_DIM, dtype=np.float32)

        recent = df.tail(window).copy()
        close  = recent["close"].astype(float).values
        volume = recent["volume"].astype(float).values if "volume" in recent else np.ones(window)

        # 정규화
        close_n  = self._normalize(close)
        volume_n = self._normalize(volume)

        foreign_n = np.zeros(window)
        if "foreign_net" in recent.columns:
            foreign_n = self._normalize(recent["foreign_net"].fillna(0).astype(float).values)

        indicators = self._calc_indicators(close, volume, window)

        vec = np.concatenate([close_n, volume_n, foreign_n, indicators])
        vec = vec[:PATTERN_DIM]
        if len(vec) < PATTERN_DIM:
            vec = np.pad(vec, (0, PATTERN_DIM - len(vec)))

        norm = np.linalg.norm(vec)
        return (vec / (norm + 1e-8)).astype(np.float32)

    def _normalize(self, arr: np.ndarray) -> np.ndarray:
        std = arr.std()
        if std < 1e-8:
            return np.zeros_like(arr, dtype=np.float32)
        return ((arr - arr.mean()) / std).astype(np.float32)

    def _calc_indicators(self, close: np.ndarray, volume: np.ndarray, window: int) -> np.ndarray:
        features = []

        # RSI 패턴
        rsi = self._rsi(close, min(14, window - 1))
        features.extend((rsi[-window:] / 100.0).tolist())  # 20

        # EMA 비율
        ema12 = self._ema(close, min(12, window - 1))
        ema26 = self._ema(close, min(26, window - 1))
        macd  = ema12 - ema26
        macd_n = self._normalize(macd)
        features.extend(macd_n[-window:].tolist())  # 20

        # 볼린저 %B
        bb = self._bb_pct(close, min(20, window - 1))
        features.extend(bb[-window:].tolist())  # 20

        # 거래량 비율
        vol_mean = volume.mean() + 1e-8
        features.extend((volume[-window:] / vol_mean).clip(0, 10).tolist())  # 20

        # 고저 위치
        hl_range = (np.maximum.accumulate(close) - np.minimum.accumulate(close)) + 1e-8
        hl_pos   = (close - np.minimum.accumulate(close)) / hl_range
        features.extend(hl_pos[-window:].tolist())  # 20

        # 패딩 → 196 dim
        while len(features) < 196:
            features.append(0.0)
        return np.array(features[:196], dtype=np.float32)

    def _ema(self, data: np.ndarray, span: int) -> np.ndarray:
        alpha = 2.0 / (max(span, 1) + 1)
        result = np.empty_like(data, dtype=float)
        result[0] = data[0]
        for i in range(1, len(data)):
            result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
        return result

    def _rsi(self, prices: np.ndarray, period: int = 14) -> np.ndarray:
        delta = np.diff(prices)
        gain  = np.maximum(delta, 0)
        loss  = np.maximum(-delta, 0)
        period = max(period, 1)
        avg_gain = np.full(len(prices), np.nan)
        avg_loss = np.full(len(prices), np.nan)
        if len(gain) >= period:
            avg_gain[period] = gain[:period].mean()
            avg_loss[period] = loss[:period].mean()
            for i in range(period + 1, len(prices)):
                avg_gain[i] = (avg_gain[i-1] * (period-1) + gain[i-1]) / period
                avg_loss[i] = (avg_loss[i-1] * (period-1) + loss[i-1]) / period
        rs  = np.where(avg_loss == 0, 100.0, avg_gain / (avg_loss + 1e-8))
        rsi = 100 - 100 / (1 + rs)
        return np.nan_to_num(rsi, nan=50.0)

    def _bb_pct(self, prices: np.ndarray, period: int = 20) -> np.ndarray:
        result = np.full(len(prices), 0.5)
        period = max(period, 2)
        for i in range(period - 1, len(prices)):
            w   = prices[i - period + 1:i + 1]
            mid = w.mean()
            std = w.std()
            up  = mid + 2 * std
            lo  = mid - 2 * std
            if up - lo > 0:
                result[i] = (prices[i] - lo) / (up - lo)
        return result
