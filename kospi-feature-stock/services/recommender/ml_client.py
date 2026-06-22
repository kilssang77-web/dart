"""
ML 추론 클라이언트.
- /models/lgbm/{entry,risk}_model.lgb 존재 시 → LightGBM + Isotonic Calibration
- 모델 미학습 상태 시 → 규칙 기반 fallback (서비스 재시작 불필요)
"""
import json
import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import asyncpg
import numpy as np

logger = logging.getLogger(__name__)

_MODEL_DIR = os.environ.get("LGBM_MODEL_DIR", "/models/lgbm")
_ML_SERVICE_URL = os.environ.get("ML_SERVICE_URL", "")  # e.g. "http://ml:8001"

# 기본값 — feature_columns.json 로드 성공 시 동적으로 교체됨 (lgbm_predictor.py와 동기화)
FEATURE_COLUMNS: list[str] = [
    "return_1d", "return_3d", "return_5d", "return_10d", "return_20d",
    "ma5_ratio", "ma20_ratio", "ma60_ratio",
    "ma5_slope", "ma20_slope",
    "vol_ratio_5d", "vol_ratio_20d", "vol_surge",
    "amount_ratio",
    "atr_ratio",
    "rsi14", "rsi_oversold", "rsi_overbought",
    "macd_hist", "macd_golden_cross",
    "bb_pct", "bb_width", "bb_squeeze",
    "body_size", "is_bullish", "upper_wick", "lower_wick",
    "is_new_high_20d", "is_new_high_52d", "is_new_high_260d",
    "pos_52w",
    "foreign_cumnet_5d", "foreign_cumnet_20d",
    "foreign_cumnet_streak",
    "inst_cumnet_5d", "inst_cumnet_20d",
    "dual_buy", "dual_buy_3d",
    "short_ratio", "short_increasing",
    "disclosure_sentiment", "has_favorable_disclosure",
    "rel_strength_1d", "rel_strength_3d", "rel_strength_5d",
    "rel_strength_10d", "rel_strength_20d",
    "kospi_vol_5d",
    "market_vol_ratio",
    "market_phase",
    "price_accel",
    "gap_pct",
    "consec_up", "consec_down",
    "vol_up_down_ratio",
    "ma5_ma20_cross", "ma20_ma60_cross",
    "foreign_net_ratio", "inst_net_ratio",
    "dow_sin", "dow_cos", "month_sin", "month_cos",
    "news_sentiment_7d", "news_count_7d",
    "per", "pbr", "roe", "debt_ratio",
    "log_market_cap",
]


@dataclass
class MLResult:
    success_prob: float = 0.5
    risk_score: float = 0.4
    expected_return: float = 0.0
    hold_days: int = 5
    confidence: float = 0.0
    model_used: bool = False
    atr_ratio: float = 0.0


# ── 모델 지연 로딩 ────────────────────────────────────────────────

_entry_model = None
_risk_model  = None
_entry_cal   = None
_risk_cal    = None
_model_checked = False


def _try_load_models():
    global _entry_model, _risk_model, _entry_cal, _risk_cal, _model_checked, FEATURE_COLUMNS
    if _model_checked:
        return
    _model_checked = True
    model_path = Path(_MODEL_DIR)

    # feature_columns.json — 단일 소스 오브 트루스
    fc_path = model_path / "feature_columns.json"
    if fc_path.exists():
        try:
            with open(fc_path) as f:
                cols = json.load(f)
            if cols:
                FEATURE_COLUMNS = cols
                logger.info(f"[MLClient] feature_columns.json loaded: {len(FEATURE_COLUMNS)} features")
        except Exception as e:
            logger.warning(f"[MLClient] feature_columns.json read error: {e}")

    try:
        import lightgbm as lgb
        ep = model_path / "entry_model.lgb"
        rp = model_path / "risk_model.lgb"
        if ep.exists():
            _entry_model = lgb.Booster(model_file=str(ep))
            # feature_columns.json 없을 경우 모델에서 직접 로드
            if not fc_path.exists():
                model_features = _entry_model.feature_name()
                if model_features:
                    FEATURE_COLUMNS = model_features
            logger.info(f"[MLClient] entry_model loaded, features={len(FEATURE_COLUMNS)}")
        else:
            logger.warning(f"[MLClient] entry_model NOT found at {ep} — rule-based fallback")
        if rp.exists():
            _risk_model = lgb.Booster(model_file=str(rp))
            logger.info(f"[MLClient] risk_model loaded from {rp}")
    except ImportError:
        logger.warning("[MLClient] lightgbm not installed — rule-based fallback")
    except Exception as e:
        logger.error(f"[MLClient] model load error: {e}")

    # Isotonic calibrators
    try:
        import joblib, warnings
        ecp = model_path / "entry_calibrator.pkl"
        rcp = model_path / "risk_calibrator.pkl"
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*unpickle.*")
            if ecp.exists():
                _entry_cal = joblib.load(str(ecp))
                logger.info("[MLClient] entry_calibrator loaded")
            if rcp.exists():
                _risk_cal = joblib.load(str(rcp))
                logger.info("[MLClient] risk_calibrator loaded")
    except Exception as e:
        logger.warning(f"[MLClient] calibrator load error: {e}")


