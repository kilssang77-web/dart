"""
GCP e2-micro 장 마감 후 스캐너 (Supabase daily_bars → ML → Telegram)
pykrx/KRX API 의존성 없음 — Supabase 데이터만 사용
크론: 30 7 * * 1-5  (UTC 07:30 = KST 16:30, 평일 장 마감 후)
"""
import asyncio
import asyncpg
import json
import logging
import math
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.env"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("scanner")

KST     = timezone(timedelta(hours=9))
NOW     = datetime.now(KST)
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
SCORE_THRESHOLD   = float(os.environ.get("SCORE_THRESHOLD", "0.27"))  # 추천 저장 기준 (DB)
RISK_THRESHOLD    = float(os.environ.get("RISK_THRESHOLD", "0.55"))   # 추천 저장 기준 (DB)
COOLDOWN_DAYS     = int(os.environ.get("COOLDOWN_DAYS", "2"))
HISTORY_DAYS      = 75  # MA60 + 여유


# ── 텔레그램 설정 (Redis telegram:config 연동) ─────────────────

def _load_tg_config() -> dict:
    """Redis에서 설정 UI 값을 조회. REDIS_URL 없거나 실패 시 env 기본값."""
    default = {
        "enabled":         os.environ.get("TELEGRAM_ENABLED", "1") == "1",
        "min_prob":        float(os.environ.get("REC_MIN_PROB",        "0.22")),
        "max_risk":        float(os.environ.get("REC_MAX_RISK",        "0.60")),
        "min_risk_reward": float(os.environ.get("REC_MIN_RISK_REWARD", "2.0")),
    }
    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url:
        return default
    try:
        import redis as _r
        rc = _r.from_url(redis_url, decode_responses=True, socket_timeout=3)
        raw = rc.get("telegram:config")
        rc.close()
        if raw:
            cfg = json.loads(raw)
            log.info(
                f"Redis 설정 로드: enabled={cfg.get('enabled')} "
                f"min_prob={cfg.get('min_prob'):.3f} max_risk={cfg.get('max_risk'):.3f}"
            )
            return cfg
    except Exception as e:
        log.warning(f"Redis 설정 로드 실패, env 기본값 사용: {e}")
    return default


