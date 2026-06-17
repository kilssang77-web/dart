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
import math
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
from shared.feature_schema import DEFAULT_FEATURE_COLUMNS as FEATURE_COLUMNS
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
            d.market_cap,
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
    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")


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


async def load_financials(pool: asyncpg.Pool) -> pd.DataFrame:
    """분기별 재무 데이터 로드 (전체 기간, 날짜 변환 포함)."""
    rows = await pool.fetch(
        "SELECT code, year, quarter, per, pbr, roe, debt_ratio FROM financials"
    )
    if not rows:
        return pd.DataFrame(columns=["code", "quarter_date", "per", "pbr", "roe", "debt_ratio"])
    df = pd.DataFrame([dict(r) for r in rows])
    qend_month = {1: 3, 2: 6, 3: 9, 4: 12}
    qend_day   = {1: 31, 2: 30, 3: 30, 4: 31}
    df["quarter_date"] = pd.to_datetime(
        df["year"].astype(str) + "-"
        + df["quarter"].map(qend_month).astype(str).str.zfill(2) + "-"
        + df["quarter"].map(qend_day).astype(str).str.zfill(2)
    )
    return df.sort_values(["code", "quarter_date"]).reset_index(drop=True)


async def load_news_sentiment(pool: asyncpg.Pool, start, end) -> pd.DataFrame:
    rows = await pool.fetch(
        """
        SELECT nsl.code, DATE(n.published_at) AS date,
               AVG(n.sentiment_score) AS avg_sentiment,
               COUNT(*) AS news_count
        FROM news n
        JOIN news_stock_links nsl ON nsl.news_id = n.id
        WHERE n.published_at BETWEEN $1::date AND $2::date
          AND n.sentiment_score IS NOT NULL
        GROUP BY nsl.code, DATE(n.published_at)
        """,
        start, end,
    )
    if not rows:
        return pd.DataFrame(columns=["code", "date", "avg_sentiment", "news_count"])
    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    return df


# ── 피처 엔지니어링 ───────────────────────────────────────────────────────────

def _safe(v, default=0.0):
    try:
        f = float(v)
        import math
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return default


