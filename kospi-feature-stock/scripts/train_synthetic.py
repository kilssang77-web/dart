"""
합성 OHLCV 데이터로 LightGBM 모델을 학습하고 모델 파일을 저장합니다.
실데이터 축적 전 서비스 기동용 최소 모델 생성에 사용합니다.

사용: python scripts/train_synthetic.py
"""
import sys
import logging
import numpy as np
import pandas as pd
from pathlib import Path
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score

sys.path.insert(0, "/app")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("train_synthetic")

MODEL_DIR   = "/models/lgbm"
N_STOCKS    = 50
N_DAYS      = 500
RANDOM_SEED = 42


def _generate_ohlcv(n_days: int, rng: np.random.Generator) -> pd.DataFrame:
    """랜덤워크 기반 현실적 일봉 데이터 생성."""
    # 수익률: 정규분포 + 모멘텀 팩터
    drift    = rng.normal(0.0002, 0.0015, n_days)
    momentum = np.zeros(n_days)
    for i in range(5, n_days):
        momentum[i] = drift[i-5:i].mean() * 0.3
    ret = drift + momentum + rng.normal(0, 0.012, n_days)

    close = np.cumprod(1 + ret) * rng.integers(10_000, 300_000)
    close = close.astype(int)

    high  = (close * rng.uniform(1.001, 1.05, n_days)).astype(int)
    low   = (close * rng.uniform(0.95, 0.999, n_days)).astype(int)
    open_ = (close * rng.uniform(0.985, 1.015, n_days)).astype(int)

    base_vol = int(rng.integers(100_000, 5_000_000))
    volume   = (base_vol * rng.uniform(0.2, 6.0, n_days)).astype(int)
    amount   = (close * volume).astype(int)

    # 수급: 외인·기관 순매수 (거래량의 -20% ~ +20%)
    foreign_net = (volume * rng.uniform(-0.2, 0.2, n_days)).astype(int)
    inst_net    = (volume * rng.uniform(-0.15, 0.15, n_days)).astype(int)
    short_vol   = (volume * rng.uniform(0.0, 0.1, n_days)).astype(int)

    dates = pd.date_range("2022-01-03", periods=n_days, freq="B")
    return pd.DataFrame({
        "date":           dates.strftime("%Y-%m-%d"),
        "open":           open_,
        "high":           high,
        "low":            low,
        "close":          close,
        "volume":         volume,
        "amount":         amount,
        "change_rate":    ret * 100,
        "foreign_net":    foreign_net,
        "inst_net":       inst_net,
        "indiv_net":      -(foreign_net + inst_net),
        "short_sell_vol": short_vol,
    })


def _extract_features(df: pd.DataFrame) -> pd.DataFrame:
    """기술적 지표 + 수급 피처 추출."""
    f = df.copy()
    c = f["close"]
    v = f["volume"]

    # 이동평균
    for n in [5, 10, 20, 60]:
        f[f"ma{n}"]     = c.rolling(n).mean()
        f[f"ma{n}_r"]   = c / f[f"ma{n}"] - 1
        f[f"vol_ma{n}"] = v.rolling(n).mean()

    f["vol_ratio"]  = v / f["vol_ma20"].replace(0, np.nan)

    # 볼린저밴드
    bb_mean = c.rolling(20).mean()
    bb_std  = c.rolling(20).std()
    f["bb_upper"] = bb_mean + 2 * bb_std
    f["bb_lower"] = bb_mean - 2 * bb_std
    f["bb_pct"]   = (c - f["bb_lower"]) / (f["bb_upper"] - f["bb_lower"] + 1e-8)

    # RSI(14)
    delta = c.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    f["rsi14"] = 100 - 100 / (1 + gain / (loss + 1e-8))

    # MACD
    ema12 = c.ewm(span=12).mean()
    ema26 = c.ewm(span=26).mean()
    f["macd"]        = ema12 - ema26
    f["macd_signal"] = f["macd"].ewm(span=9).mean()
    f["macd_hist"]   = f["macd"] - f["macd_signal"]

    # 수익률
    for n in [1, 3, 5, 10, 20]:
        f[f"ret{n}d"] = c.pct_change(n)

    # 고가 대비 현재가
    for n in [20, 60]:
        f[f"high{n}d_r"] = c / c.rolling(n).max() - 1

    # 수급
    for col in ["foreign_net", "inst_net", "indiv_net"]:
        if col in f.columns:
            f[f"{col}_20d"] = f[col].rolling(20).mean()
            f[f"{col}_r"]   = f[col] / (v + 1)

    # 거래대금
    f["amount_ma20"] = f["amount"].rolling(20).mean() if "amount" in f.columns else 0
    f["amount_r"]    = f["amount"] / (f["amount_ma20"] + 1) if "amount" in f.columns else 0

    # 봉 형태
    f["body_r"]  = (f["close"] - f["open"]).abs() / (f["high"] - f["low"] + 1)
    f["hl_r"]    = (f["high"] - f["low"]) / (f["close"] + 1)

    return f