async def _log_telegram(
    conn,
    *,
    msg_type: str,
    title: str,
    message: str,
    success: bool,
    code: str = "",
    name: str = "",
) -> None:
    try:
        await conn.execute(
            """
            INSERT INTO telegram_logs (msg_type, code, name, title, message, success)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            msg_type, code or None, name or None, title, message, success,
        )
    except Exception as e:
        log.warning(f"telegram_logs 기록 실패: {e}")

# 동적 임계값 — result_tracker.py가 갱신, 초기값은 env/기본값
_DYN_CFG = Path(os.path.expanduser("~/quant/dynamic_config.json"))
if _DYN_CFG.exists():
    try:
        _d = json.loads(_DYN_CFG.read_text())
        if "score_threshold" in _d:
            SCORE_THRESHOLD = float(_d["score_threshold"])
    except Exception:
        pass


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

    # calibrator 로딩 (XGBoost와 독립적으로 처리)
    try:
        import joblib, warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            for key, fname in [("entry_cal", "entry_calibrator.pkl"),
                                ("risk_cal",  "risk_calibrator.pkl")]:
                p = MODEL_DIR / fname
                if p.exists():
                    models[key] = joblib.load(str(p))
        log.info("calibrator 로드 완료")
    except Exception as e:
        log.warning(f"calibrator 로드 실패: {e}")

    # XGBoost 앙상블 (선택적)
    try:
        import xgboost  # noqa: F401
        import joblib as _jl, warnings as _w
        with _w.catch_warnings():
            _w.filterwarnings("ignore")
            for key, fname in [("xgb_entry",     "xgb_entry_model.pkl"),
                                ("xgb_entry_cal", "xgb_entry_calibrator.pkl")]:
                p = MODEL_DIR / fname
                if p.exists():
                    models[key] = _jl.load(str(p))
        log.info("XGBoost 앙상블 로드 완료")
    except ImportError:
        log.info("xgboost 미설치 — LGBM 단독 사용")
    except Exception as e:
        log.warning(f"XGBoost 로드 실패: {e}")

    return models, feature_cols


# ── Supabase 데이터 로드 ───────────────────────────────────────────────

async def fetch_latest_date(conn) -> date:
    """Supabase에 있는 가장 최근 영업일 반환"""
    d = await conn.fetchval("SELECT MAX(date) FROM daily_bars")
    return d


async def fetch_latest_ohlcv(conn, target_date: date) -> dict[str, dict]:
    """target_date 전 종목 OHLCV + market 반환"""
    rows = await conn.fetch("""
        SELECT d.code, d.open, d.high, d.low, d.close,
               d.volume, d.amount, d.change_rate,
               COALESCE(s.market, 'KOSPI') AS market,
               COALESCE(s.name, d.code) AS name
        FROM daily_bars d
        LEFT JOIN stocks s ON s.code = d.code
        WHERE d.date = $1 AND d.close > 0
    """, target_date)
    return {r["code"]: dict(r) for r in rows}


async def fetch_avg_volumes(conn, target_date: date) -> dict[str, float]:
    """최근 20영업일 평균 거래량"""
    rows = await conn.fetch("""
        SELECT code, AVG(volume)::FLOAT AS avg_vol
        FROM daily_bars
        WHERE date >= $1 AND date < $2
        GROUP BY code
    """, target_date - timedelta(days=30), target_date)
    return {r["code"]: float(r["avg_vol"]) for r in rows if r["avg_vol"]}


async def fetch_history(conn, codes: list[str], since: date) -> dict[str, list]:
    """코드별 최근 이력 일봉 (최신→과거 순)"""
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


async def fetch_kospi_index(conn) -> list:
    rows = await conn.fetch("""
        SELECT close FROM daily_bars
        WHERE code = '0001'
        ORDER BY date DESC LIMIT 65
    """)
    return [{"close": r["close"]} for r in rows]


async def fetch_financials(conn, codes: list[str]) -> dict[str, dict]:
    """종목별 최신 재무데이터 (EPS/BPS/debt_ratio → PER/PBR/ROE 계산용)"""
    try:
        rows = await conn.fetch("""
            SELECT DISTINCT ON (code) code, eps, bps, debt_ratio
            FROM financials
            WHERE code = ANY($1::varchar[])
            ORDER BY code, year DESC, quarter DESC NULLS LAST
        """, codes)
        return {
            r["code"]: {
                "eps":        float(r["eps"]        or 0),
                "bps":        float(r["bps"]        or 0),
                "debt_ratio": float(r["debt_ratio"] or 0),
            }
            for r in rows
        }
    except Exception as e:
        log.warning(f"재무 데이터 로드 실패: {e}")
        return {}


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


# ── 기술적 지표 ────────────────────────────────────────────────────────

def _compute_macd_bb(closes_new_to_old: list):
    prices = list(reversed(closes_new_to_old))
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
    is_kosdaq: float,
    kospi_hist: list,
    feature_cols: list,
    fin: dict | None = None,
) -> dict:
    rows    = [today_row] + hist_rows
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
        v = closes[:n]; return sum(v) / len(v) if v else c

    def ma_prev(n, offset=1):
        v = closes[offset:offset + n]
        return sum(v) / len(v) if v else (closes[offset] if len(closes) > offset else c)

    ma5  = ma(5);  ma20 = ma(20); ma60 = ma(60)
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

    rsi14          = _rsi(closes, 14)
    rsi_oversold   = 1.0 if rsi14 < 30 else 0.0
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

    # 수급/공시/뉴스 — Supabase supply_demand/disclosures 없으므로 중립값
    foreign_cumnet_5d    = foreign_cumnet_20d = foreign_cumnet_streak = 0.0
    inst_cumnet_5d       = inst_cumnet_20d    = 0.0
    dual_buy             = dual_buy_3d        = 0.0
    short_ratio          = short_increasing   = 0.0
    foreign_net_ratio    = inst_net_ratio     = 0.0
    disclosure_sentiment = has_favorable_disclosure = 0.0
    news_sentiment_7d    = news_count_7d      = 0.0

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
        market_phase = 1.0 if kc0 > kma60 and kma20 > kma60 else (
            -1.0 if kc0 < kma60 and kma20 < kma60 else 0.0)
    else:
        market_phase = 0.0

    dow   = NOW.weekday()
    month = NOW.month
    dow_sin   = math.sin(2 * math.pi * dow / 7)
    dow_cos   = math.cos(2 * math.pi * dow / 7)
    month_sin = math.sin(2 * math.pi * (month - 1) / 12)
    month_cos = math.cos(2 * math.pi * (month - 1) / 12)

    if fin:
        eps_v       = fin.get("eps", 0.0)
        bps_v       = fin.get("bps", 0.0)
        debt_ratio  = fin.get("debt_ratio", 0.0)
        per         = round(c / eps_v,  2) if eps_v  > 0 else 0.0
        pbr         = round(c / bps_v,  2) if bps_v  > 0 else 0.0
        roe         = round(eps_v / bps_v * 100, 2) if bps_v > 0 else 0.0
    else:
        per = pbr = roe = debt_ratio = 0.0
    log_market_cap = 0.0
    rank_return_5d = rank_vol_ratio = rank_foreign_net = rank_rsi14 = 0.5

    return {k: locals().get(k, 0.0) for k in feature_cols}


# ── 단면 랭크 ─────────────────────────────────────────────────────────

def add_rank_features(feats_list: list[dict]) -> list[dict]:
    if len(feats_list) <= 1:
        return feats_list

    def pct_rank(values):
        n = len(values)
        order = sorted(range(n), key=lambda i: values[i])
        ranks = [0.0] * n
        for rank, idx in enumerate(order):
            ranks[idx] = rank / (n - 1)
        return ranks

    for feat_key, rank_key in [
        ("return_5d",      "rank_return_5d"),
        ("vol_ratio_20d",  "rank_vol_ratio"),
        ("foreign_net_ratio", "rank_foreign_net"),
        ("rsi14",          "rank_rsi14"),
    ]:
        ranks = pct_rank([f.get(feat_key, 0.0) for f in feats_list])
        for i, f in enumerate(feats_list):
            f[rank_key] = ranks[i]

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

    raw_risk = np.clip(models["risk_lgbm"].predict(X), 0.0, 1.0)
    risk_cal = models.get("risk_cal")
    risk     = np.clip(risk_cal.predict(raw_risk), 0.0, 1.0) if risk_cal else raw_risk
    return prob, risk


# ── 추천 저장 ─────────────────────────────────────────────────────────

async def save_recommendations(conn, recs: list[dict]) -> int:
    if not recs:
        return 0
    rows = [
        (
            r["code"], "BUY", r.get("close_price", 0),
            r.get("target_price", 0), r.get("stop_loss_price", 0),
            r["success_prob"], r["risk_score"], r["expected_return"],
            r["hold_days"],
            json.dumps({"vol_ratio": r.get("vol_ratio", 1.0),
                        "change_rate": r.get("change_rate", 0.0),
                        "source": "market_scan"}),
        )
        for r in recs
    ]
    try:
        await conn.executemany("""
            INSERT INTO recommendations
                (code, action, entry_price, target_price, stop_loss_price,
                 success_prob, risk_score,
                 expected_return, expected_hold_days, rationale)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::JSONB)
        """, rows)
    except Exception as e:
        log.error(f"추천 저장 실패: {e}")
        return 0
    return len(rows)


# ── Telegram ──────────────────────────────────────────────────────────

async def send_telegram(msg: str) -> bool:
    if not TG_TOKEN or not TG_CHAT:
        return False
    import urllib.request
    url     = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    success = True
    for chat_id in TG_CHAT.split(","):
        chat_id = chat_id.strip()
        if not chat_id:
            continue
        data = json.dumps({
            "chat_id": chat_id, "text": msg,
            "parse_mode": "HTML", "disable_web_page_preview": True,
        }).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        try:
            urllib.request.urlopen(req, timeout=10)
            log.info(f"Telegram 전송 완료 ({chat_id})")
        except Exception as e:
            log.warning(f"Telegram 전송 실패 ({chat_id}): {e}")
            success = False
    return success


# ── 메인 ─────────────────────────────────────────────────────────────

async def main():
    log.info(f"스캔 시작 {NOW.strftime('%Y-%m-%d %H:%M KST')}")
    cfg = _load_tg_config()

    models, feature_cols = load_models()

    conn = await asyncpg.connect(DSN, statement_cache_size=0)
    try:
        # 최신 영업일 확인
        target_date = await fetch_latest_date(conn)
        if not target_date:
            log.error("daily_bars 데이터 없음")
            return
        log.info(f"기준일: {target_date}")

        # 전 종목 당일 OHLCV
        today_data = await fetch_latest_ohlcv(conn, target_date)
        if not today_data:
            log.warning("당일 OHLCV 없음")
            return
        log.info(f"종목 수: {len(today_data)}개")

        # 20일 평균 거래량 (신호 탐지용)
        avg_vols = await fetch_avg_volumes(conn, target_date)

        # 신호 탐지: 거래량 급등 OR 상승률 조건
        candidates = []
        for code, r in today_data.items():
            vol   = _s(r.get("volume"))
            chg   = _s(r.get("change_rate"))
            avg_v = avg_vols.get(code, 0.0)
            vol_ratio = vol / avg_v if avg_v > 0 else 1.0
            if vol_ratio >= SIGNAL_VOL_RATIO or chg >= SIGNAL_CHANGE_MIN:
                candidates.append(code)
        log.info(f"신호 종목: {len(candidates)}개")

        # 쿨다운 필터
        recent_recs = await get_recent_recs(conn)
        candidates  = [c for c in candidates if c not in recent_recs]
        log.info(f"쿨다운 후 후보: {len(candidates)}개")
        if not candidates:
            log.info("추천 대상 없음 — 종료")
            return

        # 이력 데이터 로드
        since      = target_date - timedelta(days=HISTORY_DAYS + 10)
        hist_data  = await fetch_history(conn, candidates, since)
        kospi_hist = await fetch_kospi_index(conn)
        fin_data   = await fetch_financials(conn, candidates)
        log.info(f"재무 데이터: {len(fin_data)}개 종목")

    finally:
        await conn.close()

    # 피처 계산
    feats_list:  list[dict] = []
    valid_codes: list[str]  = []

    for code in candidates:
        today_r   = today_data.get(code)
        if not today_r or _s(today_r.get("close")) <= 0:
            continue
        hist_rows = hist_data.get(code, [])
        is_kosdaq = 1.0 if today_r.get("market") == "KOSDAQ" else 0.0

        feats = compute_features(today_r, hist_rows, is_kosdaq, kospi_hist, feature_cols,
                                 fin=fin_data.get(code))
        feats_list.append(feats)
        valid_codes.append(code)

    if not feats_list:
        log.info("유효 피처 없음")
        return

    feats_list = add_rank_features(feats_list)

    feats_df        = pd.DataFrame(feats_list)
    probs, risks    = ml_score(feats_df, models, feature_cols)

    log.info(f"점수 분포 — prob: min={probs.min():.3f} mean={probs.mean():.3f} max={probs.max():.3f}"
             f" | risk: min={risks.min():.3f} mean={risks.mean():.3f} max={risks.max():.3f}")

    # 추천 필터링 (설정 UI min_prob 기준)
    tg_min_prob = float(cfg.get("min_prob", SCORE_THRESHOLD))
    tg_max_risk = float(cfg.get("max_risk", RISK_THRESHOLD))
    new_recs = []
    for i, code in enumerate(valid_codes):
        prob = float(probs[i])
        risk = float(risks[i])
        if prob >= tg_min_prob and risk <= tg_max_risk:
            r = today_data[code]
            close = int(_s(r.get("close")))
            new_recs.append({
                "code":            code,
                "name":            r.get("name", code),
                "success_prob":    round(prob, 4),
                "risk_score":      round(risk, 4),
                "expected_return": round((prob - 0.5) * 20.0, 2),
                "hold_days":       5,
                "close_price":     close,
                "target_price":    int(close * 1.10),   # +10%
                "stop_loss_price": int(close * 0.95),   # -5%
                "change_rate":     round(_s(r.get("change_rate")), 2),
                "vol_ratio":       round(feats_list[i].get("vol_ratio_20d", 1.0), 2),
            })

    log.info(f"추천 종목: {len(new_recs)}개 / 후보 {len(valid_codes)}개")
    if not new_recs:
        return

    conn = await asyncpg.connect(DSN, statement_cache_size=0)
    try:
        n = await save_recommendations(conn, new_recs)
        log.info(f"저장 완료: {n}건")

        # ── Telegram 발송 — DB 저장과 동일 기준(이미 필터됨) ──
        tg_enabled = cfg.get("enabled", True)
        tg_recs    = new_recs  # DB 저장 기준과 동일하므로 별도 필터 불필요
        log.info(
            f"텔레그램 발송 대상: {len(tg_recs)}종목 "
            f"(min_prob={tg_min_prob:.3f}, max_risk={tg_max_risk:.3f})"
        )

        if tg_enabled and tg_recs:
            scan_dt = NOW.strftime("%Y-%m-%d %H:%M")
            top     = sorted(tg_recs, key=lambda x: -x["success_prob"])[:5]

            def _pct(a, b):
                try:
                    v = (float(b) - float(a)) / float(a) * 100
                    return f"+{v:.1f}%" if v >= 0 else f"{v:.1f}%"
                except Exception:
                    return "N/A"

            all_msgs = []
            for r in top:
                name  = r.get("name", r["code"])
                code  = r["code"]
                price = r["close_price"]
                tgt   = r["target_price"]
                stp   = r["stop_loss_price"]
                prob  = r["success_prob"]
                name_line  = (
                    f"📌 종목: <b>{name}</b>  (<code>{code}</code>)"
                    if name != code else f"📌 종목: <b>{code}</b>"
                )
                score_line = f"🎯 성공확률: <b>{prob * 100:.0f}%</b>"
                price_line = (
                    f"💰 매수가: <b>{price:,}원</b>"
                    f" / 🏆 목표가: {tgt:,}원 (<code>{_pct(price, tgt)}</code>)"
                    f" / 🚫 손절가: {stp:,}원 (<code>{_pct(price, stp)}</code>)"
                )
                msg = "\n".join([
                    "<b>🚀 매수 추천 알림</b>",
                    name_line, score_line, price_line,
                    f"🕐 탐지 일시: {scan_dt} KST",
                ])
                all_msgs.append((code, name, msg))

            ok = True
            for code, name, msg in all_msgs:
                ok = await send_telegram(msg)
                await _log_telegram(
                    conn,
                    msg_type="scan_daily",
                    title=f"{name} 매수 추천 (장 마감 스캔)",
                    message=msg,
                    success=ok,
                    code=code,
                    name=name,
                )

            if len(tg_recs) > 5:
                summary = (
                    f"<b>📊 장 마감 스캔 완료</b>\n"
                    f"기준 충족 종목: <b>{len(tg_recs)}개</b> (상위 5건 개별 발송)\n"
                    f"🕐 {scan_dt} KST"
                )
                await send_telegram(summary)
        elif not tg_enabled:
            log.info("텔레그램 알림 비활성화 — 발송 스킵")
        else:
            log.info("텔레그램 발송 기준 충족 종목 없음 — 발송 스킵")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
