import numpy as np
import pandas as pd


class SupplyDemandFeatureExtractor:

    def extract(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy().sort_values("date").reset_index(drop=True)

        for investor in ["foreign", "inst", "indiv"]:
            net = f"{investor}_net"
            if net not in df.columns:
                continue
            s = df[net].astype(float)

            for n in [3, 5, 10, 20]:
                df[f"{investor}_cumnet_{n}d"] = s.rolling(n).sum()

            df[f"{investor}_net_ma5"]  = s.rolling(5).mean()
            df[f"{investor}_net_ma20"] = s.rolling(20).mean()
            df[f"{investor}_trend"]    = np.sign(df[f"{investor}_net_ma5"])

            if "volume" in df.columns:
                df[f"{investor}_intensity"] = s / df["volume"].replace(0, np.nan)

        if "foreign_net" in df.columns and "inst_net" in df.columns:
            df["dual_buy"]    = ((df["foreign_net"] > 0) & (df["inst_net"] > 0)).astype(int)
            df["dual_buy_3d"] = df["dual_buy"].rolling(3).sum()

        if "short_sell_vol" in df.columns and "volume" in df.columns:
            df["short_ratio"]     = df["short_sell_vol"] / df["volume"].replace(0, np.nan)
            df["short_ma5"]       = df["short_ratio"].rolling(5).mean()
            df["short_increasing"] = (df["short_ratio"] > df["short_ma5"]).astype(int)

        # 순매수 비율 (거래량 대비) — 수급 강도 지표
        if "volume" in df.columns:
            vol = df["volume"].replace(0, np.nan)
            if "foreign_net" in df.columns:
                df["foreign_net_ratio"] = df["foreign_net"] / vol
            if "inst_net" in df.columns:
                df["inst_net_ratio"] = df["inst_net"] / vol

        return df.replace([np.inf, -np.inf], np.nan)
