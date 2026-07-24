"""
장중 폴러 전용 LightGBM 스코어.

- LGBM_MODEL_DIR 경로의 모델 파일 지연 로딩
- daily_bars + Redis 통계만 사용 (뉴스·공시·재무는 0 기본값)
- 모델 미존재 시 (None, False) 반환 → 호출측 규칙 기반 점수 사용
"""
import json
import logging
import math
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("ml-scorer")

_MODEL_DIR = os.environ.get("LGBM_MODEL_DIR", "/lgbm_export")

_entry_model   = None
_entry_cal     = None
_FEATURE_COLS: list[str] = []
_model_checked = False


def _try_load() -> None:
    global _entry_model, _entry_cal, _FEATURE_COLS, _model_checked
    if _model_checked:
        return
    _model_checked = True

    p = Path(_MODEL_DIR)
    if not p.exists():
        logger.warning(f"[ml-scorer] 모델 디렉터리 없음: {_MODEL_DIR}")
        return

    fc_path = p / "feature_columns.json"
    if fc_path.exists():
        try:
            with open(fc_path) as f:
                _FEATURE_COLS = json.load(f)
            logger.info(f"[ml-scorer] feature_columns loaded: {len(_FEATURE_COLS)}개")
        except Exception as e:
            logger.warning(f"[ml-scorer] feature_columns.json 오류: {e}")

    try:
        import lightgbm as lgb
        ep = p / "entry_model.lgb"
        if ep.exists():
            _entry_model = lgb.Booster(model_file=str(ep))
            if not _FEATURE_COLS:
                _FEATURE_COLS = _entry_model.feature_name()
            logger.info(f"[ml-scorer] entry_model 로드 완료 ({len(_FEATURE_COLS)} features)")
        else:
            logger.warning(f"[ml-scorer] entry_model.lgb 없음: {ep}")
    except ImportError:
        logger.warning("[ml-scorer] lightgbm 미설치 — ML 스코어링 비활성")
    except Exception as e:
        logger.error(f"[ml-scorer] 모델 로드 오류: {e}")

    try:
        import joblib
        import warnings
        ecp = p / "entry_calibrator.pkl"
        if ecp.exists():
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*unpickle.*")
                _entry_cal = joblib.load(str(ecp))
            logger.info("[ml-scorer] entry_calibrator 로드 완료")
    except Exception as e:
        logger.warning(f"[ml-scorer] calibrator 오류: {e}")


# ── 피처 계산 (ml_client._compute_features와 동일 로직) ──────────────