# ── 피처 계산 ─────────────────────────────────────────────────────

def _safe(v, default=0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _compute_features(rows: list, sd_rows: list, disc_rows: list, kospi_rows: list = None,
                      news_sentiment: dict | None = None,
                      _kospi_returns: tuple[float, float, float, float, float, float] | None = None,
                      fin_row: dict | None = None) -> dict:
    """daily_bars rows(최신 → 과거 순) + 수급 + 공시 + 뉴스감성 → FEATURE_COLUMNS dict."""
    if not rows:
        return {k: 0.0 for k in FEATURE_COLUMNS}

    closes  = [_safe(r["close"])  for r in rows]
    volumes = [_safe(r["volume"]) for r in rows]
    amounts = [_safe(r["amount"]) for r in rows]
    highs   = [_safe(r["high"])   for r in rows]
    lows    = [_safe(r["low"])    for r in rows]
    opens   = [_safe(r["open"])   for r in rows]

    c = closes[0]

    def ret(n):
        return (closes[0] / closes[n] - 1) * 100 if len(closes) > n and closes[n] else 0.0

    # ── 수익률 ──
    return_1d  = ret(1)
    return_3d  = ret(3)
    return_5d  = ret(5)
    return_10d = ret(10)
    return_20d = ret(20)

    # ── MA 비율 / 기울기 ──
    def ma(n):
        v = closes[:n]
        return sum(v) / len(v) if v else c
    ma5  = ma(5);  ma20 = ma(20); ma60 = ma(60)
    ma5_ratio  = c / ma5  if ma5  else 1.0
    ma20_ratio = c / ma20 if ma20 else 1.0
    ma60_ratio = c / ma60 if ma60 else 1.0
    ma5_slope  = (ma(5) / ma(min(10, len(closes))) - 1) if len(closes) >= 5 else 0.0
    ma20_slope = (ma(20) / ma(min(40, len(closes))) - 1) if len(closes) >= 20 else 0.0

    # ── 가격 가속도·갭 ── (학습과 동일: 최근 5일 모멘텀 - 직전 5일 모멘텀)
    prior5      = (closes[0] / closes[10] - 1) * 100 if len(closes) > 10 and closes[10] else 0.0
    price_accel = return_5d - prior5
    gap_pct = (opens[0] / closes[1] - 1) * 100 if len(closes) > 1 and closes[1] else 0.0

    # ── 연속 상승/하락 일수 ──
    consec_up = consec_down = 0
    for i in range(1, min(len(closes), 20)):
        if closes[i - 1] > closes[i]:
            if consec_down == 0:
                consec_up += 1
            else:
                break
        elif closes[i - 1] < closes[i]:
            if consec_up == 0:
                consec_down += 1
            else:
                break
        else:
            break

    # ── 거래량/거래대금 ──
    vol5   = sum(volumes[:5])  / 5  if len(volumes) >= 5  else volumes[0]
    vol20  = sum(volumes[:20]) / 20 if len(volumes) >= 20 else volumes[0]
    amt20  = sum(amounts[:20]) / 20 if len(amounts) >= 20 else amounts[0]
    vol_ratio_5d  = volumes[0] / vol5  if vol5  else 1.0
    vol_ratio_20d = volumes[0] / vol20 if vol20 else 1.0
    vol_surge     = 1.0 if vol_ratio_20d >= 3.0 else 0.0
    amount_ratio  = amounts[0] / amt20 if amt20 else 1.0

    # 상승일/하락일 거래량 비율
    up_vols   = [volumes[i] for i in range(1, min(20, len(volumes))) if closes[i-1] >= closes[i]]
    down_vols = [volumes[i] for i in range(1, min(20, len(volumes))) if closes[i-1] < closes[i]]
    avg_up   = sum(up_vols)   / len(up_vols)   if up_vols   else 1.0
    avg_down = sum(down_vols) / len(down_vols) if down_vols else 1.0
    vol_up_down_ratio = avg_up / avg_down if avg_down else 1.0

    # ── MA 크로스 ──
    def ma_prev(n, offset=1):
        v = closes[offset:offset + n]
        return sum(v) / len(v) if v else closes[offset] if len(closes) > offset else c
    ma5_prev  = ma_prev(5)
    ma20_prev = ma_prev(20)
    ma60_prev = ma_prev(60)
    ma5_ma20_cross  = 1.0 if ma5 > ma20 and ma5_prev <= ma20_prev else 0.0
    ma20_ma60_cross = 1.0 if ma20 > ma60 and ma20_prev <= ma60_prev else 0.0

    # ── ATR ──
    atrs = [highs[i] - lows[i] for i in range(min(14, len(highs)))]
    atr  = sum(atrs) / len(atrs) if atrs else c * 0.02
    atr_ratio = atr / c if c else 0.0

    # ── RSI ──
    rsi14 = _safe(rows[0].get("rsi14"), 50.0)
    rsi_oversold  = 1.0 if rsi14 < 30 else 0.0
    rsi_overbought = 1.0 if rsi14 > 70 else 0.0

    # ── MACD ──
    macd_h  = _safe(rows[0].get("macd_hist"))
    macd_ph = _safe(rows[1].get("macd_hist")) if len(rows) > 1 else macd_h
    macd_hist         = macd_h
    macd_golden_cross = 1.0 if macd_h > 0 and macd_ph <= 0 else 0.0

    # ── Bollinger ──
    bb_up = _safe(rows[0].get("bb_upper"), c * 1.05)
    bb_lo = _safe(rows[0].get("bb_lower"), c * 0.95)
    bb_rng = max(bb_up - bb_lo, 1.0)
    bb_pct    = (c - bb_lo) / bb_rng
    bb_width  = bb_rng / c if c else 0.0
    bb_squeeze = 1.0 if bb_width < 0.04 else 0.0

    # ── 캔들 패턴 ──
    o = opens[0]
    body = abs(c - o)
    rng  = max(highs[0] - lows[0], 1.0)
    body_size   = body / rng
    is_bullish  = 1.0 if c > o else 0.0
    upper_wick  = (highs[0] - max(c, o)) / rng
    lower_wick  = (min(c, o) - lows[0])  / rng

    # ── 신고가 ──
    def is_new_high(n):
        if len(closes) <= n:
            return 0.0
        return 1.0 if c >= max(closes[1:n+1]) else 0.0
    is_new_high_20d  = is_new_high(20)
    is_new_high_52d  = is_new_high(130)
    is_new_high_260d = is_new_high(260)
    high52  = max(closes[1:131]) if len(closes) > 131 else c
    low52   = min(closes[1:131]) if len(closes) > 131 else c
    pos_52w = (c - low52) / (high52 - low52) if high52 != low52 else 0.5

    # ── 수급 (supply_demand rows) ──
    f5  = sum(_safe(r.get("foreign_net")) for r in sd_rows[:5])
    f20 = sum(_safe(r.get("foreign_net")) for r in sd_rows[:20])
    i5  = sum(_safe(r.get("inst_net"))    for r in sd_rows[:5])
    i20 = sum(_safe(r.get("inst_net"))    for r in sd_rows[:20])
    foreign_cumnet_5d   = f5
    foreign_cumnet_20d  = f20
    inst_cumnet_5d      = i5
    inst_cumnet_20d     = i20
    dual_buy    = 1.0 if f5 > 0 and i5 > 0 else 0.0
    f3  = sum(_safe(r.get("foreign_net")) for r in sd_rows[:3])
    i3  = sum(_safe(r.get("inst_net"))    for r in sd_rows[:3])
    dual_buy_3d = 1.0 if f3 > 0 and i3 > 0 else 0.0
    short_vol       = _safe(rows[0].get("short_sell_vol"))
    short_ratio     = short_vol / volumes[0] if volumes[0] else 0.0
    short_increasing = _safe(rows[0].get("short_increasing", 0))

    # 외국인 연속 순매수/순매도 streak (+N=연속매수일, -N=연속매도일, 최대 ±20)
    _fstreak = 0
    for _sr in sd_rows[:20]:
        _fn = _safe(_sr.get("foreign_net"))
        if _fn > 0:
            if _fstreak >= 0:
                _fstreak += 1
            else:
                break
        elif _fn < 0:
            if _fstreak <= 0:
                _fstreak -= 1
            else:
                break
        else:
            break
    foreign_cumnet_streak = float(_fstreak)

    # 외국인/기관 순매수 비율 (당일 거래량 대비)
    foreign_net_today = _safe(sd_rows[0].get("foreign_net")) if sd_rows else _safe(rows[0].get("foreign_net_buy"))
    inst_net_today    = _safe(sd_rows[0].get("inst_net"))    if sd_rows else _safe(rows[0].get("inst_net_buy"))
    foreign_net_ratio = foreign_net_today / (volumes[0] + 1)
    inst_net_ratio    = inst_net_today    / (volumes[0] + 1)

    # 신규 수급 피처
    foreign_hold_rate = _safe(sd_rows[0].get("foreign_hold_rate")) if sd_rows else 0.0
    expert_net_5d = sum(
        _safe(r.get("pension_net")) + _safe(r.get("insurance_net"))
        + _safe(r.get("trust_net")) + _safe(r.get("bank_net"))
        for r in sd_rows[:5]
    )
    prog_arb_net_5d = sum(_safe(r.get("prog_arbitrage_net")) for r in sd_rows[:5])

    # ── 공시 ──
    disc_sentiment = 0.0
    has_favorable  = 0.0
    if disc_rows:
        scores = [_safe(r.get("sentiment_score")) for r in disc_rows]
        disc_sentiment = float(np.mean(scores)) if scores else 0.0
        has_favorable  = 1.0 if any(s >= 0.3 for s in scores) else 0.0
    disclosure_sentiment   = disc_sentiment
    has_favorable_disclosure = has_favorable

    # ── KOSPI/시장 대비 상대강도 (방향성 제거 — 상대강도만 사용) ──
    if _kospi_returns is not None:
        kr1d, kr3d, kr5d, kr10d, kr20d, kospi_vol_5d = _kospi_returns
    else:
        kc = [float(r["close"]) for r in (kospi_rows or []) if r.get("close")]
        if len(kc) >= 6:
            kr1d  = (kc[0] / kc[1]  - 1) * 100 if kc[1]  else 0.0
            kr3d  = (kc[0] / kc[3]  - 1) * 100 if len(kc) > 3  and kc[3]  else 0.0
            kr5d  = (kc[0] / kc[5]  - 1) * 100 if kc[5]  else 0.0
            kr10d = (kc[0] / kc[10] - 1) * 100 if len(kc) > 10 and kc[10] else 0.0
            kr20d = (kc[0] / kc[20] - 1) * 100 if len(kc) > 20 and kc[20] else 0.0
            _ks5  = kc[:5]
            kospi_vol_5d = float(np.std([((_ks5[j] / _ks5[j+1] - 1) * 100) for j in range(len(_ks5)-1)])) if len(_ks5) >= 2 else 0.0
        else:
            kr1d = kr3d = kr5d = kr10d = kr20d = kospi_vol_5d = 0.0
    rel_strength_1d  = return_1d  - kr1d
    rel_strength_3d  = return_3d  - kr3d
    rel_strength_5d  = return_5d  - kr5d
    rel_strength_10d = return_10d - kr10d
    rel_strength_20d = return_20d - kr20d
    market_vol_ratio = vol_ratio_20d

    # 시장 국면: KOSPI MA20·MA60 기반 (+1=불장, -1=약세장, 0=중립)
    _kc_list = [float(r["close"]) for r in (kospi_rows or []) if r.get("close")]
    if len(_kc_list) >= 60:
        _kma20 = float(np.mean(_kc_list[:20]))
        _kma60 = float(np.mean(_kc_list[:60]))
        _kc0   = _kc_list[0]
        if _kc0 > _kma60 and _kma20 > _kma60:
            market_phase = 1.0
        elif _kc0 < _kma60 and _kma20 < _kma60:
            market_phase = -1.0
        else:
            market_phase = 0.0
    else:
        market_phase = 0.0

    # ── 시간 인코딩 (sin/cos) — 학습 코드와 동일하게 /7 사용 ──
    _now = datetime.now()
    dow = _now.weekday()  # 0=Mon…6=Sun (한국 주식은 Mon-Fri만 거래하지만 /7로 인코딩)
    month = _now.month
    dow_sin   = math.sin(2 * math.pi * dow / 7)
    dow_cos   = math.cos(2 * math.pi * dow / 7)
    month_sin = math.sin(2 * math.pi * (month - 1) / 12)
    month_cos = math.cos(2 * math.pi * (month - 1) / 12)

    # 뉴스 피처 — Redis news:sentiment:{code} 에서 읽은 집계값 사용
    if news_sentiment:
        news_sentiment_7d = _safe(news_sentiment.get("avg_sentiment"), 0.0)
        news_count_7d     = min(_safe(news_sentiment.get("count"), 0.0), 50.0) / 50.0
    else:
        news_sentiment_7d = 0.0
        news_count_7d     = 0.0

    # ── 재무 피처 (분기별, financials 테이블 최신 분기) ──
    per        = _safe(fin_row.get("per"),        0.0) if fin_row else 0.0
    pbr        = _safe(fin_row.get("pbr"),        0.0) if fin_row else 0.0
    roe        = _safe(fin_row.get("roe"),        0.0) if fin_row else 0.0
    debt_ratio = _safe(fin_row.get("debt_ratio"), 0.0) if fin_row else 0.0

    # ── 시가총액 크기 인자 (size factor) ──
    _mc = _safe(rows[0].get("market_cap"), 0.0) if rows else 0.0
    log_market_cap = math.log(_mc) if _mc > 0 else 0.0

    return {k: locals().get(k, 0.0) for k in FEATURE_COLUMNS}


# ── 메인 공개 함수 ────────────────────────────────────────────────

async def get_ml_result(event: dict, db: asyncpg.Pool, redis=None) -> MLResult:
    _try_load_models()
    code = event.get("code", "")

    # Redis에 사전 계산된 KOSPI 수익률이 있으면 DB 쿼리 생략
    _kospi_returns: tuple[float, float, float, float, float, float] | None = None
    if redis:
        try:
            r1d  = await redis.get("market:kospi_return_1d")
            r5d  = await redis.get("market:kospi_return_5d")
            r3d  = await redis.get("market:kospi_return_3d")
            r10d = await redis.get("market:kospi_return_10d")
            r20d = await redis.get("market:kospi_return_20d")
            rvol = await redis.get("market:kospi_vol_5d")
            if r1d is not None and r5d is not None:
                _kospi_returns = (
                    float(r1d),
                    float(r3d)  if r3d  else 0.0,
                    float(r5d),
                    float(r10d) if r10d else 0.0,
                    float(r20d) if r20d else 0.0,
                    float(rvol) if rvol else 0.0,
                )
        except Exception:
            pass

    try:
        async with db.acquire() as conn:
            bar_rows = await conn.fetch(
                """
                SELECT close, open, high, low, volume, amount, change_rate,
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
            sd_rows = await conn.fetch(
                """
                SELECT foreign_net, inst_net, foreign_hold_rate,
                       pension_net, insurance_net, trust_net, bank_net,
                       prog_arbitrage_net
                FROM supply_demand
                WHERE code=$1 ORDER BY date DESC LIMIT 20
                """,
                code,
            )
            disc_rows = await conn.fetch(
                """
                SELECT sentiment_score FROM disclosures
                WHERE code=$1 AND disclosed_at >= NOW()-INTERVAL '7 days'
                ORDER BY disclosed_at DESC LIMIT 5
                """,
                code,
            )
            fin_row_rec = await conn.fetchrow(
                """
                SELECT per, pbr, roe, debt_ratio FROM financials
                WHERE code=$1 ORDER BY year DESC, quarter DESC LIMIT 1
                """,
                code,
            )
            if _kospi_returns is None:
                kospi_rows = await conn.fetch(
                    "SELECT close FROM daily_bars WHERE code = '0001' ORDER BY date DESC LIMIT 25"
                )
            else:
                kospi_rows = []
    except Exception as e:
        logger.error(f"[MLClient] DB query error {code}: {e}")
        return MLResult()

    if not bar_rows:
        return MLResult()

    # 수급 fallback: supply_demand 없으면 daily_bars 컬럼 사용
    sd = [dict(r) for r in sd_rows]
    if not sd:
        sd = [{"foreign_net": r["foreign_net_buy"], "inst_net": r["inst_net_buy"]}
              for r in bar_rows[:20]]

    bars = [dict(r) for r in bar_rows]
    bars[0]["short_increasing"] = _safe(
        await _short_increasing(db, code, bars)
    )

    # Redis에서 종목별 뉴스 감성 집계 조회
    _news_sentiment = None
    if redis:
        try:
            import orjson as _orjson
            raw = await redis.get(f"news:sentiment:{code}")
            if raw:
                _news_sentiment = _orjson.loads(raw)
        except Exception:
            pass

    feats = _compute_features(bars, sd, [dict(r) for r in disc_rows],
                              kospi_rows=[dict(r) for r in kospi_rows],
                              news_sentiment=_news_sentiment,
                              _kospi_returns=_kospi_returns,
                              fin_row=dict(fin_row_rec) if fin_row_rec else None)
    _atr_ratio = feats.get("atr_ratio", 0.0)

    # ── ML 서비스 HTTP 추론 (우선) ──
    if _ML_SERVICE_URL:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{_ML_SERVICE_URL}/predict",
                    json={"features": feats},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return MLResult(
                        success_prob=data["success_prob"],
                        risk_score=data["risk_score"],
                        expected_return=data["expected_return"],
                        hold_days=data["hold_days"],
                        confidence=data["confidence"],
                        model_used=data["model_used"],
                        atr_ratio=_atr_ratio,
                    )
        except Exception as e:
            logger.warning(f"[MLClient] HTTP inference failed {code}, falling back to local: {e}")

    # ── LightGBM 직접 추론 (fallback) ──
    if _entry_model is not None:
        try:
            import pandas as pd
            X = pd.DataFrame([feats])[FEATURE_COLUMNS].fillna(0.0)
            raw_prob = float(np.clip(_entry_model.predict(X)[0], 0.0, 1.0))

            # Isotonic calibration 적용
            if _entry_cal is not None:
                prob = float(np.clip(_entry_cal.predict([raw_prob])[0], 0.0, 1.0))
            else:
                prob = raw_prob

            raw_risk = float(np.clip(_risk_model.predict(X)[0], 0.0, 1.0)) if _risk_model else 0.4
            if _risk_cal is not None:
                risk = float(np.clip(_risk_cal.predict([raw_risk])[0], 0.0, 1.0))
            else:
                risk = raw_risk

            hold = _hold_days(feats)
            return MLResult(
                success_prob=round(prob, 4),
                risk_score=round(risk, 4),
                expected_return=round((prob - 0.5) * 20.0, 2),
                hold_days=hold,
                confidence=0.85,
                model_used=True,
                atr_ratio=_atr_ratio,
            )
        except Exception as e:
            logger.warning(f"[MLClient] LightGBM inference error {code}: {e}")

    # ── 규칙 기반 fallback ──
    rsi   = feats["rsi14"]
    macd  = feats["macd_hist"]
    bb    = feats["bb_pct"]
    ma20r = feats["ma20_ratio"]
    volr  = feats["vol_ratio_20d"]

    prob = 0.5
    if rsi < 70 and macd > 0 and bb < 0.9:
        prob += 0.08
    if ma20r > 1.02:
        prob += 0.05
    if volr > 2.0:
        prob += 0.04
    if feats["dual_buy"] > 0:
        prob += 0.04
    if feats["has_favorable_disclosure"] > 0:
        prob += 0.03
    prob = min(0.82, max(0.22, prob))

    risk = 0.3
    if rsi > 80:
        risk += 0.20
    if bb > 0.95:
        risk += 0.15
    if feats["vol_surge"] > 0 and feats["is_new_high_20d"] == 0:
        risk += 0.10
    risk = min(0.9, risk)

    return MLResult(
        success_prob=round(prob, 4),
        risk_score=round(risk, 4),
        hold_days=_hold_days(feats),
        confidence=0.5,
        model_used=False,
        atr_ratio=_atr_ratio,
    )


def _hold_days(feats: dict) -> int:
    if feats.get("bb_squeeze"):
        return 3
    if feats.get("vol_ratio_20d", 1.0) > 15.0:
        return 1
    return 5


async def _short_increasing(db: asyncpg.Pool, code: str, bars: list[dict]) -> int:
    shorts = [_safe(b.get("short_sell_vol")) for b in bars[:10]]
    if len(shorts) < 6:
        return 0
    recent = sum(shorts[:3]) / 3
    older  = sum(shorts[3:6]) / 3 + 1
    return int(recent > older)


async def get_similar_cases(event: dict, db: asyncpg.Pool) -> tuple[list, dict]:
    """pgvector IVFFlat 인덱스를 사용한 실제 유사사례 검색."""
    code = event.get("code", "")
    try:
        async with db.acquire() as conn:
            anchor = await conn.fetchrow(
                """
                SELECT pattern_vector FROM feature_events
                WHERE code=$1 AND pattern_vector IS NOT NULL
                ORDER BY detected_at DESC LIMIT 1
                """,
                code,
            )

            if anchor and anchor["pattern_vector"] is not None:
                # HNSW가 있으면 ef_search 설정, IVFFlat이면 probes 설정 — 양쪽 다 SET해도 무해함
                async with conn.transaction():
                    await conn.execute("SET LOCAL ivfflat.probes = 10")
                    await conn.execute("SET LOCAL hnsw.ef_search = 100")
                    rows = await conn.fetch(
                        """
                        SELECT id, code, detected_at::TEXT, event_type,
                               ROUND((1 - (pattern_vector <=> $2::vector))::NUMERIC, 4) AS similarity,
                               result_1d, result_3d, result_5d
                        FROM feature_events
                        WHERE code != $1
                          AND pattern_vector IS NOT NULL
                          AND result_5d IS NOT NULL
                        ORDER BY pattern_vector <=> $2::vector
                        LIMIT 50
                        """,
                        code,
                        anchor["pattern_vector"],
                    )
                search_method = "ann"
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, code, detected_at::TEXT, event_type,
                           NULL::NUMERIC AS similarity,
                           result_1d, result_3d, result_5d
                    FROM feature_events
                    WHERE code != $1
                      AND event_type = $2
                      AND result_5d IS NOT NULL
                    ORDER BY detected_at DESC
                    LIMIT 50
                    """,
                    code,
                    event.get("event_type", ""),
                )
                search_method = "recency_fallback"

        import decimal
        def _to_native(v):
            if isinstance(v, decimal.Decimal):
                return float(v)
            return v
        _RENAME = {"result_5d": "return_5d", "result_3d": "return_3d", "result_1d": "return_1d",
                   "detected_at": "date"}
        cases = [{_RENAME.get(k, k): _to_native(v) for k, v in dict(r).items()} for r in rows]
        if not cases:
            return [], {"success_rate": 0.5, "avg_return_5d": 0.0, "avg_return_1d": 0.0, "count": 0, "search_method": search_method}

        returns_5d = [float(c["return_5d"]) for c in cases if c.get("return_5d") is not None]
        returns_1d = [float(c["return_1d"]) for c in cases if c.get("return_1d") is not None]
        sims       = [float(c["similarity"]) for c in cases if c.get("similarity") is not None]

        success_rate = sum(1 for r in returns_5d if r >= 5.0) / max(len(returns_5d), 1)

        stats = {
            "success_rate":    round(success_rate, 4),
            "avg_return_5d":   round(float(np.median(returns_5d)), 2) if returns_5d else 0.0,
            "std_return_5d":   round(float(np.std(returns_5d)), 2)    if len(returns_5d) > 1 else 0.0,
            "avg_return_1d":   round(float(np.median(returns_1d)), 2) if returns_1d else 0.0,
            "avg_similarity":  round(float(np.mean(sims)), 4)         if sims else 0.0,
            "count":           len(cases),
            "search_method":   search_method,
        }
        return cases, stats

    except Exception as e:
        logger.error(f"[MLClient] similar cases error: {e}")
        return [], {"success_rate": 0.5, "avg_return_5d": 0.0, "avg_return_1d": 0.0, "count": 0, "search_method": "error"}