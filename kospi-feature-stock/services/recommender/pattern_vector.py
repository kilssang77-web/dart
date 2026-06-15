"""
feature_events 저장 후 pattern_vector 생성 및 DB 업데이트.
daily_bars 데이터에서 256차원 벡터 생성 (ML 유사도 검색용).

벡터 구조 v3 (256dims):
  sec1 [0:20]   — 정규화 종가 시계열 (20일)
  sec2 [20:40]  — 정규화 거래량 시계열 (20일)
  sec3 [40:60]  — 정규화 수급 시계열 (외인+기관, 20일)
  sec4 [60:256] — 기술지표 196차원 (제로패딩 없음):
    [0:20]   RSI14 시계열
    [20:40]  MACD hist 시계열
    [40:60]  BB%B 시계열
    [60:80]  ATR ratio 시계열
    [80:100] 거래량 비율 시계열
    [100:120] 정규화 외국인 순매수 시계열
    [120:140] 정규화 기관 순매수 시계열
    [140:196] 50개 스칼라 지표
"""
import logging
import asyncpg
import numpy as np

logger = logging.getLogger(__name__)

PATTERN_DIM = 256


def _ema(values: list[float], span: int) -> list[float]:
    result, alpha = [], 2.0 / (span + 1)
    for i, v in enumerate(values):
        if i == 0:
            result.append(v)
        else:
            result.append(alpha * v + (1 - alpha) * result[-1])
    return result


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains  = [d if d > 0 else 0.0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0.0 for d in deltas[-period:]]
    avg_g  = sum(gains)  / period
    avg_l  = sum(losses) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100.0 - 100.0 / (1 + rs)


def _normalize(arr: np.ndarray) -> np.ndarray:
    std = arr.std()
    if std == 0:
        return np.zeros_like(arr)
    return (arr - arr.mean()) / std


def _clip_norm(v: float, lo: float, hi: float) -> float:
    """[lo,hi] 범위로 클리핑 후 [-1,1]로 정규화."""
    return (np.clip(v, lo, hi) - lo) / (hi - lo) * 2.0 - 1.0