def _safe(v, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _build_features(bars: list[dict], is_kosdaq: float,
                    kospi_rets: tuple | None) -> dict:
    """daily_bars rows (최신→과거 순) → FEATURE_COLS dict."""
    if not bars:
        return {k: 0.0 for k in _FEATURE_COLS}

    closes  = [_safe(r.get("close"))  for r in bars]
    volumes = [_safe(r.get("volume")) for r in bars]
    amounts = [_safe(r.get("amount")) for r in bars]
    highs   = [_safe(r.get("high"))   for r in bars]
    lows    = [_safe(r.get("low"))    for r in bars]
    opens   = [_safe(r.get("open"))   for r in bars]
    c = closes[0]

    def ret(n: int) -> float:
        return (closes[0] / closes[n] - 1) * 100 if len(closes) > n and closes[n] else 0.0

    return_1d  = ret(1);  return_3d  = ret(3)
    return_5d  = ret(5);  return_10d = ret(10);  return_20d = ret(20)

    def ma(n: int) -> float:
        v = closes[:n]; return sum(v) / len(v) if v else c
    ma5 = ma(5); ma20 = ma(20); ma60 = ma(60)
    ma5_ratio  = c / ma5  if ma5  else 1.0
    ma20_ratio = c / ma20 if ma20 else 1.0
    ma60_ratio = c / ma60 if ma60 else 1.0
    ma5_slope  = (ma(5) / ma(min(10, len(closes))) - 1) if len(closes) >= 5  else 0.0
    ma20_slope = (ma(20) / ma(min(40, len(closes))) - 1) if len(closes) >= 20 else 0.0

    prior5      = (closes[0] / closes[10] - 1) * 100 if len(closes) > 10 and closes[10] else 0.0
    price_accel = return_5d - prior5
    gap_pct     = (opens[0] / closes[1] - 1) * 100 if len(closes) > 1 and closes[1] else 0.0

    consec_up = consec_down = 0
    for i in range(1, min(len(closes), 20)):
        if   closes[i-1] > closes[i]:
            if consec_down == 0: consec_up   += 1
            else: break
        elif closes[i-1] < closes[i]:
            if consec_up   == 0: consec_down += 1
            else: break
        else:
            break

    vol5  = sum(volumes[:5])  / 5  if len(volumes) >= 5  else volumes[0]
    vol20 = sum(volumes[:20]) / 20 if len(volumes) >= 20 else volumes[0]
    amt20 = sum(amounts[:20]) / 20 if len(amounts) >= 20 else amounts[0]
    vol_ratio_5d  = volumes[0] / vol5  if vol5  else 1.0
    vol_ratio_20d = volumes[0] / vol20 if vol20 else 1.0
    vol_surge     = 1.0 if vol_ratio_20d >= 3.0 else 0.0
    amount_ratio  = amounts[0] / amt20 if amt20 else 1.0

    up_vols   = [volumes[i] for i in range(1, min(20, len(volumes))) if closes[i-1] >= closes[i]]
    down_vols = [volumes[i] for i in range(1, min(20, len(volumes))) if closes[i-1] <  closes[i]]
    avg_up    = sum(up_vols)   / len(up_vols)   if up_vols   else 1.0
    avg_down  = sum(down_vols) / len(down_vols) if down_vols else 1.0
    vol_up_down_ratio = avg_up / avg_down if avg_down else 1.0

    def ma_prev(n: int, offset: int = 1) -> float:
        v = closes[offset:offset + n]
        return sum(v) / len(v) if v else (closes[offset] if len(closes) > offset else c)
    ma5_ma20_cross  = 1.0 if ma5 > ma20 and ma_prev(5)  <= ma_prev(20)  else 0.0
    ma20_ma60_cross = 1.0 if ma20 > ma60 and ma_prev(20) <= ma_prev(60) else 0.0

    atrs = [highs[i] - lows[i] for i in range(min(14, len(highs)))]
    atr  = sum(atrs) / len(atrs) if atrs else c * 0.02
    atr_ratio = atr / c if c else 0.0

    rsi14          = _safe(bars[0].get("rsi14"), 50.0)
    rsi_oversold   = 1.0 if rsi14 < 30 else 0.0
    rsi_overbought = 1.0 if rsi14 > 70 else 0.0

    macd_h  = _safe(bars[0].get("macd_hist"))
    macd_ph = _safe(bars[1].get("macd_hist")) if len(bars) > 1 else macd_h
    macd_hist         = macd_h
    macd_golden_cross = 1.0 if macd_h > 0 and macd_ph <= 0 else 0.0

    bb_up  = _safe(bars[0].get("bb_upper"), c * 1.05)
    bb_lo  = _safe(bars[0].get("bb_lower"), c * 0.95)
    bb_rng = max(bb_up - bb_lo, 1.0)
    bb_pct    = (c - bb_lo) / bb_rng
    bb_width  = bb_rng / c if c else 0.0
    bb_squeeze = 1.0 if bb_width < 0.04 else 0.0

    o = opens[0]; body = abs(c - o); rng = max(highs[0] - lows[0], 1.0)
    body_size  = body / rng
    is_bullish = 1.0 if c > o else 0.0
    upper_wick = (highs[0] - max(c, o)) / rng
    lower_wick = (min(c, o) - lows[0])  / rng

    def is_new_high(n: int) -> float:
        if len(closes) <= n: return 0.0
        return 1.0 if c >= max(closes[1:n+1]) else 0.0
    is_new_high_20d  = is_new_high(20)
    is_new_high_52d  = is_new_high(130)
    is_new_high_260d = is_new_high(260)
    high52 = max(closes[1:131]) if len(closes) > 131 else c
    low52  = min(closes[1:131]) if len(closes) > 131 else c
    pos_52w = (c - low52) / (high52 - low52) if high52 != low52 else 0.5

    # 수급 — daily_bars 컬럼 fallback (supply_demand 테이블 없음)
    fnets  = [_safe(r.get("foreign_net_buy")) for r in bars]
    inets  = [_safe(r.get("inst_net_buy"))    for r in bars]
    f5  = sum(fnets[:5]);   f20 = sum(fnets[:20])
    i5  = sum(inets[:5]);   i20 = sum(inets[:20])
    foreign_cumnet_5d  = f5;   foreign_cumnet_20d = f20
    inst_cumnet_5d     = i5;   inst_cumnet_20d    = i20
    f3  = sum(fnets[:3]);   i3  = sum(inets[:3])
    dual_buy     = 1.0 if f5 > 0 and i5 > 0 else 0.0
    dual_buy_3d  = 1.0 if f3 > 0 and i3 > 0 else 0.0
    short_vol    = _safe(bars[0].get("short_sell_vol"))
    short_ratio  = short_vol / volumes[0] if volumes[0] else 0.0

    shorts = [_safe(b.get("short_sell_vol")) for b in bars[:10]]
    if len(shorts) >= 6:
        short_increasing = 1.0 if (sum(shorts[:3]) / 3) > (sum(shorts[3:6]) / 3 + 1) else 0.0
    else:
        short_increasing = 0.0

    _fstreak = 0
    for _fn in fnets[:20]:
        if   _fn > 0:
            if _fstreak >= 0: _fstreak += 1
            else: break
        elif _fn < 0:
            if _fstreak <= 0: _fstreak -= 1
            else: break
        else:
            break
    foreign_cumnet_streak = float(_fstreak)

    foreign_net_ratio = fnets[0] / (volumes[0] + 1)
    inst_net_ratio    = inets[0] / (volumes[0] + 1)

    disclosure_sentiment     = 0.0
    has_favorable_disclosure = 0.0

    if kospi_rets:
        kr1d, kr3d, kr5d, kr10d, kr20d, kospi_vol_5d = kospi_rets
    else:
        kr1d = kr3d = kr5d = kr10d = kr20d = kospi_vol_5d = 0.0
    rel_strength_1d  = return_1d  - kr1d
    rel_strength_3d  = return_3d  - kr3d
    rel_strength_5d  = return_5d  - kr5d
    rel_strength_10d = return_10d - kr10d
    rel_strength_20d = return_20d - kr20d
    market_vol_ratio = vol_ratio_20d
    market_phase     = 0.0  # KOSPI bars 미사용 — 중립

    _now   = datetime.now()
    dow    = _now.weekday()
    month  = _now.month
    dow_sin   = math.sin(2 * math.pi * dow / 7)
    dow_cos   = math.cos(2 * math.pi * dow / 7)
    month_sin = math.sin(2 * math.pi * (month - 1) / 12)
    month_cos = math.cos(2 * math.pi * (month - 1) / 12)

    news_sentiment_7d = 0.0
    news_count_7d     = 0.0
    per = pbr = roe = debt_ratio = 0.0

    _mc = _safe(bars[0].get("market_cap"))
    log_market_cap = math.log(_mc) if _mc > 0 else 0.0

    rank_return_5d = rank_vol_ratio = rank_foreign_net = rank_rsi14 = 0.5

    return {k: locals().get(k, 0.0) for k in _FEATURE_COLS}


# ── 공개 API ──────────────────────────────────────────────────────

async def score_event(db, redis, code: str, price: int) -> tuple[float | None, bool]:
    """
    Returns (success_prob, model_used).
    (None, False) → 모델 미사용, 호출측 규칙 점수 유지.
    """
    _try_load()
    if not _FEATURE_COLS or _entry_model is None:
        return None, False

    try:
        bars_raw = await db.fetch(
            """
            SELECT close, open, high, low, volume, amount,
                   rsi14, macd, macd_signal,
                   (macd - macd_signal) AS macd_hist,
                   bb_upper, bb_lower, ma5, ma20, ma60,
                   foreign_net_buy, inst_net_buy, short_sell_vol,
                   COALESCE(market_cap, 0) AS market_cap
            FROM daily_bars
            WHERE code=$1 ORDER BY date DESC LIMIT 280
            """,
            code,
        )
    except Exception as e:
        logger.warning(f"[ml-scorer] DB 조회 실패 {code}: {e}")
        return None, False

    if not bars_raw:
        return None, False

    bars = [dict(r) for r in bars_raw]

    # Redis에서 KOSPI 수익률 조회 (optional)
    kospi_rets = None
    try:
        r1d = await redis.get("market:kospi_return_1d")
        r5d = await redis.get("market:kospi_return_5d")
        if r1d and r5d:
            r3d  = await redis.get("market:kospi_return_3d")
            r10d = await redis.get("market:kospi_return_10d")
            r20d = await redis.get("market:kospi_return_20d")
            rvol = await redis.get("market:kospi_vol_5d")
            kospi_rets = (
                float(r1d),
                float(r3d)  if r3d  else 0.0,
                float(r5d),
                float(r10d) if r10d else 0.0,
                float(r20d) if r20d else 0.0,
                float(rvol) if rvol else 0.0,
            )
    except Exception:
        pass

    is_kosdaq = 0.0
    try:
        row = await db.fetchrow("SELECT market FROM stocks WHERE code=$1", code)
        if row and row["market"] == "KOSDAQ":
            is_kosdaq = 1.0
    except Exception:
        pass

    try:
        feats = _build_features(bars, is_kosdaq, kospi_rets)
    except Exception as e:
        logger.warning(f"[ml-scorer] 피처 계산 실패 {code}: {e}")
        return None, False

    try:
        import numpy as np
        import pandas as pd
        X = pd.DataFrame([feats])[_FEATURE_COLS].fillna(0.0)
        raw_prob = float(np.clip(_entry_model.predict(X)[0], 0.0, 1.0))
        prob = float(np.clip(_entry_cal.predict([raw_prob])[0], 0.0, 1.0)) if _entry_cal else raw_prob
        return round(prob, 4), True
    except Exception as e:
        logger.warning(f"[ml-scorer] 추론 실패 {code}: {e}")
        return None, False
