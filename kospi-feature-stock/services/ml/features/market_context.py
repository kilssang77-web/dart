import numpy as np
import pandas as pd


class MarketContextFeatureExtractor:
    """KOSPI 지수 대비 상대강도 및 시장 국면 피처."""

    def extract(self, df: pd.DataFrame, kospi_df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if kospi_df is None or kospi_df.empty:
            df["kospi_return_1d"]    = 0.0
            df["kospi_return_5d"]    = 0.0
            df["rel_strength_5d"]    = 0.0
            df["market_volatility"]  = 0.01
            df["market_trend"]       = 0
            df["market_momentum_20d"] = 0.0
            df["kospi_above_ma60"]   = 0
            return df

        kospi    = kospi_df.set_index("date")["close"].astype(float)
        kospi_r1 = kospi.pct_change(1)
        kospi_r5 = kospi.pct_change(5)

        # ── 시장 국면 피처 ──────────────────────────────────────
        ma20  = kospi.rolling(20).mean()
        ma60  = kospi.rolling(60).mean()
        rsi14 = self._rsi(kospi, 14)

        # 불장: KOSPI > MA60 AND MA20 > MA60 AND RSI > 52
        bull = ((kospi > ma60) & (ma20 > ma60) & (rsi14 > 52)).astype(int)
        # 약세장: KOSPI < MA60 AND MA20 < MA60 AND RSI < 48
        bear = ((kospi < ma60) & (ma20 < ma60) & (rsi14 < 48)).astype(int)

        # 시장 변동성: 일간 수익률 20일 표준편차 (vol_ratio가 아닌 실제 변동성)
        kospi_volatility = kospi.pct_change().rolling(20).std()

        # 시장 20일 모멘텀
        kospi_mom20 = kospi.pct_change(20)

        df["date_str"] = df["date"].astype(str)
        df["kospi_return_1d"]     = df["date_str"].map(kospi_r1.to_dict()).fillna(0)
        df["kospi_return_5d"]     = df["date_str"].map(kospi_r5.to_dict()).fillna(0)
        df["market_volatility"]   = df["date_str"].map(
            kospi_volatility.to_dict()
        ).fillna(kospi_volatility.mean())
        df["market_trend"]        = df["date_str"].map(
            bull.sub(bear).to_dict()  # +1=bull, -1=bear, 0=sideways
        ).fillna(0)
        df["market_momentum_20d"] = df["date_str"].map(kospi_mom20.to_dict()).fillna(0)
        df["kospi_above_ma60"]    = df["date_str"].map(
            (kospi > ma60).astype(int).to_dict()
        ).fillna(0)

        if "return_5d" in df.columns:
            df["rel_strength_5d"] = df["return_5d"] - df["kospi_return_5d"]
        if "return_1d" in df.columns:
            df["rel_strength_1d"] = df["return_1d"] - df["kospi_return_1d"]

        df.drop(columns=["date_str"], inplace=True)
        return df.replace([np.inf, -np.inf], np.nan)

    def _rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        delta = prices.diff()
        gain  = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
        loss  = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
        rs    = gain / loss.replace(0, np.nan)
        return 100 - 100 / (1 + rs)
