"""
GCP e2-micro 장중 스캐너 (pykrx → Supabase 이력 → ML → Telegram)
크론: */10 0-6 * * 1-5  (UTC 00:00-07:00 = KST 09:00-16:00, 평일)
사전 실행: backfill_supabase.py (90일 일봉 적재)
"""
import asyncio
import asyncpg
import json
import logging
import math
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pykrx import stock as krx

load_dotenv(os.path.expanduser("~/.env"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("scanner")

KST     = timezone(timedelta(hours=9))
NOW     = datetime.now(KST)
TODAY   = NOW.strftime("%Y%m%d")
TODAY_D = NOW.date()

DSN       = os.environ["POSTGRES_DSN"]
TG_TOKEN  = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT   = os.environ.get("TELEGRAM_CHAT_ID", "")
MODEL_DIR = Path(os.environ.get(
    "LGBM_MODEL_DIR",
    os.path.expanduser("~/quant/repo/kospi-feature-stock/services/api/lgbm_export"),
))

SIGNAL_VOL_RATIO  = float(os.environ.get("SIGNAL_VOL_RATIO", "2.0"))
SIGNAL_CHANGE_MIN = float(os.environ.get("SIGNAL_CHANGE_MIN", "3.0"))
SCORE_THRESHOLD   = float(os.environ.get("SCORE_THRESHOLD", "0.55"))
RISK_THRESHOLD    = float(os.environ.get("RISK_THRESHOLD", "0.55"))
COOLDOWN_DAYS     = int(os.environ.get("COOLDOWN_DAYS", "2"))
HISTORY_DAYS      = 75  # MA60 + 여유


# ── 시장 시간 확인 ─────────────────────────────────────────────────────

def is_market_open() -> bool:
    if NOW.weekday() >= 5:
        return False
    from datetime import time as _t
    return _t(9, 5) <= NOW.time() <= _t(15, 35)


# ── 모델 로딩 ──────────────────────────────────────────────────────────

def load_models():
    import lightgbm as lgb
    fc_path = MODEL_DIR / "feature_columns.json"
    with open(fc_path) as f:
        feature_cols = json.load(f)
    log.info(f"피처 {len(feature_cols)}개 로드")

    models = {}
    models["entry_lgbm"] = lgb.Booster(model_file=str(MODEL_DIR / "entry_model.lgb"))
    models["risk_lgbm"]  = lgb.Booster(model_file=str(MODEL_DIR / "risk_model.lgb"))
    log.info("LightGBM 모델 로드 완료")

    try:
        import joblib, warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            for key, fname in [
                ("entry_cal",     "entry_calibrator.pkl"),
                ("risk_cal",      "risk_calibrator.pkl"),
                ("xgb_entry",     "xgb_entry_model.pkl"),
                ("xgb_entry_cal", "xgb_entry_calibrator.pkl"),
            ]:
                p = MODEL_DIR / fname
                if p.exists():
                    models[key] = joblib.load(str(p))
        log.info("캘리브레이터/XGB 로드 완료")
    except Exception as e:
        log.warning(f"캘리브레이터/XGB 로드 실패: {e}")

    return models, feature_cols


# ── pykrx 데이터 수집 ──────────────────────────────────────────────────

def fetch_market_data() -> dict:
    ohlcv, fund, mcap = {}, {}, {}

    for market in ["KOSPI", "KOSDAQ"]:
        try:
            df = krx.get_market_ohlcv_by_ticker(TODAY, market=market)
            if df is not None and not df.empty:
                df.index = df.index.astype(str).str.zfill(6)
                df["_market"] = market
                ohlcv[market] = df
                log.info(f"{market}: {len(df)}종목 OHLCV")
        except Exception as e:
            log.warning(f"{market} OHLCV 실패: {e}")
        time.sleep(0.5)

    for market in ["KOSPI", "KOSDAQ"]:
        try:
            df = krx.get_market_fundamental_by_ticker(TODAY, market=market)
            if df is not None and not df.empty:
                df.index = df.index.astype(str).str.zfill(6)
                for code, r in df.iterrows():
                    fund[code] = {
                        "per": float(r.get("PER", 0) or 0),
                        "pbr": float(r.get("PBR", 0) or 0),
                    }
        except Exception as e:
            log.warning(f"{market} 기초 데이터 실패: {e}")
        time.sleep(0.5)

    for market in ["KOSPI", "KOSDAQ"]:
        try:
            df = krx.get_market_cap_by_ticker(TODAY, market=market)
            if df is not None and not df.empty:
                df.index = df.index.astype(str).str.zfill(6)
                col = "시가총액" if "시가총액" in df.columns else df.columns[0]
                for code, r in df.iterrows():
                    v = r.get(col, 0)
                    mcap[code] = float(v or 0)
        except Exception as e:
            log.warning(f"{market} 시가총액 실패: {e}")
        time.sleep(0.5)

    return {"ohlcv": ohlcv, "fund": fund, "mcap": mcap}


# ── 신호 탐지 ──────────────────────────────────────────────────────────

async def get_signal_candidates(conn, market_data: dict) -> list[str]:
    try:
        rows = await conn.fetch("""
            SELECT code, AVG(volume)::BIGINT AS avg_vol
            FROM daily_bars
            WHERE date >= $1 AND date < $2
            GROUP BY code
        """, TODAY_D - timedelta(days=30), TODAY_D)
        avg_vols = {r["code"]: int(r["avg_vol"]) for r in rows if r["avg_vol"]}
    except Exception as e:
        log.warning(f"평균 거래량 조회 실패: {e}")
        avg_vols = {}

    candidates = []
    for market, df in market_data["ohlcv"].items():
        for code, r in df.iterrows():
            vol   = int(r.get("거래량", 0) or 0)
            chg   = float(r.get("등락률", 0.0) or 0.0)
            close = int(r.get("종가", 0) or 0)
            if close <= 0:
                continue
            avg_vol   = avg_vols.get(code, 0)
            vol_ratio = vol / avg_vol if avg_vol > 0 else 1.0
            if vol_ratio >= SIGNAL_VOL_RATIO or chg >= SIGNAL_CHANGE_MIN:
                candidates.append(code)

    log.info(f"신호 종목: {len(candidates)}개")
    return candidates


# ── Supabase 이력 로드 ─────────────────────────────────────────────────

async def load_history(conn, codes: list[str]) -> dict[str, list]:
    since = TODAY_D - timedelta(days=HISTORY_DAYS + 10)
    rows = await conn.fetch("""
        SELECT code, date, open, high, low, close, volume, amount, change_rate
        FROM daily_bars
        WHERE code = ANY($1::varchar[]) AND date >= $2
        ORDER BY code, date DESC
    """, codes, since)
    hist: dict[str, list] = {}
    for r in rows:
        d = dict(r)
        hist.setdefault(d["code"], []).append(d)
    return hist


async def load_kospi_index(conn) -> list:
    rows = await conn.fetch("""
        SELECT close FROM daily_bars
        WHERE code = '0001'
        ORDER BY date DESC LIMIT 65
    """)
    return [{"close": r["close"]} for r in rows]


# ── 기술적 지표 ────────────────────────────────────────────────────────

def _compute_macd_bb(closes_new_to_old: list):
    """최신→과거 순 closes에서 (macd_hist, bb_upper, bb_lower) 반환"""
    prices = list(reversed(closes_new_to_old))  # 오래된→최신
    c_last = prices[-1] if prices else 100.0
    if len(prices) < 26:
        return 0.0, c_last * 1.05, c_last * 0.95

    k12, k26, k9 = 2/13, 2/27, 2/10
    ema12 = ema26 = prices[0]
    macd_vals = []
    for p in prices:
        ema12 = p * k12 + ema12 * (1 - k12)
        ema26 = p * k26 + ema26 * (1 - k26)
        macd_vals.append(ema12 - ema26)

    signal = macd_vals[0]
    for m in macd_vals[1:]:
        signal = m * k9 + signal * (1 - k9)
    macd_hist = macd_vals[-1] - signal

    recent20 = prices[-min(20, len(prices)):]
    mean = sum(recent20) / len(recent20)
    std  = (sum((x - mean) ** 2 for x in recent20) / len(recent20)) ** 0.5
    return macd_hist, mean + 2 * std, mean - 2 * std


def _rsi(closes_new_to_old: list, period=14) -> float:
    prices = list(reversed(closes_new_to_old[:period * 2 + 2]))
    if len(prices) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(prices)):
        d = prices[i] - prices[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    return 100.0 - 100.0 / (1 + ag / al) if al > 0 else 100.0


# ── 피처 계산 ──────────────────────────────────────────────────────────

def _s(v, d=0.0) -> float:
    try:
        return float(v) if v is not None else d
    except Exception:
        return d


def compute_features(
    today_row: dict,
    hist_rows: list,
    fund: dict,
    mcap: float,
    is_kosdaq: float,
    kospi_hist: list,
    feature_cols: list,
) -> dict:
    rows   = [today_row] + hist_rows  # 최신→과거
    closes  = [_s(r.get("close"))  for r in rows]
    volumes = [_s(r.get("volume")) for r in rows]
    amounts = [_s(r.get("amount")) for r in rows]
    highs   = [_s(r.get("high"))   for r in rows]
    lows    = [_s(r.get("low"))    for r in rows]
    opens   = [_s(r.get("open"))   for r in rows]

    c = closes[0]
    if c <= 0:
        return {k: 0.0 for k in feature_cols}

    def ret(n):
        return (c / closes[n] - 1) * 100 if len(closes) > n and closes[n] else 0.0

    return_1d  = ret(1)
    return_3d  = ret(3)
    return_5d  = ret(5)
    return_10d = ret(10)
    return_20d = ret(20)

    def ma(n):
        v = closes[:n]
        return sum(v) / len(v) if v else c

    def ma_prev(n, offset=1):
        v = closes[offset:offset + n]
        return sum(v) / len(v) if v else (closes[offset] if len(closes) > offset else c)

    ma5   = ma(5);  ma20 = ma(20); ma60 = ma(60)
    ma5_ratio   = c / ma5  if ma5  else 1.0
    ma20_ratio  = c / ma20 if ma20 else 1.0
    ma60_ratio  = c / ma60 if ma60 else 1.0
    ma5_slope   = (ma5  / ma_prev(5)  - 1) if len(closes) >= 10 else 0.0
    ma20_slope  = (ma20 / ma_prev(20) - 1) if len(closes) >= 40 else 0.0

    prior5      = (c / closes[10] - 1) * 100 if len(closes) > 10 and closes[10] else 0.0
    price_accel = return_5d - prior5
    gap_pct     = (opens[0] / closes[1] - 1) * 100 if len(closes) > 1 and closes[1] else 0.0

    consec_up = consec_down = 0
    for i in range(1, min(len(closes), 20)):
        if closes[i - 1] > closes[i]:
            if consec_down == 0: consec_up += 1
            else: break
        elif closes[i - 1] < closes[i]:
            if consec_up == 0: consec_down += 1
            else: break
        else:
            break

    vol5   = sum(volumes[:5])  / 5  if len(volumes) >= 5  else volumes[0]
    vol20  = sum(volumes[:20]) / 20 if len(volumes) >= 20 else volumes[0]
    amt20  = sum(amounts[:20]) / 20 if len(amounts) >= 20 else amounts[0]
    vol_ratio_5d  = volumes[0] / vol5  if vol5  else 1.0
    vol_ratio_20d = volumes[0] / vol20 if vol20 else 1.0
    vol_surge     = 1.0 if vol_ratio_20d >= 3.0 else 0.0
    amount_ratio  = amounts[0] / amt20 if amt20 else 1.0

    up_vols   = [volumes[i] for i in range(1, min(20, len(volumes))) if closes[i-1] >= closes[i]]
    down_vols = [volumes[i] for i in range(1, min(20, len(volumes))) if closes[i-1] < closes[i]]
    avg_up    = sum(up_vols)   / len(up_vols)   if up_vols   else 1.0
    avg_down  = sum(down_vols) / len(down_vols) if down_vols else 1.0
    vol_up_down_ratio = avg_up / avg_down if avg_down else 1.0

    ma5_prev  = ma_prev(5)
    ma20_prev = ma_prev(20)
    ma60_prev = ma_prev(60)
    ma5_ma20_cross  = 1.0 if ma5  > ma20 and ma5_prev  <= ma20_prev else 0.0
    ma20_ma60_cross = 1.0 if ma20 > ma60 and ma20_prev <= ma60_prev else 0.0

    atrs      = [highs[i] - lows[i] for i in range(min(14, len(highs)))]
    atr       = sum(atrs) / len(atrs) if atrs else c * 0.02
    atr_ratio = atr / c if c else 0.0

    rsi14         = _rsi(closes, 14)
    rsi_oversold  = 1.0 if rsi14 < 30 else 0.0
    rsi_overbought = 1.0 if rsi14 > 70 else 0.0

    macd_hist, bb_upper, bb_lower = _compute_macd_bb(closes)
    prev_macd, _, _               = _compute_macd_bb(closes[1:]) if len(closes) > 27 else (0.0, 0, 0)
    macd_golden_cross = 1.0 if macd_hist > 0 and prev_macd <= 0 else 0.0
    bb_rng    = max(bb_upper - bb_lower, 1.0)
    bb_pct    = (c - bb_lower) / bb_rng
    bb_width  = bb_rng / c if c else 0.0
    bb_squeeze = 1.0 if bb_width < 0.04 else 0.0

    o = opens[0]
    body_range = max(highs[0] - lows[0], 1.0)
    body_size  = abs(c - o) / body_range
    is_bullish = 1.0 if c > o else 0.0
    upper_wick = (highs[0] - max(c, o)) / body_range
    lower_wick = (min(c, o) - lows[0])  / body_range

    def is_new_high(n):
        return 1.0 if len(closes) > n and c >= max(closes[1:n+1]) else 0.0

    is_new_high_20d  = is_new_high(20)
    is_new_high_52d  = is_new_high(130)
    is_new_high_260d = is_new_high(260)
    high52  = max(closes[1:131]) if len(closes) > 131 else c
    low52   = min(closes[1:131]) if len(closes) > 131 else c
    pos_52w = (c - low52) / (high52 - low52) if high52 != low52 else 0.5

    # 수급 — Supabase에 supply_demand 없으므로 중립값 사용
    foreign_cumnet_5d    = 0.0
    foreign_cumnet_20d   = 0.0
    foreign_cumnet_streak = 0.0
    inst_cumnet_5d       = 0.0
    inst_cumnet_20d      = 0.0
    dual_buy             = 0.0
    dual_buy_3d          = 0.0
    short_ratio          = 0.0
    short_increasing     = 0.0
    foreign_net_ratio    = 0.0
    inst_net_ratio       = 0.0

    # 공시/뉴스 — 없으므로 중립값
    disclosure_sentiment     = 0.0
    has_favorable_disclosure = 0.0
    news_sentiment_7d        = 0.0
    news_count_7d            = 0.0

    # KOSPI 상대강도
    kc = [_s(r.get("close")) for r in kospi_hist if r.get("close")]
    if len(kc) >= 21:
        kr1d  = (kc[0] / kc[1]  - 1) * 100 if kc[1]              else 0.0
        kr3d  = (kc[0] / kc[3]  - 1) * 100 if len(kc) > 3  and kc[3]  else 0.0
        kr5d  = (kc[0] / kc[5]  - 1) * 100 if len(kc) > 5  and kc[5]  else 0.0
        kr10d = (kc[0] / kc[10] - 1) * 100 if len(kc) > 10 and kc[10] else 0.0
        kr20d = (kc[0] / kc[20] - 1) * 100 if len(kc) > 20 and kc[20] else 0.0
        ks5   = kc[:5]
        kospi_vol_5d = float(np.std([(ks5[j] / ks5[j+1] - 1) * 100
                                     for j in range(len(ks5) - 1)])) if len(ks5) >= 2 else 0.0
    else:
        kr1d = kr3d = kr5d = kr10d = kr20d = kospi_vol_5d = 0.0

    rel_strength_1d  = return_1d  - kr1d
    rel_strength_3d  = return_3d  - kr3d
    rel_strength_5d  = return_5d  - kr5d
    rel_strength_10d = return_10d - kr10d
    rel_strength_20d = return_20d - kr20d
    market_vol_ratio = vol_ratio_20d

    if len(kc) >= 60:
        kma20 = float(np.mean(kc[:20]))
        kma60 = float(np.mean(kc[:60]))
        kc0   = kc[0]
        if kc0 > kma60 and kma20 > kma60:
            market_phase = 1.0
        elif kc0 < kma60 and kma20 < kma60:
            market_phase = -1.0
        else:
            market_phase = 0.0
    else:
        market_phase = 0.0

    dow   = NOW.weekday()
    month = NOW.month
    dow_sin   = math.sin(2 * math.pi * dow / 7)
    dow_cos   = math.cos(2 * math.pi * dow / 7)
    month_sin = math.sin(2 * math.pi * (month - 1) / 12)
    month_cos = math.cos(2 * math.pi * (month - 1) / 12)

    per        = _s(fund.get("per"), 0.0)
    pbr        = _s(fund.get("pbr"), 0.0)
    roe        = 0.0
    debt_ratio = 0.0
    log_market_cap = math.log(mcap) if mcap > 0 else 0.0

    # 단면 랭크 — add_rank_features()에서 덮어씌움
    rank_return_5d   = 0.5
    rank_vol_ratio   = 0.5
    rank_foreign_net = 0.5
    rank_rsi14       = 0.5

    return {k: locals().get(k, 0.0) for k in feature_cols}


# ── 단면 랭크 업데이트 ────────────────────────────────────────────────

def add_rank_features(feats_list: list[dict]) -> list[dict]:
    if len(feats_list) <= 1:
        return feats_list

    def pct_rank(values: list) -> list:
        n = len(values)
        order = sorted(range(n), key=lambda i: values[i])
        ranks = [0.0] * n
        for rank, idx in enumerate(order):
            ranks[idx] = rank / (n - 1)
        return ranks

    r5d_ranks  = pct_rank([f.get("return_5d", 0.0)      for f in feats_list])
    vol_ranks  = pct_rank([f.get("vol_ratio_20d", 1.0)   for f in feats_list])
    fnet_ranks = pct_rank([f.get("foreign_net_ratio", 0.0) for f in feats_list])
    rsi_ranks  = pct_rank([f.get("rsi14", 50.0)          for f in feats_list])

    for i, f in enumerate(feats_list):
        f["rank_return_5d"]   = r5d_ranks[i]
        f["rank_vol_ratio"]   = vol_ranks[i]
        f["rank_foreign_net"] = fnet_ranks[i]
        f["rank_rsi14"]       = rsi_ranks[i]

    return feats_list


# ── ML 배치 추론 ──────────────────────────────────────────────────────

def ml_score(feats_df: pd.DataFrame, models: dict, feature_cols: list):
    X = feats_df[feature_cols].fillna(0.0)

    raw_lgbm  = np.clip(models["entry_lgbm"].predict(X), 0.0, 1.0)
    entry_cal = models.get("entry_cal")
    lgbm_prob = np.clip(entry_cal.predict(raw_lgbm), 0.0, 1.0) if entry_cal else raw_lgbm

    xgb_entry = models.get("xgb_entry")
    if xgb_entry is not None:
        raw_xgb  = np.clip(xgb_entry.predict_proba(X)[:, 1], 0.0, 1.0)
        xgb_ec   = models.get("xgb_entry_cal")
        xgb_prob = np.clip(xgb_ec.predict(raw_xgb), 0.0, 1.0) if xgb_ec else raw_xgb
        prob = lgbm_prob * 0.6 + xgb_prob * 0.4
    else:
        prob = lgbm_prob

    raw_risk  = np.clip(models["risk_lgbm"].predict(X), 0.0, 1.0)
    risk_cal  = models.get("risk_cal")
    risk = np.clip(risk_cal.predict(raw_risk), 0.0, 1.0) if risk_cal else raw_risk

    return prob, risk


# ── Telegram ──────────────────────────────────────────────────────────

async def send_telegram(msg: str) -> None:
    if not TG_TOKEN or not TG_CHAT:
        return
    import urllib.request
    url  = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": TG_CHAT, "text": msg, "parse_mode": "HTML"}).encode()
    req  = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log.warning(f"Telegram 전송 실패: {e}")


# ── 쿨다운 확인 ───────────────────────────────────────────────────────

async def get_recent_recs(conn) -> set[str]:
    since = TODAY_D - timedelta(days=COOLDOWN_DAYS)
    try:
        rows = await conn.fetch(
            "SELECT DISTINCT code FROM recommendations WHERE created_at >= $1 AND action='BUY'",
            since,
        )
        return {r["code"] for r in rows}
    except Exception as e:
        log.warning(f"쿨다운 조회 실패: {e}")
        return set()


# ── 추천 저장 ─────────────────────────────────────────────────────────

async def save_recommendations(conn, recs: list[dict]) -> int:
    if not recs:
        return 0
    rows = [
        (
            r["code"],
            "BUY",
            r.get("close_price", 0),
            r["success_prob"],
            r["risk_score"],
            r["expected_return"],
            r["hold_days"],
            json.dumps({
                "signal_type": r.get("signal_type", "SCAN_SIGNAL"),
                "vol_ratio":   r.get("vol_ratio", 1.0),
                "source":      "market_scan",
            }),
        )
        for r in recs
    ]
    try:
        await conn.executemany("""
            INSERT INTO recommendations
                (code, action, entry_price, success_prob, risk_score,
                 expected_return, expected_hold_days, rationale)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8::JSONB)
        """, rows)
    except Exception as e:
        log.error(f"추천 저장 실패: {e}")
        return 0
    return len(rows)


# ── 메인 ─────────────────────────────────────────────────────────────

async def main():
    if not is_market_open():
        log.info(f"장 외 시간 — 종료 ({NOW.strftime('%H:%M KST')})")
        return

    log.info(f"스캔 시작 {NOW.strftime('%Y-%m-%d %H:%M KST')}")

    models, feature_cols = load_models()
    market_data = fetch_market_data()
    if not market_data["ohlcv"]:
        log.warning("OHLCV 없음 — 종료")
        return

    conn = await asyncpg.connect(DSN)
    try:
        candidates  = await get_signal_candidates(conn, market_data)
        recent_recs = await get_recent_recs(conn)
        candidates  = [c for c in candidates if c not in recent_recs]
        log.info(f"쿨다운 후 후보: {len(candidates)}개")
        if not candidates:
            return

        hist_data  = await load_history(conn, candidates)
        kospi_hist = await load_kospi_index(conn)
    finally:
        await conn.close()

    # 오늘 OHLCV 딕셔너리화 (pykrx 한글 컬럼 → 영문)
    all_today: dict[str, dict] = {}
    for market, df in market_data["ohlcv"].items():
        for code, r in df.iterrows():
            all_today[code] = {
                "open":        int(r.get("시가",   0) or 0),
                "high":        int(r.get("고가",   0) or 0),
                "low":         int(r.get("저가",   0) or 0),
                "close":       int(r.get("종가",   0) or 0),
                "volume":      int(r.get("거래량", 0) or 0),
                "amount":      int(r.get("거래대금", 0) or 0),
                "change_rate": float(r.get("등락률", 0.0) or 0.0),
                "_market":     market,
            }

    # 피처 계산
    feats_list:  list[dict] = []
    valid_codes: list[str]  = []

    for code in candidates:
        today_r   = all_today.get(code)
        if not today_r or today_r["close"] <= 0:
            continue
        hist_rows = hist_data.get(code, [])
        fund      = market_data["fund"].get(code, {})
        mcap      = market_data["mcap"].get(code, 0.0)
        is_kosdaq = 1.0 if today_r["_market"] == "KOSDAQ" else 0.0

        feats = compute_features(
            today_r, hist_rows, fund, mcap, is_kosdaq, kospi_hist, feature_cols
        )
        feats_list.append(feats)
        valid_codes.append(code)

    if not feats_list:
        log.info("유효 피처 없음")
        return

    feats_list = add_rank_features(feats_list)

    # ML 배치 추론
    feats_df = pd.DataFrame(feats_list)
    probs, risks = ml_score(feats_df, models, feature_cols)

    # 추천 필터링
    new_recs = []
    for i, code in enumerate(valid_codes):
        prob = float(probs[i])
        risk = float(risks[i])
        if prob >= SCORE_THRESHOLD and risk <= RISK_THRESHOLD:
            td   = all_today[code]
            new_recs.append({
                "code":            code,
                "success_prob":    round(prob, 4),
                "risk_score":      round(risk, 4),
                "expected_return": round((prob - 0.5) * 20.0, 2),
                "hold_days":       5,
                "signal_type":     "SCAN_SIGNAL",
                "close_price":     td["close"],
                "vol_ratio":       round(feats_list[i].get("vol_ratio_20d", 1.0), 2),
            })

    log.info(f"추천 종목: {len(new_recs)}개 (후보 {len(valid_codes)}개)")

    if not new_recs:
        return

    conn = await asyncpg.connect(DSN)
    try:
        n = await save_recommendations(conn, new_recs)
    finally:
        await conn.close()

    log.info(f"저장 완료: {n}건")

    # Telegram 알림 (최대 10종목)
    top = sorted(new_recs, key=lambda x: -x["success_prob"])[:10]
    lines = [f"<b>매수 추천 {len(new_recs)}종목</b> ({NOW.strftime('%H:%M')} KST)\n"]
    for r in top:
        lines.append(
            f"• <b>{r['code']}</b>  확률 {r['success_prob']:.0%}"
            f"  리스크 {r['risk_score']:.0%}"
            f"  거래량 {r['vol_ratio']:.1f}x"
            f"  ₩{r['close_price']:,}"
        )
    await send_telegram("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
