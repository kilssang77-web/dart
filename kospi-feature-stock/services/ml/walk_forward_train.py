#!/usr/bin/env python3
"""
Walk-Forward 학습 및 검증 스크립트.

분할 전략 (데이터 누수 없음):
  Train : --train-start ~ --train-end   (기본 2020-01-01 ~ 2023-12-31)
  Val   : --val-start   ~ --val-end     (기본 2024-01-01 ~ 2024-12-31)
  Test  : --test-start  ~ --test-end    (기본 2025-01-01 ~ 현재)

Val 세트: 조기 종료 + 임계값 튜닝에 사용
Test 세트: 완전 홀드아웃, 학습에 절대 사용 안 함

출력: AUC, Brier Score, 분류 리포트 (Val/Test 각각)
사용법:
  python walk_forward_train.py \\
      --train-start 2020-01-01 --train-end 2023-12-31 \\
      --val-start 2024-01-01   --val-end 2024-12-31 \\
      --test-start 2025-01-01  --test-end 2026-06-06 \\
      --smote --model-dir /models/lgbm
"""
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

import asyncpg
import numpy as np
import pandas as pd
from sklearn.metrics import (
    roc_auc_score, brier_score_loss,
    classification_report, precision_recall_curve,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models.lgbm_predictor import FEATURE_COLUMNS
from models.trainer import LGBMTrainer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("walk_forward")


# ── 데이터 로딩 ──────────────────────────────────────────────────────────────

async def get_liquid_codes(pool: asyncpg.Pool, start, end, max_codes: int) -> list[str]:
    """거래대금 상위 max_codes개 종목 코드 반환 (메모리 절감용)."""
    rows = await pool.fetch(
        """
        SELECT code, AVG(amount) AS avg_amount
        FROM daily_bars
        WHERE date BETWEEN $1::date AND $2::date
          AND code NOT IN ('0001','1001')
          AND close > 0
        GROUP BY code
        HAVING COUNT(*) >= 100
        ORDER BY avg_amount DESC
        LIMIT $3
        """,
        start, end, max_codes,
    )
    return [r["code"] for r in rows]


async def load_daily_bars(pool: asyncpg.Pool, start, end, codes: list[str] | None = None) -> pd.DataFrame:
    """daily_bars + supply_demand join으로 원시 데이터 로드."""
    code_filter = "AND d.code = ANY($3::text[])" if codes else ""
    params = [start, end] + ([codes] if codes else [])
    rows = await pool.fetch(
        f"""
        SELECT
            d.code, d.date,
            d.open, d.high, d.low, d.close, d.volume, d.amount,
            d.change_rate, d.foreign_net_buy, d.inst_net_buy,
            d.short_sell_vol, d.rsi14, d.macd, d.macd_signal,
            d.bb_upper, d.bb_lower, d.ma5, d.ma20, d.ma60, d.atr14,
            COALESCE(sd.foreign_net, d.foreign_net_buy) AS foreign_net,
            COALESCE(sd.inst_net,    d.inst_net_buy)    AS inst_net
        FROM daily_bars d
        LEFT JOIN supply_demand sd ON sd.code=d.code AND sd.date=d.date
        WHERE d.date BETWEEN $1::date AND $2::date
          AND d.code NOT IN ('0001','1001')
          AND d.close > 0
          {code_filter}
        ORDER BY d.code, d.date
        """,
        *params,
    )
    return pd.DataFrame([dict(r) for r in rows])


async def load_kospi(pool: asyncpg.Pool, start, end) -> pd.DataFrame:
    rows = await pool.fetch(
        """
        SELECT date, close FROM daily_bars
        WHERE code='0001' AND date BETWEEN $1::date AND $2::date
        ORDER BY date
        """,
        start, end,
    )
    if not rows:
        return pd.DataFrame(columns=["close"])
    return pd.DataFrame([dict(r) for r in rows]).set_index("date")


async def load_disclosures(pool: asyncpg.Pool, start, end) -> pd.DataFrame:
    rows = await pool.fetch(
        """
        SELECT code, disclosed_at::date AS date, sentiment_score, category
        FROM disclosures
        WHERE disclosed_at BETWEEN $1::date AND $2::date
        """,
        start, end,
    )
    if not rows:
        return pd.DataFrame(columns=["code", "date", "sentiment_score", "category"])
    return pd.DataFrame([dict(r) for r in rows])


# ── 피처 엔지니어링 ───────────────────────────────────────────────────────────

def _safe(v, default=0.0):
    try:
        f = float(v)
        import math
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return default


def build_features(df: pd.DataFrame, kospi_df: pd.DataFrame, disc_df: pd.DataFrame) -> pd.DataFrame:
    """
    daily_bars DataFrame → 특징 행렬 (FEATURE_COLUMNS 기준).
    종목별 순서 정렬 후 롤링 계산.
    """
    df = df.copy().sort_values(["code", "date"]).reset_index(drop=True)

    results = []
    for code, grp in df.groupby("code"):
        grp = grp.reset_index(drop=True)
        if len(grp) < 80:
            continue

        closes  = grp["close"].astype(float).values
        volumes = grp["volume"].astype(float).fillna(0).values
        amounts = grp["amount"].astype(float).fillna(0).values
        highs   = grp["high"].astype(float).values
        lows    = grp["low"].astype(float).values
        opens   = grp["open"].astype(float).values
        f_nets  = grp["foreign_net"].astype(float).fillna(0).values
        i_nets  = grp["inst_net"].astype(float).fillna(0).values

        rows_feat = []
        for i in range(60, len(grp)):
            c   = closes[i]
            if c <= 0:
                continue

            def ret(n):
                return (c / closes[i-n] - 1)*100 if i >= n and closes[i-n] > 0 else 0.0

            def ma(n):
                v = closes[max(0,i-n+1):i+1]
                return float(v.mean()) if len(v) > 0 else c

            # Returns
            r1d = ret(1); r3d = ret(3); r5d = ret(5)

            # MA ratios
            ma5 = ma(5); ma20 = ma(20); ma60 = ma(60)
            ma5_r  = c/ma5  if ma5  else 1.0
            ma20_r = c/ma20 if ma20 else 1.0
            ma60_r = c/ma60 if ma60 else 1.0
            ma5_sl  = (ma(5)/ma(10)-1)  if i >= 10  else 0.0
            ma20_sl = (ma(20)/ma(40)-1) if i >= 40  else 0.0

            # Volume
            v5  = volumes[max(0,i-4):i+1].mean()
            v20 = volumes[max(0,i-19):i+1].mean()
            a20 = amounts[max(0,i-19):i+1].mean()
            vr5  = volumes[i]/v5  if v5  else 1.0
            vr20 = volumes[i]/v20 if v20 else 1.0
            vsurge = 1.0 if vr20 >= 3.0 else 0.0
            ar = amounts[i]/a20 if a20 else 1.0

            # ATR
            atr_raw = grp["atr14"].iloc[i]
            atr_r   = _safe(atr_raw)/c if _safe(atr_raw) and c else c*0.02/c

            # RSI/MACD/BB — prefer precomputed, else 0
            rsi14      = _safe(grp["rsi14"].iloc[i],   50.0)
            macd_h     = _safe(grp.get("macd_hist", pd.Series([None]*len(grp))).iloc[i] if "macd_hist" in grp.columns
                               else (_safe(grp["macd"].iloc[i]) - _safe(grp["macd_signal"].iloc[i])))
            bb_up      = _safe(grp["bb_upper"].iloc[i], c*1.05)
            bb_lo      = _safe(grp["bb_lower"].iloc[i], c*0.95)
            bb_rng     = max(bb_up - bb_lo, 1.0)
            bb_pct     = (c - bb_lo)/bb_rng
            bb_width   = bb_rng/c if c else 0.0
            bb_squeeze = 1.0 if bb_width < 0.04 else 0.0
            rsi_os = 1.0 if rsi14 < 30 else 0.0
            rsi_ob = 1.0 if rsi14 > 70 else 0.0

            macd_prev = _safe(grp["macd"].iloc[i-1]) - _safe(grp["macd_signal"].iloc[i-1]) if i > 0 else macd_h
            macd_gc = 1.0 if macd_h > 0 and macd_prev <= 0 else 0.0

            # Candle
            o = opens[i]; body = abs(c-o); rng = max(highs[i]-lows[i],1.0)
            body_sz  = body/rng
            is_bull  = 1.0 if c > o else 0.0
            up_wick  = (highs[i]-max(c,o))/rng
            lo_wick  = (min(c,o)-lows[i])/rng

            # New high
            def is_nh(n):
                if i < n: return 0.0
                return 1.0 if c >= float(closes[i-n:i].max()) else 0.0
            nh20  = is_nh(20); nh52w = is_nh(130); nh260 = is_nh(260)
            c52hi = float(closes[max(0,i-130):i].max()) if i >= 2 else c
            c52lo = float(closes[max(0,i-130):i].min()) if i >= 2 else c
            pos52w = (c-c52lo)/(c52hi-c52lo) if c52hi != c52lo else 0.5

            # Supply
            f5  = f_nets[max(0,i-4):i+1].sum()
            f20 = f_nets[max(0,i-19):i+1].sum()
            i5  = i_nets[max(0,i-4):i+1].sum()
            i20 = i_nets[max(0,i-19):i+1].sum()
            db  = 1.0 if f5 > 0 and i5 > 0 else 0.0
            f3  = f_nets[max(0,i-2):i+1].sum()
            i3  = i_nets[max(0,i-2):i+1].sum()
            db3 = 1.0 if f3 > 0 and i3 > 0 else 0.0

            sv_arr = grp["short_sell_vol"].iloc[max(0,i-9):i+1].astype(float).fillna(0).values
            short_r = sv_arr[-1]/volumes[i] if volumes[i] else 0.0
            short_inc = 1.0 if (len(sv_arr) >= 6 and sv_arr[-3:].mean() > sv_arr[-6:-3].mean()+1) else 0.0

            # Disclosure
            date_val = grp["date"].iloc[i]
            disc_sub = disc_df[(disc_df["code"]==code) &
                                (disc_df["date"]>=pd.Timestamp(date_val)-pd.Timedelta(days=7)) &
                                (disc_df["date"]<=pd.Timestamp(date_val))]
            disc_s  = float(disc_sub["sentiment_score"].mean()) if len(disc_sub) > 0 else 0.0
            has_fav = 1.0 if len(disc_sub[disc_sub["category"]=="favorable"]) > 0 else 0.0

            # KOSPI
            kdate = pd.Timestamp(date_val)
            if len(kospi_df) >= 6:
                kidx = kospi_df.index.searchsorted(kdate, side="right") - 1
                if kidx >= 1:
                    kc = float(kospi_df["close"].iloc[kidx])
                    kc1 = float(kospi_df["close"].iloc[kidx-1])
                    kc5 = float(kospi_df["close"].iloc[max(0,kidx-5)])
                    kr1d = (kc/kc1-1)*100 if kc1 else 0.0
                    kr5d = (kc/kc5-1)*100 if kc5 else 0.0
                else:
                    kr1d = kr5d = 0.0
            else:
                kr1d = kr5d = 0.0
            rel5 = r5d - kr5d

            feat = {
                "return_1d":r1d, "return_3d":r3d, "return_5d":r5d,
                "ma5_ratio":ma5_r, "ma20_ratio":ma20_r, "ma60_ratio":ma60_r,
                "ma5_slope":ma5_sl, "ma20_slope":ma20_sl,
                "vol_ratio_5d":vr5, "vol_ratio_20d":vr20, "vol_surge":vsurge,
                "amount_ratio":ar, "atr_ratio":atr_r,
                "rsi14":rsi14, "rsi_oversold":rsi_os, "rsi_overbought":rsi_ob,
                "macd_hist":macd_h, "macd_golden_cross":macd_gc,
                "bb_pct":bb_pct, "bb_width":bb_width, "bb_squeeze":bb_squeeze,
                "body_size":body_sz, "is_bullish":is_bull, "upper_wick":up_wick, "lower_wick":lo_wick,
                "is_new_high_20d":nh20, "is_new_high_52d":nh52w, "is_new_high_260d":nh260,
                "pos_52w":pos52w,
                "foreign_cumnet_5d":f5, "foreign_cumnet_20d":f20,
                "inst_cumnet_5d":i5, "inst_cumnet_20d":i20,
                "dual_buy":db, "dual_buy_3d":db3,
                "short_ratio":short_r, "short_increasing":short_inc,
                "disclosure_sentiment":disc_s, "has_favorable_disclosure":has_fav,
                "kospi_return_1d":kr1d, "kospi_return_5d":kr5d,
                "rel_strength_5d":rel5, "market_vol_ratio":vr20,
                "__code": code, "__date": date_val, "__close": c,
            }
            rows_feat.append(feat)
        results.extend(rows_feat)

    return pd.DataFrame(results)


def make_labels(feat_df: pd.DataFrame, raw_df: pd.DataFrame,
                entry_pct: float = 5.0, risk_pct: float = 5.0) -> tuple[pd.Series, pd.Series]:
    """
    5일 후 수익률 기반 레이블 생성.
    entry: return_5d_fwd >= entry_pct
    risk:  return_5d_fwd <= -risk_pct
    데이터 누수 방지: 미래 수익률은 raw_df에서 직접 계산.
    """
    # close by (code, date)
    pivot = raw_df.pivot_table(index="date", columns="code", values="close")

    entry_labels = []
    risk_labels  = []

    for _, row in feat_df.iterrows():
        code  = row["__code"]
        date  = row["__date"]
        close = row["__close"]
        try:
            col   = pivot[code]
            idx   = col.index.searchsorted(pd.Timestamp(date))
            fwd5  = col.iloc[idx+5] if idx+5 < len(col) else None
            if fwd5 and close > 0 and not pd.isna(fwd5):
                ret5 = (float(fwd5)/float(close)-1)*100
                entry_labels.append(1 if ret5 >= entry_pct else 0)
                risk_labels.append(1 if ret5 <= -risk_pct else 0)
            else:
                entry_labels.append(None)
                risk_labels.append(None)
        except Exception:
            entry_labels.append(None)
            risk_labels.append(None)

    return pd.Series(entry_labels, dtype="float64"), pd.Series(risk_labels, dtype="float64")


# ── 검증 리포트 ───────────────────────────────────────────────────────────────

def report(name: str, model, X: pd.DataFrame, y: pd.Series, threshold: float = 0.5):
    prob = model.predict_proba(X)[:, 1]
    valid = y.notna()
    X_v = X[valid]; y_v = y[valid]; p_v = prob[valid.values]

    auc   = roc_auc_score(y_v, p_v)
    brier = brier_score_loss(y_v, p_v)
    pred  = (p_v >= threshold).astype(int)

    logger.info(f"[{name}] AUC={auc:.4f}  Brier={brier:.4f}  pos_rate={y_v.mean():.3f}")
    print(f"\n=== {name} 분류 리포트 ===")
    print(classification_report(y_v, pred, zero_division=0,
                                 target_names=["부정(0)", "긍정(1)"]))

    # 최적 임계값 (F1 기준)
    prec, rec, threshs = precision_recall_curve(y_v, p_v)
    f1 = 2*prec*rec/(prec+rec+1e-8)
    best_t = float(threshs[np.argmax(f1[:-1])]) if len(threshs) > 0 else threshold
    logger.info(f"[{name}] Best threshold (F1): {best_t:.3f}")
    return auc, brier, best_t


# ── 메인 ──────────────────────────────────────────────────────────────────────

async def main(args):
    from datetime import date as _date
    def _d(s: str) -> _date:
        return _date.fromisoformat(s)

    # 문자열 → datetime.date 변환 (asyncpg는 date 객체를 요구)
    train_start = _d(args.train_start); train_end = _d(args.train_end)
    val_start   = _d(args.val_start);   val_end   = _d(args.val_end)
    test_start  = _d(args.test_start);  test_end  = _d(args.test_end)
    all_start   = min(train_start, val_start, test_start)
    all_end     = max(train_end,   val_end,   test_end)

    pool = await asyncpg.create_pool(
        dsn=os.environ["POSTGRES_DSN"].replace("+asyncpg", ""),
        min_size=3, max_size=10,
    )
    logger.info("=== Walk-Forward Training ===")
    logger.info(f"Train: {train_start} ~ {train_end}")
    logger.info(f"Val:   {val_start} ~ {val_end}")
    logger.info(f"Test:  {test_start} ~ {test_end}")

    # 거래대금 상위 종목 선정 (메모리 제한: 훈련 기간 기준)
    logger.info(f"Selecting top {args.max_codes} liquid codes by train-period avg amount...")
    codes = await get_liquid_codes(pool, train_start, train_end, args.max_codes)
    logger.info(f"Selected {len(codes)} codes")

    # 데이터 로드
    logger.info("Loading data...")
    tr_raw   = await load_daily_bars(pool, train_start, train_end, codes)
    va_raw   = await load_daily_bars(pool, val_start,   val_end,   codes)
    te_raw   = await load_daily_bars(pool, test_start,  test_end,  codes)
    kospi_tr = await load_kospi(pool, train_start, train_end)
    kospi_va = await load_kospi(pool, val_start,   val_end)
    kospi_te = await load_kospi(pool, test_start,  test_end)
    disc_all = await load_disclosures(pool, all_start, all_end)
    await pool.close()

    logger.info(f"Raw data: train={len(tr_raw)} val={len(va_raw)} test={len(te_raw)}")

    # 피처 엔지니어링
    logger.info("Building features...")
    tr_feat = build_features(tr_raw, kospi_tr, disc_all)
    va_feat = build_features(va_raw, kospi_va, disc_all)
    te_feat = build_features(te_raw, kospi_te, disc_all)

    # 레이블 생성
    logger.info("Generating labels (5-day forward returns)...")
    tr_le, tr_lr = make_labels(tr_feat, tr_raw, args.entry_pct, args.risk_pct)
    va_le, va_lr = make_labels(va_feat, va_raw, args.entry_pct, args.risk_pct)
    te_le, te_lr = make_labels(te_feat, te_raw, args.entry_pct, args.risk_pct)

    # 피처 행렬 준비 (FEATURE_COLUMNS)
    def prep(feat_df, labels):
        mask = labels.notna()
        X = feat_df[mask][[c for c in FEATURE_COLUMNS if c in feat_df.columns]].copy()
        for col in FEATURE_COLUMNS:
            if col not in X.columns:
                X[col] = 0.0
        X = X[FEATURE_COLUMNS].replace([float("inf"), float("-inf")], 0.0).fillna(0.0)
        y = labels[mask].astype(int)
        return X, y

    Xtr_e, ytr_e = prep(tr_feat, tr_le)
    Xva_e, yva_e = prep(va_feat, va_le)
    Xte_e, yte_e = prep(te_feat, te_le)
    Xtr_r, ytr_r = prep(tr_feat, tr_lr)
    Xva_r, yva_r = prep(va_feat, va_lr)
    Xte_r, yte_r = prep(te_feat, te_lr)

    logger.info(f"Train: {len(Xtr_e)} | Val: {len(Xva_e)} | Test: {len(Xte_e)}")
    logger.info(f"Entry label pos rate — train:{ytr_e.mean():.3f} val:{yva_e.mean():.3f} test:{yte_e.mean():.3f}")
    logger.info(f"Risk  label pos rate — train:{ytr_r.mean():.3f} val:{yva_r.mean():.3f} test:{yte_r.mean():.3f}")

    # 학습
    Path(args.model_dir).mkdir(parents=True, exist_ok=True)
    trainer = LGBMTrainer()

    logger.info("Training entry model...")
    entry_model = trainer.train_entry(Xtr_e, ytr_e, Xva_e, yva_e, args.model_dir,
                                       use_smote=args.smote)
    logger.info("Training risk model...")
    risk_model  = trainer.train_risk(Xtr_r, ytr_r, Xva_r, yva_r, args.model_dir)

    # 검증 리포트
    print("\n" + "="*60)
    print("VALIDATION SET RESULTS (2024)")
    print("="*60)
    va_e_auc, va_e_brier, best_t_e = report("Entry [Val]",  entry_model, Xva_e, yva_e)
    va_r_auc, va_r_brier, best_t_r = report("Risk  [Val]",  risk_model,  Xva_r, yva_r)

    print("\n" + "="*60)
    print("TEST SET RESULTS (2025+) — 완전 홀드아웃")
    print("="*60)
    te_e_auc, te_e_brier, _ = report("Entry [Test]", entry_model, Xte_e, yte_e, best_t_e)
    te_r_auc, te_r_brier, _ = report("Risk  [Test]", risk_model,  Xte_r, yte_r, best_t_r)

    print(f"""
╔══════════════════════════════════════════════════════════╗
║           Walk-Forward 검증 요약                         ║
╠══════════════════════════════════════════════════════════╣
║ Entry Model  Val AUC={va_e_auc:.4f}  Test AUC={te_e_auc:.4f}  ║
║ Risk  Model  Val AUC={va_r_auc:.4f}  Test AUC={te_r_auc:.4f}  ║
║ Best Entry Threshold: {best_t_e:.3f}                          ║
║ Best Risk  Threshold: {best_t_r:.3f}                          ║
╚══════════════════════════════════════════════════════════╝
""")
    logger.info(f"Models saved to {args.model_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Walk-Forward ML Training")
    parser.add_argument("--train-start", default="2020-01-01")
    parser.add_argument("--train-end",   default="2023-12-31")
    parser.add_argument("--val-start",   default="2024-01-01")
    parser.add_argument("--val-end",     default="2024-12-31")
    parser.add_argument("--test-start",  default="2025-01-01")
    parser.add_argument("--test-end",    default="2026-06-06")
    parser.add_argument("--model-dir",   default="/models/lgbm")
    parser.add_argument("--entry-pct",   type=float, default=5.0,
                        help="진입 레이블 임계 수익률 %%")
    parser.add_argument("--risk-pct",    type=float, default=5.0,
                        help="리스크 레이블 임계 손실률 %%")
    parser.add_argument("--smote",       action="store_true",
                        help="SMOTE 오버샘플링 적용")
    parser.add_argument("--max-codes",   type=int, default=600,
                        help="거래대금 상위 N개 종목만 사용 (메모리 절감, 기본 600)")
    asyncio.run(main(parser.parse_args()))
