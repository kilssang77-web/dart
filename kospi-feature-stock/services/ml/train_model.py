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
from sklearn.metrics import roc_auc_score, classification_report, brier_score_loss

sys.path.insert(0, "/app")
from features.technical import TechnicalFeatureExtractor
from features.supply_demand import SupplyDemandFeatureExtractor
from models.lgbm_predictor import FEATURE_COLUMNS
from models.trainer import LGBMTrainer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("train")


async def load_disclosure_sentiment(
    pool: asyncpg.Pool, start: str, end: str
) -> pd.DataFrame:
    """공시 감성 점수를 (code, date) 키로 집계하여 반환."""
    start_d, end_d = date_type.fromisoformat(start), date_type.fromisoformat(end)
    rows = await pool.fetch(
        """
        SELECT
            code,
            disclosed_at::DATE AS date,
            AVG(sentiment_score) AS disclosure_sentiment,
            MAX(CASE WHEN category='favorable' THEN 1 ELSE 0 END) AS has_favorable_disclosure
        FROM disclosures
        WHERE code IS NOT NULL
          AND disclosed_at::DATE BETWEEN $1 AND $2
        GROUP BY code, disclosed_at::DATE
        """,
        start_d, end_d,
    )
    if not rows:
        return pd.DataFrame(columns=["code", "date", "disclosure_sentiment", "has_favorable_disclosure"])
    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = df["date"].astype(str)
    return df


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


async def load_news_sentiment(pool: asyncpg.Pool, start: str, end: str) -> pd.DataFrame:
    """뉴스 감성 점수를 (code, date) 키로 7일 롤링 평균으로 집계하여 반환."""
    start_d, end_d = date_type.fromisoformat(start), date_type.fromisoformat(end)
    rows = await pool.fetch(
        """
        SELECT nsl.code, DATE(n.published_at) AS date,
               AVG(n.sentiment_score) AS avg_sentiment,
               COUNT(*) AS news_count
        FROM news n
        JOIN news_stock_links nsl ON nsl.news_id = n.id
        WHERE DATE(n.published_at) BETWEEN $1 AND $2
          AND n.sentiment_score IS NOT NULL
        GROUP BY nsl.code, DATE(n.published_at)
        """,
        start_d, end_d,
    )
    if not rows:
        return pd.DataFrame(columns=["code", "date", "avg_sentiment", "news_count"])
    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = df["date"].astype(str)
    return df