def build_vector(bars: list[dict], disclosure_score: float = 0.0) -> np.ndarray | None:
    """일봉 데이터 리스트 → 256D 패턴 벡터 v3.
    bars: 시간순(오래된→최신) 정렬된 OHLCV 딕셔너리 리스트.
    disclosure_score: 최근 공시 감성 (-1.0~1.0).
    """
    if len(bars) < 20:
        return None

    n = len(bars)
    closes   = np.array([float(b["close"])  for b in bars], dtype=float)
    volumes  = np.array([float(b["volume"]) for b in bars], dtype=float)
    highs    = np.array([float(b["high"])   for b in bars], dtype=float)
    lows     = np.array([float(b["low"])    for b in bars], dtype=float)
    opens    = np.array([float(b.get("open") or b["close"]) for b in bars], dtype=float)
    amounts  = np.array([float(b.get("amount") or (b["close"] * b["volume"])) for b in bars], dtype=float)
    f_nets   = np.array([float(b.get("foreign_net_buy") or 0) for b in bars], dtype=float)
    i_nets   = np.array([float(b.get("inst_net_buy")    or 0) for b in bars], dtype=float)

    c = closes[-1]

    # ── sec1: 최근 20일 정규화 종가 ────────────────────────────
    sec1 = _normalize(closes[-20:])

    # ── sec2: 최근 20일 정규화 거래량 ──────────────────────────
    sec2 = _normalize(volumes[-20:])

    # ── sec3: 정규화 수급 (외인+기관, 20일) ────────────────────
    sec3 = _normalize(f_nets[-20:] + i_nets[-20:])

    # ── MACD/BB 사전 계산 (sec4 시계열 + 스칼라 공유) ─────────
    if n >= 26:
        ema12 = np.array(_ema(closes.tolist(), 12))
        ema26 = np.array(_ema(closes.tolist(), 26))
        macd_line = ema12 - ema26
        macd_sig  = np.array(_ema(macd_line.tolist(), 9))
        hist_full = macd_line - macd_sig
    else:
        hist_full = np.zeros(n)

    if n >= 20:
        _ma20  = np.convolve(closes, np.ones(20) / 20, mode="valid")  # shape: n-19
        _std20 = np.array([closes[i:i+20].std() for i in range(n - 19)])
        _bbup  = _ma20 + 2 * _std20
        _bblo  = _ma20 - 2 * _std20
        bb_pct_full = np.where(_bbup != _bblo, (closes[19:] - _bblo) / (_bbup - _bblo), 0.5)
        bbup_last = float(_bbup[-1]);  bblo_last = float(_bblo[-1])
    else:
        bb_pct_full = np.full(max(n - 19, 1), 0.5)
        bbup_last = c * 1.05;  bblo_last = c * 0.95

    # ── sec4: 196차원 기술지표 시계열(140) + 스칼라(56) ────────
    # [0:20] RSI14 시계열 — 최근 20일 각 포인트의 RSI 값
    rsi_series = np.array([
        _rsi(closes[:max(n - 19 + i, 15)].tolist())
        for i in range(20)
    ], dtype=float) / 100.0  # [0,1]

    # [20:40] MACD hist 시계열
    hist_20 = hist_full[-20:] if len(hist_full) >= 20 else np.pad(hist_full, (20 - len(hist_full), 0))
    macd_series = _normalize(hist_20)

    # [40:60] BB%B 시계열
    bb_20 = bb_pct_full[-20:] if len(bb_pct_full) >= 20 else np.pad(bb_pct_full, (20 - len(bb_pct_full), 0), constant_values=0.5)
    bb_series = np.clip(bb_20, -0.5, 1.5)  # 이상치 제한

    # [60:80] ATR ratio 시계열
    atr_series = _normalize((highs[-20:] - lows[-20:]) / (closes[-20:] + 1e-8))

    # [80:100] 거래량 비율 시계열 (vs 20일 평균)
    vol20_avg = float(volumes[-20:].mean()) if n >= 20 else float(volumes.mean())
    vol_ratio_series = _normalize(volumes[-20:] / (vol20_avg + 1e-8))

    # [100:120] 정규화 외국인 순매수
    fnet_series = _normalize(f_nets[-20:])

    # [120:140] 정규화 기관 순매수
    inet_series = _normalize(i_nets[-20:])

    # ── 스칼라 사전 계산 ──────────────────────────────────────
    def _ma(n_bars): return float(closes[-n_bars:].mean()) if len(closes) >= n_bars else c
    ma5 = _ma(5); ma20 = _ma(20); ma60 = _ma(60)
    ma5_ratio  = c / ma5  if ma5  else 1.0
    ma20_ratio = c / ma20 if ma20 else 1.0
    ma60_ratio = c / ma60 if ma60 else 1.0

    ma5_slope  = (ma5 / (float(closes[-10:-5].mean()) if n >= 10 else c) - 1) if n >= 10 else 0.0
    ma20_slope = (ma20 / (float(closes[-40:-20].mean()) if n >= 40 else c) - 1) if n >= 40 else 0.0

    vol5 = float(volumes[-5:].mean()); vol20v = float(volumes[-20:].mean()) if n >= 20 else vol5
    vol_ratio_5d  = volumes[-1] / (vol5  + 1e-8)
    vol_ratio_20d = volumes[-1] / (vol20v + 1e-8)
    vol_surge     = 1.0 if vol_ratio_20d >= 3.0 else 0.0
    amt20 = float(amounts[-20:].mean()) if n >= 20 else float(amounts.mean())
    amount_ratio  = amounts[-1] / (amt20 + 1e-8)

    atr14 = float((highs[-14:] - lows[-14:]).mean()) if n >= 14 else float((highs - lows).mean())
    atr_ratio_s = atr14 / (c + 1e-8)

    rsi14_v = _rsi(closes.tolist())
    rsi_os  = 1.0 if rsi14_v < 30 else 0.0
    rsi_ob  = 1.0 if rsi14_v > 70 else 0.0

    macd_h_s = float(hist_full[-1]) / (c * 0.01 + 1e-8) if n >= 26 else 0.0
    macd_h_p = float(hist_full[-2]) if n >= 27 else macd_h_s
    macd_gc  = 1.0 if float(hist_full[-1]) > 0 and macd_h_p <= 0 else 0.0

    bb_pct_s  = float(bb_pct_full[-1]) if len(bb_pct_full) > 0 else 0.5
    bb_rng    = bbup_last - bblo_last
    bb_width_s = bb_rng / (c + 1e-8)
    bb_squeeze = 1.0 if bb_width_s < 0.04 else 0.0

    o = opens[-1]; body = abs(c - o); rng = max(highs[-1] - lows[-1], 1.0)
    body_size  = body / rng
    is_bullish = 1.0 if c > o else 0.0
    upper_wick = (highs[-1] - max(c, o)) / rng
    lower_wick = (min(c, o) - lows[-1])  / rng

    nh20  = 1.0 if n >= 21 and c >= float(closes[-21:-1].max()) else 0.0
    nh52w = 1.0 if n >= 131 and c >= float(closes[-131:-1].max()) else 0.0
    hi52  = float(closes[-131:-1].max()) if n >= 131 else c
    lo52  = float(closes[-131:-1].min()) if n >= 131 else c
    pos_52w = (c - lo52) / (hi52 - lo52) if hi52 != lo52 else 0.5

    f5 = float(f_nets[-5:].sum()); f3 = float(f_nets[-3:].sum())
    i5 = float(i_nets[-5:].sum()); i3 = float(i_nets[-3:].sum())
    dual_buy   = 1.0 if f5 > 0 and i5 > 0 else 0.0
    dual_buy_3d = 1.0 if f3 > 0 and i3 > 0 else 0.0
    fnet_5d_norm = np.clip(f5 / (amt20 * 1e6 + 1e-8), -1.0, 1.0)
    inet_5d_norm = np.clip(i5 / (amt20 * 1e6 + 1e-8), -1.0, 1.0)

    disc = float(max(-1.0, min(1.0, disclosure_score)))

    def _ret(k): return (c / closes[-k-1] - 1) * 100 if n > k and closes[-k-1] > 0 else 0.0
    r1d=_ret(1); r3d=_ret(3); r5d=_ret(5); r10d=_ret(10); r20d=_ret(20)
    prior5 = (closes[-6] / closes[-11] - 1) * 100 if n >= 11 and closes[-11] > 0 else 0.0
    price_accel = r5d - prior5
    gap_pct = (opens[-1] / closes[-2] - 1) * 100 if n >= 2 and closes[-2] > 0 else 0.0

    consec_up = consec_down = 0
    for j in range(1, min(n, 11)):
        if closes[-j] > closes[-(j+1)]:
            if consec_down == 0: consec_up += 1
            else: break
        elif closes[-j] < closes[-(j+1)]:
            if consec_up == 0: consec_down += 1
            else: break
        else:
            break

    up_v  = sum(float(volumes[-j]) for j in range(1, min(n, 11)) if closes[-j] > closes[-(j+1)])
    dn_v  = sum(float(volumes[-j]) for j in range(1, min(n, 11)) if closes[-j] < closes[-(j+1)])
    vol_ud = up_v / (dn_v + 1e-8)

    ma5_p  = float(closes[-6:-1].mean())  if n >= 6  else ma5
    ma20_p = float(closes[-21:-1].mean()) if n >= 21 else ma20
    ma60_p = float(closes[-61:-1].mean()) if n >= 61 else ma60
    ma5_ma20_cross  = 1.0 if ma5  >= ma20 and ma5_p  < ma20_p else 0.0
    ma20_ma60_cross = 1.0 if ma20 >= ma60 and ma20_p < ma60_p else 0.0

    price_range_20d = (float(closes[-20:].max()) - float(closes[-20:].min())) / (c + 1e-8) if n >= 20 else 0.0
    dist_from_high20 = c / (float(closes[-20:].max()) + 1e-8) - 1.0 if n >= 20 else 0.0
    dist_from_low20  = c / (float(closes[-20:].min()) + 1e-8) - 1.0 if n >= 20 else 0.0
    atr_avg_20 = float((highs[-20:] - lows[-20:]).mean()) if n >= 20 else atr14
    atr_trend = atr14 / (atr_avg_20 + 1e-8)
    vol_momentum = vol_ratio_5d / (vol_ratio_20d + 1e-8)
    # 최근 5일 일간수익률 표준편차 (단기 변동성)
    drets5 = np.diff(closes[-6:]) / (closes[-6:-1] + 1e-8) * 100 if n >= 6 else np.zeros(1)
    vol_5d_intraday = float(drets5.std()) if len(drets5) > 1 else 0.0

    # [140:196] 50개 스칼라 + 6 예약
    scalars = np.array([
        _clip_norm(ma5_ratio,  0.8, 1.2),  # MA 비율 (5)
        _clip_norm(ma20_ratio, 0.8, 1.2),
        _clip_norm(ma60_ratio, 0.8, 1.2),
        np.clip(ma5_slope,  -0.1, 0.1) * 10,
        np.clip(ma20_slope, -0.1, 0.1) * 10,
        _clip_norm(vol_ratio_5d,  0.0, 5.0),  # 거래량 (5)
        _clip_norm(vol_ratio_20d, 0.0, 5.0),
        vol_surge,
        _clip_norm(amount_ratio, 0.0, 5.0),
        np.clip(atr_ratio_s, 0.0, 0.1) * 20,
        (rsi14_v - 50.0) / 50.0,   # RSI (3)
        rsi_os,
        rsi_ob,
        np.clip(macd_h_s, -1.0, 1.0),   # MACD (2)
        macd_gc,
        bb_pct_s * 2.0 - 1.0,           # BB (3)
        np.clip(bb_width_s, 0.0, 0.2) * 5.0,
        bb_squeeze,
        body_size,                        # 캔들 (4)
        is_bullish,
        upper_wick,
        lower_wick,
        nh20,                             # 신고가/위치 (4)
        nh52w,
        0.0,                              # nh260 (bars 부족 시 0)
        pos_52w * 2.0 - 1.0,
        dual_buy,                         # 수급 (4)
        dual_buy_3d,
        fnet_5d_norm,
        inet_5d_norm,
        disc,                             # 공시 (1)
        np.clip(r1d,  -10.0, 10.0) / 10.0,  # 수익률 (5)
        np.clip(r3d,  -15.0, 15.0) / 15.0,
        np.clip(r5d,  -20.0, 20.0) / 20.0,
        np.clip(r10d, -30.0, 30.0) / 30.0,
        np.clip(r20d, -40.0, 40.0) / 40.0,
        np.clip(price_accel, -10.0, 10.0) / 10.0,  # 가속도/갭 (2)
        np.clip(gap_pct, -5.0, 5.0) / 5.0,
        consec_up  / 10.0,                # 연속 (2)
        consec_down / 10.0,
        np.clip(vol_ud, 0.0, 5.0) / 5.0, # 기타 (6)
        ma5_ma20_cross,
        _clip_norm(price_range_20d, 0.0, 0.5),
        np.clip(atr_trend - 1.0, -1.0, 2.0),
        np.clip(vol_momentum - 1.0, -1.0, 3.0),   # 45
        ma20_ma60_cross,                            # 46
        np.clip(dist_from_high20, -0.5, 0.0) * 2,  # 47 (고점 대비 거리, ≤0)
        np.clip(dist_from_low20,   0.0, 1.0),       # 48 (저점 대비 거리, ≥0)
        np.clip(vol_5d_intraday, 0.0, 5.0) / 5.0,  # 49 (단기 변동성)
        0.0, 0.0, 0.0, 0.0, 0.0,                   # 50-54 예약
        0.0,                                         # 55 예약
        0.0,                                         # 56 예약 (총 56 = 49개 지표 + 7 예약)
    ], dtype=float)

    # sec4 조립 (7×20 시계열 = 140 + 56 스칼라 = 196)
    sec4 = np.concatenate([
        rsi_series,    # [0:20]
        macd_series,   # [20:40]
        bb_series,     # [40:60]
        atr_series,    # [60:80]
        vol_ratio_series,  # [80:100]
        fnet_series,   # [100:120]
        inet_series,   # [120:140]
        scalars,       # [140:196]
    ])

    vec = np.concatenate([sec1, sec2, sec3, sec4]).astype(np.float32)
    assert len(vec) == PATTERN_DIM, f"dim mismatch: {len(vec)}"

    if not np.isfinite(vec).all():
        vec = np.nan_to_num(vec, nan=0.0, posinf=1.0, neginf=-1.0)

    return vec


