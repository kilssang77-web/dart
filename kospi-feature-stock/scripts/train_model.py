"""
LightGBM 모델 학습.
사용: python scripts/train_model.py --start 2022-01-01 --end 2024-12-31
"""
import argparse
import asyncio
import asyncpg
import os
import sys
import logging
import pandas as pd
import numpy as np
from datetime import date as date_type
from pathlib import Path
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score, classification_report

sys.path.insert(0, "/app")
from features.technical import TechnicalFeatureExtractor
from features.supply_demand import SupplyDemandFeatureExtractor
from models.lgbm_predictor import FEATURE_COLUMNS
from models.trainer import LGBMTrainer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("train")


async def load_data(pool: asyncpg.Pool, start: str, end: str) -> pd.DataFrame:
    start_d, end_d = date_type.fromisoformat(start), date_type.fromisoformat(end)
    rows = await pool.fetch(
        """
        SELECT
            db.date::TEXT AS date, db.code,
            db.open, db.high, db.low, db.close,
            db.volume, db.amount, db.change_rate,
            db.short_sell_vol,
            COALESCE(sd.foreign_net, db.foreign_net_buy) AS foreign_net,
            COALESCE(sd.inst_net,    db.inst_net_buy)    AS inst_net,
            COALESCE(sd.indiv_net,   db.indiv_net_buy)   AS indiv_net
        FROM daily_bars db
        LEFT JOIN supply_demand sd ON sd.code=db.code AND sd.date=db.date
        WHERE db.date BETWEEN $1 AND $2
        ORDER BY db.code, db.date
        """,
        start_d, end_d,
    )
    return pd.DataFrame([dict(r) for r in rows])


async def load_market_data(pool: asyncpg.Pool, start: str, end: str) -> tuple[pd.Series, pd.Series]:
    """KOSPI 지수 종가 및 시장 전체 거래량 반환."""
    start_d, end_d = date_type.fromisoformat(start), date_type.fromisoformat(end)
    rows = await pool.fetch(
        "SELECT date::TEXT AS date, close, volume FROM daily_bars "
        "WHERE code='0001' AND date BETWEEN $1 AND $2 ORDER BY date",
        start_d, end_d,
    )
    if not rows:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    dates = [r["date"] for r in rows]
    kospi_close  = pd.Series([float(r["close"])  for r in rows], index=dates, name="kospi_close")
    market_vol   = pd.Series([float(r["volume"]) for r in rows], index=dates, name="market_vol")
    return kospi_close, market_vol


async def main(args):
    pool = await asyncpg.create_pool(
        dsn=os.environ["POSTGRES_DSN"].replace("+asyncpg", ""),
        min_size=3, max_size=10,
    )
    logger.info(f"Loading data {args.start} ~ {args.end} ...")
    raw = await load_data(pool, args.start, args.end)
    kospi_close, market_vol = await load_market_data(pool, args.start, args.end)
    logger.info(f"Loaded {len(raw)} rows, {raw['code'].nunique()} stocks, KOSPI={len(kospi_close)} days")
    await pool.close()

    tech = TechnicalFeatureExtractor()
    sd   = SupplyDemandFeatureExtractor()
    tr   = LGBMTrainer()

    all_feat, all_label_e, all_label_r = [], [], []

    for code, grp in raw.groupby("code"):
        grp = grp.sort_values("date").reset_index(drop=True)
        if len(grp) < 80:
            continue
        try:
            f = tech.extract(grp)
            f = sd.extract(f)
            if len(kospi_close) > 0:
                f = tech.inject_market_features(f, kospi_close, market_vol if len(market_vol) > 0 else None)
            f["code"] = code

            label_e = tr.make_label_entry(f, fwd=5, thr=0.05)
            label_r = tr.make_label_risk(f,   fwd=5, loss=-0.05)

            all_feat.append(f)
            all_label_e.append(label_e)
            all_label_r.append(label_r)
        except Exception as e:
            logger.debug(f"Feature error {code}: {e}")

    df = pd.concat(all_feat).reset_index(drop=True)
    le = pd.concat(all_label_e).reset_index(drop=True)
    lr = pd.concat(all_label_r).reset_index(drop=True)

    mask = le.notna() & lr.notna()
    df, le, lr = df[mask], le[mask], lr[mask]

    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0
    X = df[FEATURE_COLUMNS].fillna(0)

    logger.info(f"Training set: {len(X)} rows | entry pos={le.mean():.3f} | risk pos={lr.mean():.3f}")

    tscv  = TimeSeriesSplit(n_splits=5)
    sp    = list(tscv.split(X))
    ti, vi = sp[-1]
    X_tr, X_va = X.iloc[ti], X.iloc[vi]
    le_tr, le_va = le.iloc[ti], le.iloc[vi]
    lr_tr, lr_va = lr.iloc[ti], lr.iloc[vi]

    model_dir = "/models/lgbm"
    Path(model_dir).mkdir(parents=True, exist_ok=True)

    logger.info("Training entry model ...")
    entry_m = tr.train_entry(X_tr, le_tr, X_va, le_va, model_dir)
    auc_e   = roc_auc_score(le_va, entry_m.predict_proba(X_va)[:, 1])
    logger.info(f"Entry AUC: {auc_e:.4f}")

    logger.info("Training risk model ...")
    risk_m  = tr.train_risk(X_tr, lr_tr, X_va, lr_va, model_dir)
    auc_r   = roc_auc_score(lr_va, risk_m.predict_proba(X_va)[:, 1])
    logger.info(f"Risk  AUC: {auc_r:.4f}")

    logger.info("\n--- Entry Model Classification Report ---")
    y_pred = (entry_m.predict_proba(X_va)[:, 1] >= 0.5).astype(int)
    print(classification_report(le_va, y_pred))

    # Feature importance
    fi = pd.Series(entry_m.feature_importances_, index=FEATURE_COLUMNS).sort_values(ascending=False)
    logger.info("Top 15 features:\n" + fi.head(15).to_string())
    logger.info(f"\nModels saved to {model_dir}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end",   default="2024-12-31")
    asyncio.run(main(parser.parse_args()))