async def main(args):
    pool = await asyncpg.create_pool(
        dsn=os.environ["POSTGRES_DSN"].replace("+asyncpg", ""),
        min_size=3, max_size=10,
    )
    logger.info(f"Loading data {args.start} ~ {args.end} ...")
    raw = await load_data(pool, args.start, args.end)
    kospi_close, market_vol = await load_market_data(pool, args.start, args.end)
    disc_df = await load_disclosure_sentiment(pool, args.start, args.end)
    news_df = await load_news_sentiment(pool, args.start, args.end)
    logger.info(f"Loaded {len(raw)} rows, {raw['code'].nunique()} stocks, "
                f"KOSPI={len(kospi_close)} days, disclosures={len(disc_df)} rows, "
                f"news_sentiment={len(news_df)} rows")
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

            # 공시 감성 피처 주입 (해당 날짜 공시가 없으면 0/0)
            if not disc_df.empty:
                code_disc = disc_df[disc_df["code"] == code][["date", "disclosure_sentiment", "has_favorable_disclosure"]]
                if not code_disc.empty:
                    f = f.merge(code_disc, on="date", how="left")
                    f["disclosure_sentiment"]      = f["disclosure_sentiment"].fillna(0.0)
                    f["has_favorable_disclosure"]  = f["has_favorable_disclosure"].fillna(0).astype(int)
                else:
                    f["disclosure_sentiment"]     = 0.0
                    f["has_favorable_disclosure"] = 0
            else:
                f["disclosure_sentiment"]     = 0.0
                f["has_favorable_disclosure"] = 0

            # 뉴스 감성 피처 주입 — 7일 롤링 평균
            if not news_df.empty:
                code_news = news_df[news_df["code"] == code][["date", "avg_sentiment", "news_count"]].copy()
                if not code_news.empty:
                    code_news = code_news.set_index("date").sort_index()
                    # 일별 데이터가 없는 날은 forward-fill 후 7일 이동평균
                    f_indexed = f.set_index("date")
                    f_indexed["news_sentiment_7d"] = (
                        code_news["avg_sentiment"].reindex(f_indexed.index)
                        .fillna(method="ffill", limit=7).fillna(0.0)
                    )
                    f_indexed["news_count_7d"] = (
                        code_news["news_count"].reindex(f_indexed.index)
                        .fillna(0.0).rolling(7, min_periods=1).sum().clip(upper=50) / 50.0
                    )
                    f = f_indexed.reset_index()
                else:
                    f["news_sentiment_7d"] = 0.0
                    f["news_count_7d"]     = 0.0
            else:
                f["news_sentiment_7d"] = 0.0
                f["news_count_7d"]     = 0.0

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

    # ── LightGBM ──────────────────────────────────────────────────────────────
    logger.info("Training entry model (LightGBM)...")
    entry_m   = tr.train_entry(X_tr, le_tr, X_va, le_va, model_dir)
    entry_raw = entry_m.predict_proba(X_va)[:, 1]
    auc_lgbm  = roc_auc_score(le_va, entry_raw)
    brier_e   = brier_score_loss(le_va, entry_raw)
    logger.info(f"[LightGBM] Entry AUC: {auc_lgbm:.4f}  Brier: {brier_e:.4f}")

    logger.info("Training risk model (LightGBM)...")
    risk_m   = tr.train_risk(X_tr, lr_tr, X_va, lr_va, model_dir)
    risk_raw = risk_m.predict_proba(X_va)[:, 1]
    auc_r    = roc_auc_score(lr_va, risk_raw)
    brier_r  = brier_score_loss(lr_va, risk_raw)
    logger.info(f"[LightGBM] Risk  AUC: {auc_r:.4f}  Brier: {brier_r:.4f}")

    # ── CatBoost 비교 ─────────────────────────────────────────────────────────
    auc_cat = 0.0
    try:
        from catboost import CatBoostClassifier
        cat_e = CatBoostClassifier(
            iterations=500, learning_rate=0.05, depth=6,
            eval_metric="AUC", early_stopping_rounds=50,
            random_seed=42, verbose=0,
        )
        cat_e.fit(X_tr, le_tr, eval_set=(X_va, le_va))
        auc_cat = roc_auc_score(le_va, cat_e.predict_proba(X_va)[:, 1])
        logger.info(f"[CatBoost]  Entry AUC: {auc_cat:.4f}")
    except ImportError:
        logger.warning("[CatBoost] not installed — skipping comparison")

    # ── XGBoost 비교 ──────────────────────────────────────────────────────────
    auc_xgb = 0.0
    try:
        import xgboost as xgb
        xgb_e = xgb.XGBClassifier(
            n_estimators=500, learning_rate=0.05, max_depth=6,
            eval_metric="auc", early_stopping_rounds=50,
            random_state=42, verbosity=0,
        )
        xgb_e.fit(X_tr, le_tr, eval_set=[(X_va, le_va)], verbose=False)
        auc_xgb = roc_auc_score(le_va, xgb_e.predict_proba(X_va)[:, 1])
        logger.info(f"[XGBoost]   Entry AUC: {auc_xgb:.4f}")
    except ImportError:
        logger.warning("[XGBoost] not installed — skipping comparison")

    # ── 모델 선택 ─────────────────────────────────────────────────────────────
    best_name = "LightGBM"
    best_auc  = auc_lgbm
    if auc_cat > best_auc:
        best_auc  = auc_cat
        best_name = "CatBoost"
    if auc_xgb > best_auc:
        best_auc  = auc_xgb
        best_name = "XGBoost"

    logger.info(f"\n{'='*50}")
    logger.info(f"모델 비교 결과:")
    logger.info(f"  LightGBM AUC: {auc_lgbm:.4f}")
    logger.info(f"  CatBoost AUC: {auc_cat:.4f}")
    logger.info(f"  XGBoost  AUC: {auc_xgb:.4f}")
    logger.info(f"  → 선택: {best_name} (AUC {best_auc:.4f})")
    logger.info(f"{'='*50}\n")

    logger.info("\n--- Entry Model Classification Report (LightGBM) ---")
    y_pred = (entry_raw >= 0.5).astype(int)
    print(classification_report(le_va, y_pred))

    # Feature importance
    fi = pd.Series(entry_m.feature_importances_, index=FEATURE_COLUMNS).sort_values(ascending=False)
    logger.info("Top 15 features:\n" + fi.head(15).to_string())

    # 항상 0인 피처 경고
    zero_features = [c for c in FEATURE_COLUMNS if X[c].std() < 1e-8]
    if zero_features:
        logger.warning(f"⚠️  항상 0인 피처 발견 ({len(zero_features)}개): {zero_features}")

    logger.info(f"\nModels saved to {model_dir}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end",   default="2024-12-31")
    asyncio.run(main(parser.parse_args()))
