import numpy as np
import pandas as pd


class TechnicalFeatureExtractor:

    def extract(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy().sort_values("date").reset_index(drop=True)
        close  = df["close"].astype(float)
        high   = df["high"].astype(float)
        low    = df["low"].astype(float)
        open_  = df["open"].astype(float)
        volume = df["volume"].astype(float)

        # 수익률
        for n in [1, 2, 3, 5, 10, 20]:
            df[f"return_{n}d"] = close.pct_change(n)

        # 이동평균 비율
        for n in [5, 10, 20, 60, 120]:
            ma = close.rolling(n).mean()
            df[f"ma{n}_ratio"] = close / ma.replace(0, np.nan)
            df[f"ma{n}_slope"] = ma.pct_change(3, fill_method=None)

        # 거래량
        vol5  = volume.rolling(5).mean()
        vol20 = volume.rolling(20).mean()
        df["vol_ratio_5d"]  = volume / vol5.replace(0, np.nan)
        df["vol_ratio_20d"] = volume / vol20.replace(0, np.nan)
        df["vol_surge"]     = (df["vol_ratio_20d"] >= 3).astype(int)

        # 거래대금 비율
        if "amount" in df.columns:
            amt20 = df["amount"].rolling(20).mean()
            df["amount_ratio"] = df["amount"] / amt20.replace(0, np.nan)

        # ATR
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low  - prev_close).abs(),
        ], axis=1).max(axis=1)
        df["atr14"]     = tr.rolling(14).mean()
        df["atr_ratio"] = df["atr14"] / close.replace(0, np.nan)

        # RSI
        df["rsi14"]       = self._rsi(close, 14)
        df["rsi_oversold"]  = (df["rsi14"] < 30).astype(int)
        df["rsi_overbought"] = (df["rsi14"] > 70).astype(int)

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd  = ema12 - ema26
        sig   = macd.ewm(span=9, adjust=False).mean()
        df["macd_hist"]         = macd - sig
        df["macd_golden_cross"] = (
            (macd > sig) & (macd.shift(1) <= sig.shift(1))
        ).astype(int)

        # 볼린저 밴드
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_up  = bb_mid + 2 * bb_std
        bb_lo  = bb_mid - 2 * bb_std
        bb_rng = (bb_up - bb_lo).replace(0, np.nan)
        df["bb_pct"]    = (close - bb_lo) / bb_rng
        df["bb_width"]  = bb_rng / bb_mid.replace(0, np.nan)
        df["bb_squeeze"] = (df["bb_width"] < df["bb_width"].rolling(20).mean() * 0.6).astype(int)

        # 캔들
        df["body_size"]  = (close - open_).abs() / open_.replace(0, np.nan)
        df["is_bullish"] = (close > open_).astype(int)
        df["upper_wick"] = (high - pd.concat([open_, close], axis=1).max(axis=1)) / close.replace(0, np.nan)
        df["lower_wick"] = (pd.concat([open_, close], axis=1).min(axis=1) - low) / close.replace(0, np.nan)

        # 신고가
        for n in [20, 52, 260]:
            df[f"is_new_high_{n}d"] = (close >= close.rolling(n).max()).astype(int)

        # 위치 (52주 범위 내 위치)
        h52 = close.rolling(260).max()
        l52 = close.rolling(260).min()
        df["pos_52w"] = (close - l52) / (h52 - l52 + 1e-8).replace(0, np.nan)

        return df.replace([np.inf, -np.inf], np.nan)

    def inject_market_features(
        self,
        df: pd.DataFrame,
        kospi_close: pd.Series,
        market_volume: pd.Series | None = None,
    ) -> pd.DataFrame:
        """
        KOSPI 지수 데이터로 시장 상대 피처를 계산한다.
        kospi_close: date 인덱스, KOSPI 종가 Series
        market_volume: date 인덱스, 시장 전체 거래량 (없으면 생략)
        """
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])

        kospi_ret = kospi_close.pct_change()
        date_index = pd.to_datetime(df["date"])

        def align(series: pd.Series, shift: int = 0) -> pd.Series:
            shifted = series.shift(shift)
            return date_index.map(shifted)

        df["kospi_return_1d"] = align(kospi_ret, 0)
        df["kospi_return_5d"] = date_index.map(kospi_close.pct_change(5))

        if "return_5d" in df.columns:
            df["rel_strength_5d"] = df["return_5d"] - df["kospi_return_5d"]

        if market_volume is not None:
            mkt_vol20 = market_volume.rolling(20).mean()
            df["market_vol_ratio"] = date_index.map(
                market_volume / mkt_vol20.replace(0, np.nan)
            )

        return df.replace([np.inf, -np.inf], np.nan)

    def _rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        delta = prices.diff()
        gain  = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
        loss  = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
        rs    = gain / loss.replace(0, np.nan)
        return 100 - 100 / (1 + rs)