FEATURE_COLS = [
    "ma5_r", "ma10_r", "ma20_r", "ma60_r",
    "vol_ratio", "bb_pct", "rsi14",
    "macd", "macd_signal", "macd_hist",
    "ret1d", "ret3d", "ret5d", "ret10d", "ret20d",
    "high20d_r", "high60d_r",
    "body_r", "hl_r",
    "foreign_net_r", "inst_net_r", "indiv_net_r",
    "foreign_net_20d", "inst_net_20d",
    "amount_r",
]


def main():
    rng = np.random.default_rng(RANDOM_SEED)

    logger.info(f"Generating synthetic data: {N_STOCKS} stocks × {N_DAYS} days ...")
    all_feat, all_le, all_lr = [], [], []

    for i in range(N_STOCKS):
        df = _generate_ohlcv(N_DAYS, rng)
        f  = _extract_features(df)

        # 라벨: 5일 후 +5% 이상 상승 (entry), -5% 이상 하락 (risk)
        fwd_ret = f["close"].pct_change(5).shift(-5)
        le = (fwd_ret >= 0.05).astype(int)
        lr = (fwd_ret <= -0.05).astype(int)

        avail = [c for c in FEATURE_COLS if c in f.columns]
        f_sub = f[avail].copy()

        mask = le.notna() & lr.notna() & f_sub.notna().all(axis=1)
        f_sub, le, lr = f_sub[mask], le[mask], lr[mask]

        if len(f_sub) < 50:
            continue

        all_feat.append(f_sub)
        all_le.append(le)
        all_lr.append(lr)

    X  = pd.concat(all_feat).reset_index(drop=True)
    LE = pd.concat(all_le).reset_index(drop=True)
    LR = pd.concat(all_lr).reset_index(drop=True)

    logger.info(f"Dataset: {len(X)} rows | entry_pos={LE.mean():.3f} | risk_pos={LR.mean():.3f}")

    tscv = TimeSeriesSplit(n_splits=5)
    splits = list(tscv.split(X))
    ti, vi = splits[-1]
    X_tr, X_va = X.iloc[ti], X.iloc[vi]
    le_tr, le_va = LE.iloc[ti], LE.iloc[vi]
    lr_tr, lr_va = LR.iloc[ti], LR.iloc[vi]

    avail = X.columns.tolist()

    Path(MODEL_DIR).mkdir(parents=True, exist_ok=True)

    # ── Entry 모델 학습 ───────────────────────────────────────────
    logger.info("Training entry model ...")
    entry_params = {
        "n_estimators": 300, "learning_rate": 0.05,
        "max_depth": 6, "num_leaves": 31,
        "min_child_samples": 20, "subsample": 0.8,
        "colsample_bytree": 0.8, "class_weight": "balanced",
        "random_state": RANDOM_SEED, "verbose": -1,
    }
    entry_m = lgb.LGBMClassifier(**entry_params)
    entry_m.fit(
        X_tr, le_tr,
        eval_set=[(X_va, le_va)],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(100)],
    )
    entry_m.booster_.save_model(f"{MODEL_DIR}/entry_model.lgb")
    auc_e = roc_auc_score(le_va, entry_m.predict_proba(X_va)[:, 1])
    logger.info(f"Entry AUC: {auc_e:.4f}  → saved {MODEL_DIR}/entry_model.lgb")

    # ── Risk 모델 학습 ────────────────────────────────────────────
    logger.info("Training risk model ...")
    risk_params = {
        "n_estimators": 300, "learning_rate": 0.05,
        "max_depth": 5, "num_leaves": 25,
        "min_child_samples": 20, "subsample": 0.8,
        "colsample_bytree": 0.8, "class_weight": "balanced",
        "random_state": RANDOM_SEED, "verbose": -1,
    }
    risk_m = lgb.LGBMClassifier(**risk_params)
    risk_m.fit(
        X_tr, lr_tr,
        eval_set=[(X_va, lr_va)],
        callbacks=[lgb.early_stopping(50, verbose=False)],
    )
    risk_m.booster_.save_model(f"{MODEL_DIR}/risk_model.lgb")
    auc_r = roc_auc_score(lr_va, risk_m.predict_proba(X_va)[:, 1])
    logger.info(f"Risk  AUC: {auc_r:.4f}  → saved {MODEL_DIR}/risk_model.lgb")

    # 피처 컬럼 목록 저장 (추론 시 정렬 기준)
    import json
    meta = {"feature_columns": avail, "entry_auc": auc_e, "risk_auc": auc_r}
    Path(f"{MODEL_DIR}/meta.json").write_text(json.dumps(meta, indent=2))
    logger.info(f"Metadata saved: {MODEL_DIR}/meta.json")
    logger.info("Done.")


if __name__ == "__main__":
    main()
