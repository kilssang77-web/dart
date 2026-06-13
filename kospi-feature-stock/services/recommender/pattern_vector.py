"""
feature_events 저장 후 pattern_vector 생성 및 DB 업데이트.
daily_bars 데이터에서 256차원 벡터 생성 (ML 유사도 검색용).
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


def build_vector(bars: list[dict], disclosure_score: float = 0.0) -> np.ndarray | None:
    """일봉 데이터 리스트 → 256D 패턴 벡터.
    disclosure_score: 최근 공시 감성 (-1.0~1.0, 공시없으면 0.0)
    """
    if len(bars) < 20:
        return None

    closes   = np.array([float(b["close"])  for b in bars], dtype=float)
    volumes  = np.array([float(b["volume"]) for b in bars], dtype=float)
    highs    = np.array([float(b["high"])   for b in bars], dtype=float)
    lows     = np.array([float(b["low"])    for b in bars], dtype=float)
    f_nets   = np.array([float(b.get("foreign_net_buy") or 0) for b in bars], dtype=float)
    i_nets   = np.array([float(b.get("inst_net_buy")    or 0) for b in bars], dtype=float)

    # ── 섹션 1: 최근 20일 정규화 종가 (20d) ──────────────────
    sec1 = _normalize(closes[-20:])

    # ── 섹션 2: 최근 20일 정규화 거래량 (20d) ────────────────
    sec2 = _normalize(volumes[-20:])

    # ── 섹션 3: 정규화 수급 (외인+기관, 20d) ─────────────────
    net_flow = f_nets[-20:] + i_nets[-20:]
    sec3 = _normalize(net_flow)

    # ── 섹션 4: 기술적 지표 벡터 (196d) ─────────────────────
    indicators = []

    # RSI (14) — 마지막 10개 포인트
    for i in range(min(10, len(closes))):
        indicators.append(_rsi(closes[: len(closes) - i].tolist()))

    # MACD (12,26,9)
    if len(closes) >= 26:
        ema12 = np.array(_ema(closes.tolist(), 12))
        ema26 = np.array(_ema(closes.tolist(), 26))
        macd  = ema12 - ema26
        sig   = np.array(_ema(macd.tolist(), 9))
        hist  = macd - sig
        indicators.extend(_normalize(hist[-10:]).tolist())

    # Bollinger %B (20일)
    if len(closes) >= 20:
        ma20  = np.convolve(closes, np.ones(20) / 20, mode="valid")
        std20 = np.array([closes[i:i+20].std() for i in range(len(closes)-19)])
        bb_up = ma20 + 2 * std20
        bb_lo = ma20 - 2 * std20
        bb_pct = np.where(bb_up != bb_lo, (closes[19:] - bb_lo) / (bb_up - bb_lo), 0.5)
        indicators.extend(bb_pct[-10:].tolist())

    # 고저 비율 (High-Low / Close), 최근 20일
    hl_ratio = (highs[-20:] - lows[-20:]) / (closes[-20:] + 1)
    indicators.extend(_normalize(hl_ratio).tolist())

    # 전일비 수익률, 최근 20일
    returns = np.diff(closes[-21:]) / (closes[-21:-1] + 1)
    indicators.extend(_normalize(returns).tolist())

    # 최대 195개 + 공시 감성 1개 = 196
    sec4 = np.array(indicators[:195], dtype=float)
    if len(sec4) < 195:
        sec4 = np.concatenate([sec4, np.zeros(195 - len(sec4))])
    # 마지막 원소: 공시 감성 (favorable=+1, unfavorable=-1, none=0)
    sec4 = np.concatenate([sec4, [float(max(-1.0, min(1.0, disclosure_score)))]])

    vec = np.concatenate([sec1, sec2, sec3, sec4]).astype(np.float32)
    assert len(vec) == PATTERN_DIM, f"dim mismatch: {len(vec)}"
    return vec


async def update_pattern_vector(pool: asyncpg.Pool, event_id: int, code: str) -> bool:
    """DB에서 일봉 데이터를 가져와 벡터 생성 후 feature_events 업데이트"""
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT date, close, high, low, volume, foreign_net_buy, inst_net_buy
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