async def update_pattern_vector(pool: asyncpg.Pool, event_id: int, code: str) -> bool:
    """DB에서 일봉 데이터를 가져와 벡터 생성 후 feature_events 업데이트"""
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT date, open, high, low, close, volume, amount, foreign_net_buy, inst_net_buy
                FROM daily_bars
                WHERE code = $1
                ORDER BY date DESC
                LIMIT 60
                """,
                code,
            )
            if len(rows) < 20:
                return False

            # 최근 공시 감성 점수 조회 (7일 이내)
            disc_row = await conn.fetchrow(
                """
                SELECT sentiment_score FROM disclosures
                WHERE code = $1
                  AND disclosed_at >= NOW() - INTERVAL '7 days'
                ORDER BY disclosed_at DESC
                LIMIT 1
                """,
                code,
            )
            disclosure_score = float(disc_row["sentiment_score"]) if disc_row and disc_row["sentiment_score"] is not None else 0.0

            bars = [dict(r) for r in reversed(rows)]  # 오래된 것부터
            vec  = build_vector(bars, disclosure_score)
            if vec is None:
                return False

            vec_str = "[" + ",".join(f"{v:.6f}" for v in vec.tolist()) + "]"
            await conn.execute(
                "UPDATE feature_events SET pattern_vector = $1::vector WHERE id = $2",
                vec_str, event_id,
            )
            return True

    except Exception as e:
        logger.warning(f"[PatternVector] update failed event_id={event_id} code={code}: {e}")
        return False
