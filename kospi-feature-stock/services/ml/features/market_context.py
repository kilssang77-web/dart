import numpy as np
import pandas as pd


class MarketContextFeatureExtractor:
    """KOSPI 지수 대비 상대강도 피처"""

    def extract(self, df: pd.DataFrame, kospi_df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if kospi_df is None or kospi_df.empty:
            df["kospi_return_1d"] = 0.0
            df["kospi_return_5d"] = 0.0
            df["rel_strength_5d"] = 0.0
            df["market_vol_ratio"] = 1.0
            return df

        kospi = kospi_df.set_index("date")["close"].astype(float)
        kospi_r1 = kospi.pct_change(1)
        kospi_r5 = kospi.pct_change(5)

        df["date_str"] = df["date"].astype(str)
        df["kospi_return_1d"] = df["date_str"].map(kospi_r1.to_dict()).fillna(0)
        df["kospi_return_5d"] = df["date_str"].map(kospi_r5.to_dict()).fillna(0)

        if "return_5d" in df.columns:
            df["rel_strength_5d"] = df["return_5d"] - df["kospi_return_5d"]

        vol_ma20 = kospi.rolling(20).std()
        df["market_vol_ratio"] = (
            df["date_str"].map(vol_ma20.to_dict()).fillna(vol_ma20.mean())
        )

        df.drop(columns=["date_str"], inplace=True)
        return df.replace([np.inf, -np.inf], np.nan)