def build_features(df: pd.DataFrame, kospi_df: pd.DataFrame, disc_df: pd.DataFrame,
                   news_df: pd.DataFrame | None = None,
                   fin_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    daily_bars DataFrame → 특징 행렬 (FEATURE_COLUMNS 기준).
    종목별 순서 정렬 후 롤링 계산.
    """
    df = df.sort_values(["code", "date"]).reset_index(drop=True)

    # Pre-group disclosures by code for O(log N) per-row lookup (avoid O(N²) full scan)
    disc_by_code: dict = {}
    if len(disc_df) > 0 and "date" in disc_df.columns:
        _ddf = disc_df.copy()
        _ddf["date"] = pd.to_datetime(_ddf["date"])
        for _dc, _dg in _ddf.groupby("code"):
            disc_by_code[_dc] = _dg.sort_values("date").reset_index(drop=True)

    # Pre-group financials by code for quarterly data lookup (O(log N) via searchsorted)
    fin_by_code: dict = {}
    if fin_df is not None and len(fin_df) > 0:
        for _fc, _fg in fin_df.groupby("code"):
            fin_by_code[_fc] = _fg.sort_values("quarter_date").reset_index(drop=True)

    # Pre-group news data by code for O(log N) per-row lookup
    news_by_code: dict = {}
    if news_df is not None and len(news_df) > 0:
        _ndf = news_df.copy()
        _ndf["date"] = pd.to_datetime(_ndf["date"])
        for _nc, _ng in _ndf.groupby("code"):
            news_by_code[_nc] = _ng.sort_values("date").reset_index(drop=True)

    chunk_frames: list[pd.DataFrame] = []
    _float_meta = ("__code", "__date")
    for code, grp in df.groupby("code"):
        grp = grp.reset_index(drop=True)
        if len(grp) < 62:  # range(60,...) 시작 → 최소 2개 행 보장
            continue

        closes  = grp["close"].astype(float).values
        volumes = grp["volume"].astype(float).fillna(0).values
        amounts = grp["amount"].astype(float).fillna(0).values
        highs   = grp["high"].astype(float).values
        lows    = grp["low"].astype(float).values
        opens   = grp["open"].astype(float).values
        f_nets  = grp["foreign_net"].astype(float).fillna(0).values
        i_nets  = grp["inst_net"].astype(float).fillna(0).values

        # Pre-extract disclosure data for this code (O(log N) per row via searchsorted)
        disc_code_df = disc_by_code.get(code)
        disc_dates_np = disc_code_df["date"].values if disc_code_df is not None else None

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

            # Disclosure (O(log N) via pre-grouped searchsorted)
            date_val = grp["date"].iloc[i]
            disc_s = 0.0; has_fav = 0.0
            if disc_dates_np is not None:
                _ts_disc = pd.Timestamp(date_val)
                _d_lo = np.searchsorted(disc_dates_np, np.datetime64(_ts_disc - pd.Timedelta(days=7)), side="left")
                _d_hi = np.searchsorted(disc_dates_np, np.datetime64(_ts_disc), side="right")
                if _d_hi > _d_lo:
                    _ds = disc_code_df.iloc[_d_lo:_d_hi]
                    disc_s  = float(_ds["sentiment_score"].mean())
                    has_fav = 1.0 if (_ds["category"] == "favorable").any() else 0.0

            # KOSPI
            kdate = pd.Timestamp(date_val)
            if len(kospi_df) >= 6:
                kidx = kospi_df.index.searchsorted(kdate, side="right") - 1
                if kidx >= 1:
                    kc   = float(kospi_df["close"].iloc[kidx])
                    kc1  = float(kospi_df["close"].iloc[max(0, kidx-1)])
                    kc3  = float(kospi_df["close"].iloc[max(0, kidx-3)])
                    kc5  = float(kospi_df["close"].iloc[max(0, kidx-5)])
                    kc10 = float(kospi_df["close"].iloc[max(0, kidx-10)])
                    kc20 = float(kospi_df["close"].iloc[max(0, kidx-20)])
                    kr1d  = (kc/kc1  - 1)*100 if kc1  else 0.0
                    kr3d  = (kc/kc3  - 1)*100 if kc3  else 0.0
                    kr5d  = (kc/kc5  - 1)*100 if kc5  else 0.0
                    kr10d = (kc/kc10 - 1)*100 if kc10 else 0.0
                    kr20d = (kc/kc20 - 1)*100 if kc20 else 0.0
                    # KOSPI 5일 변동성 (방향 아닌 시장 불확실성 지표)
                    ks5 = [float(kospi_df["close"].iloc[max(0, kidx-j)]) for j in range(5)]
                    kospi_vol_5d = float(np.std([(ks5[j]/ks5[j+1]-1)*100 for j in range(len(ks5)-1)])) if len(ks5) >= 2 else 0.0
                else:
                    kr1d = kr3d = kr5d = kr10d = kr20d = kospi_vol_5d = 0.0
            else:
                kr1d = kr3d = kr5d = kr10d = kr20d = kospi_vol_5d = 0.0
            rel5 = r5d - kr5d

            # Medium-term momentum
            r10d = ret(10) if i >= 10 else 0.0
            r20d = ret(20) if i >= 20 else 0.0

            # Price acceleration: recent 5d momentum vs prior 5d momentum
            prior5 = (closes[i-5]/closes[i-10]-1)*100 if (i >= 10 and closes[i-10] > 0) else 0.0
            price_accel = r5d - prior5

            # Gap: today open vs yesterday close
            gap_pct = (opens[i]/closes[i-1]-1)*100 if (i >= 1 and closes[i-1] > 0) else 0.0

            # Consecutive up/down days (last 10)
            consec_up = 0; consec_down = 0
            for j in range(i, max(i-10, 0), -1):
                if j > 0 and closes[j] > closes[j-1]:
                    consec_up += 1
                else:
                    break
            for j in range(i, max(i-10, 0), -1):
                if j > 0 and closes[j] < closes[j-1]:
                    consec_down += 1
                else:
                    break

            # Volume on up vs down days ratio (last 10 days)
            up_vol = sum(volumes[j] for j in range(max(i-9,1), i+1) if closes[j] > closes[j-1])
            dn_vol = sum(volumes[j] for j in range(max(i-9,1), i+1) if closes[j] < closes[j-1])
            vol_ud_r = up_vol / dn_vol if dn_vol > 0 else 1.0

            # MA crossover signals
            ma5_prev  = float(closes[max(0,i-5):i].mean())   if i >= 1 else c
            ma20_prev = float(closes[max(0,i-20):i].mean())  if i >= 1 else c
            ma60_prev = float(closes[max(0,i-60):i].mean())  if i >= 1 else c
            ma5_ma20_cross  = 1.0 if (ma5 >= ma20 and ma5_prev < ma20_prev) else 0.0
            ma20_ma60_cross = 1.0 if (ma20 >= ma60 and ma20_prev < ma60_prev) else 0.0

            # Normalized net buy (divide by 20d avg amount to make cross-stock comparable)
            a20_safe = a20 if a20 > 0 else 1.0
            foreign_net_ratio = f5 / a20_safe
            inst_net_ratio    = i5 / a20_safe

            # Cyclical time features (day-of-week, month)
            _ts = pd.Timestamp(date_val)
            _dow = _ts.weekday()       # 0=Mon, 4=Fri
            _mon = _ts.month           # 1-12
            dow_sin   = math.sin(2 * math.pi * _dow / 7)
            dow_cos   = math.cos(2 * math.pi * _dow / 7)
            month_sin = math.sin(2 * math.pi * (_mon - 1) / 12)
            month_cos = math.cos(2 * math.pi * (_mon - 1) / 12)

            # Market cap size factor
            mc_raw = _safe(grp["market_cap"].iloc[i]) if "market_cap" in grp.columns else 0.0
            log_market_cap = math.log(mc_raw) if mc_raw > 0 else 0.0

            # Financials (quarterly — most recent quarter before current date)
            per_v = pbr_v = roe_v = debt_r = 0.0
            if code in fin_by_code:
                _fg    = fin_by_code[code]
                _fdate = np.datetime64(pd.Timestamp(date_val))
                _fidx  = np.searchsorted(_fg["quarter_date"].values, _fdate, side="right") - 1
                if _fidx >= 0:
                    _fr    = _fg.iloc[_fidx]
                    per_v  = _safe(_fr.get("per"))
                    pbr_v  = _safe(_fr.get("pbr"))
                    roe_v  = _safe(_fr.get("roe"))
                    debt_r = _safe(_fr.get("debt_ratio"))

            # News sentiment features (7d lookback, O(log N) via searchsorted)
            news_s7 = 0.0
            news_c7 = 0.0
            if code in news_by_code:
                _ng    = news_by_code[code]
                _dates = _ng["date"].values
                _t     = _ts
                _lo    = np.searchsorted(_dates, np.datetime64(_t - pd.Timedelta(days=7)), side="left")
                _hi    = np.searchsorted(_dates, np.datetime64(_t), side="right")
                if _hi > _lo:
                    news_s7 = float(_ng["avg_sentiment"].iloc[_lo:_hi].mean())
                    news_c7 = float(_ng["news_count"].iloc[_lo:_hi].sum())

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
                "rel_strength_1d":r1d - kr1d, "rel_strength_3d":r3d - kr3d,
                "rel_strength_5d":rel5, "rel_strength_10d":r10d - kr10d,
                "rel_strength_20d":r20d - kr20d,
                "kospi_vol_5d": kospi_vol_5d,
                "market_vol_ratio":vr20,
                "return_10d": r10d, "return_20d": r20d,
                "price_accel": price_accel,
                "gap_pct": gap_pct,
                "consec_up": float(consec_up), "consec_down": float(consec_down),
                "vol_up_down_ratio": vol_ud_r,
                "ma5_ma20_cross": ma5_ma20_cross, "ma20_ma60_cross": ma20_ma60_cross,
                "foreign_net_ratio": foreign_net_ratio, "inst_net_ratio": inst_net_ratio,
                "dow_sin": dow_sin, "dow_cos": dow_cos,
                "month_sin": month_sin, "month_cos": month_cos,
                "news_sentiment_7d": news_s7, "news_count_7d": news_c7,
                "per": per_v, "pbr": pbr_v, "roe": roe_v, "debt_ratio": debt_r,
                "log_market_cap": log_market_cap,
                "__code": code, "__date": date_val, "__close": c,
            }
            rows_feat.append(feat)

        if rows_feat:
            _cdf = pd.DataFrame(rows_feat)
            # Downcast per-code immediately to halve peak memory (float64→float32)
            _fc = [c for c in _cdf.columns if c not in _float_meta]
            _cdf[_fc] = _cdf[_fc].astype("float32")
            chunk_frames.append(_cdf)
        del rows_feat  # release per-code list

    return pd.concat(chunk_frames, ignore_index=True) if chunk_frames else pd.DataFrame()


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
    news_all = await load_news_sentiment(pool, all_start, all_end)
    fin_all  = await load_financials(pool)
    await pool.close()

    logger.info(f"Raw data: train={len(tr_raw)} val={len(va_raw)} test={len(te_raw)}")
    logger.info(f"News sentiment: {len(news_all)} (code,date) pairs")
    logger.info(f"Financials: {len(fin_all)} (code,quarter) records")

    # 피처 엔지니어링
    logger.info("Building features...")
    tr_feat = build_features(tr_raw, kospi_tr, disc_all, news_all, fin_all)
    va_feat = build_features(va_raw, kospi_va, disc_all, news_all, fin_all)
    te_feat = build_features(te_raw, kospi_te, disc_all, news_all, fin_all)

    # 레이블 생성
    logger.info("Generating labels (5-day forward returns)...")
    tr_le, tr_lr = LGBMTrainer.make_labels_bulk(tr_feat, tr_raw, args.entry_pct, args.risk_pct)
    va_le, va_lr = LGBMTrainer.make_labels_bulk(va_feat, va_raw, args.entry_pct, args.risk_pct)
    te_le, te_lr = LGBMTrainer.make_labels_bulk(te_feat, te_raw, args.entry_pct, args.risk_pct)

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
    # Feature importance
    if entry_model is not None:
        imp = pd.Series(
            entry_model.feature_importances_,
            index=[c for c in FEATURE_COLUMNS if c in Xtr_e.columns],
        ).sort_values(ascending=False)
        print("\n=== Entry Model Top-20 Feature Importance ===")
        print(imp.head(20).to_string())

    logger.info(f"Models saved to {args.model_dir}")

    # ── Redis 핫리로드 신호 (ml/main.py의 _model_watch_loop가 감지) ──────────
    try:
        import redis as _redis_lib
        _redis_url = os.environ.get("REDIS_URL", "")
        if _redis_url:
            _r = _redis_lib.from_url(_redis_url)
            _r.set("ml:model_updated", "1", ex=3600)
            _r.close()
            logger.info("[Retrain] Redis ml:model_updated 신호 전송 완료")
    except Exception as _re:
        logger.warning(f"[Retrain] Redis 신호 전송 실패 (비필수): {_re}")

    # ── ml_models 테이블 기록 ─────────────────────────────────────────────────
    import json as _json2
    from datetime import datetime as _dt, timezone as _tz
    _dsn = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    _pool2 = await asyncpg.create_pool(dsn=_dsn, min_size=1, max_size=3)
    try:
        _metrics = {
            "auc":           round(float(va_e_auc), 4),
            "val_auc":       round(float(va_e_auc), 4),
            "test_auc":      round(float(te_e_auc), 4),
            "brier":         round(float(va_e_brier), 4),
            "risk_val_auc":  round(float(va_r_auc), 4),
            "risk_test_auc": round(float(te_r_auc), 4),
            "entry_threshold": round(float(best_t_e), 3),
            "risk_threshold":  round(float(best_t_r), 3),
            "n_train": int(len(Xtr_e)),
            "n_val":   int(len(Xva_e)),
            "n_test":  int(len(Xte_e)),
        }
        _version = f"wf-{_dt.now(_tz.utc).strftime('%Y%m%d')}"
        _model_id = await _pool2.fetchval(
            """
            INSERT INTO ml_models
                (model_type, version, trained_at, metrics, feature_names, model_path, is_active)
            VALUES ($1, $2, NOW(), $3::jsonb, $4::jsonb, $5, TRUE)
            RETURNING id
            """,
            "LightGBM (Entry+Risk)",
            _version,
            _json2.dumps(_metrics),
            _json2.dumps(list(FEATURE_COLUMNS)),
            str(args.model_dir),
        )
        await _pool2.execute("UPDATE ml_models SET is_active=FALSE WHERE id != $1", _model_id)
        logger.info(f"ml_models 기록 완료: id={_model_id}, version={_version}, auc={_metrics['auc']}")
    except Exception as _e:
        logger.warning(f"ml_models 기록 실패 (비치명적): {_e}")
    finally:
        await _pool2.close()

    # ── 피처 컬럼 일관성 검증 ──────────────────────────────────────────────────
    # 저장된 feature_columns.json vs 이 스크립트의 FEATURE_COLUMNS 비교
    # 불일치 시 추론 시 피처 순서/구성이 달라져 모델 성능이 크게 저하됨
    import json as _json
    _fc_path = Path(args.model_dir) / "feature_columns.json"
    if _fc_path.exists():
        _saved = _json.loads(_fc_path.read_text())
        _train_set  = set(FEATURE_COLUMNS)
        _saved_set  = set(_saved)
        _only_train = _train_set - _saved_set
        _only_saved = _saved_set - _train_set
        if _only_train or _only_saved:
            logger.warning(
                f"[FEATURE MISMATCH] 학습({len(FEATURE_COLUMNS)}) vs 저장({len(_saved)}) 불일치!"
                f"\n  학습에만 있음: {_only_train}"
                f"\n  저장에만 있음: {_only_saved}"
            )
        else:
            logger.info(f"[FEATURE OK] {len(FEATURE_COLUMNS)}개 피처 컬럼 검증 통과")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Walk-Forward ML Training")
    parser.add_argument("--train-start", default="2020-01-01")
    parser.add_argument("--train-end",   default="2023-12-31")
    parser.add_argument("--val-start",   default="2024-01-01")
    parser.add_argument("--val-end",     default="2024-12-31")
    parser.add_argument("--test-start",  default="2025-01-01")
    parser.add_argument("--test-end",    default="2026-06-06")
    parser.add_argument("--model-dir",   default="/models/lgbm")
    parser.add_argument("--entry-pct",   type=float, default=3.0,
                        help="진입 레이블 임계 수익률 %% (기본 3.0 → 양성 비율 ~6-8%%)")
    parser.add_argument("--risk-pct",    type=float, default=5.0,
                        help="리스크 레이블 임계 손실률 %%")
    parser.add_argument("--smote",       action="store_true",
                        help="SMOTE 오버샘플링 적용")
    parser.add_argument("--max-codes",   type=int, default=600,
                        help="거래대금 상위 N개 종목만 사용 (메모리 절감, 기본 600)")
    asyncio.run(main(parser.parse_args()))
