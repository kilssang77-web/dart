"""
feature_events.pattern_vector(256차원) 일괄 생성.
recommender/pattern_vector.py의 로직을 재구현 (ml container에서 실행).

벡터 구성 (256차원):
  [0:20]   최근 20일 정규화 종가
  [20:40]  최근 20일 정규화 거래량
  [40:60]  최근 20일 정규화 수급(외인+기관)
  [60:256] 기술적 지표 (RSI, MACD hist, BB%B, H-L ratio, returns)

사용:
  docker compose run --rm ml python /app/scripts/generate_pattern_vectors.py
  docker compose run --rm ml python /app/scripts/generate_pattern_vectors.py --all
"""
import asyncio
import asyncpg
import logging
import os
import sys
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("gen_vectors")

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
    return 100.0 - 100.0 / (1 + avg_g / avg_l)


def _normalize(arr: np.ndarray) -> np.ndarray:
    std = arr.std()
    if std == 0:
        return np.zeros_like(arr)
    return (arr - arr.mean()) / std


def build_vector(bars: list[dict]) -> np.ndarray | None:
    if len(bars) < 20:
        return None

    closes  = np.array([float(b["close"])  for b in bars], dtype=float)
    volumes = np.array([float(b["volume"]) for b in bars], dtype=float)
    highs   = np.array([float(b["high"])   for b in bars], dtype=float)
    lows    = np.array([float(b["low"])    for b in bars], dtype=float)
    f_nets  = np.array([float(b.get("foreign_net_buy") or 0) for b in bars], dtype=float)
    i_nets  = np.array([float(b.get("inst_net_buy")    or 0) for b in bars], dtype=float)

    # sec1: 최근 20일 정규화 종가 (20d)
    sec1 = _normalize(closes[-20:])

    # sec2: 최근 20일 정규화 거래량 (20d)
    sec2 = _normalize(volumes[-20:])

    # sec3: 정규화 수급 외인+기관 (20d)
    net_flow = f_nets[-20:] + i_nets[-20:]
    sec3 = _normalize(net_flow)

    # sec4: 기술적 지표 벡터 (196d)
    indicators: list[float] = []

    # RSI(14) 최근 10포인트
    for i in range(min(10, len(closes))):
        indicators.append(_rsi(closes[: len(closes) - i].tolist()))

    # MACD hist (12,26,9)
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

    # H-L ratio 최근 20일
    hl_ratio = (highs[-20:] - lows[-20:]) / (closes[-20:] + 1)
    indicators.extend(_normalize(hl_ratio).tolist())

    # 전일비 수익률 최근 20일
    if len(closes) >= 21:
        returns = np.diff(closes[-21:]) / (closes[-21:-1] + 1)
        indicators.extend(_normalize(returns).tolist())

    # 196차원으로 패딩
    sec4 = np.array(indicators[:196], dtype=float)
    if len(sec4) < 196:
        sec4 = np.concatenate([sec4, np.zeros(196 - len(sec4))])

    vec = np.concatenate([sec1, sec2, sec3, sec4]).astype(np.float32)
    if len(vec) != PATTERN_DIM:
        logger.warning(f"dim mismatch: {len(vec)}, expected {PATTERN_DIM}")
        return None
    return vec


async def process_batch(conn: asyncpg.Connection, events: list[dict], bars_by_code: dict) -> int:
    updates = []
    for ev in events:
        code = ev["code"]
        bars = bars_by_code.get(code, [])
        if len(bars) < 20:
            continue

        ev_date = str(ev.get("detected_at", ""))[:10]
        bars_before = [b for b in bars if str(b["date"])[:10] <= ev_date] if ev_date else bars
        if len(bars_before) < 20:
            bars_before = bars  # 날짜 필터가 너무 공격적이면 전체 사용

        vec = build_vector(bars_before)
        if vec is None:
            continue

        vec_str = "[" + ",".join(f"{v:.6f}" for v in vec.tolist()) + "]"
        updates.append((vec_str, ev["id"]))

    if not updates:
        return 0

    await conn.executemany(
        "UPDATE feature_events SET pattern_vector = $1::vector WHERE id = $2",
        updates,
    )
    return len(updates)


async def main() -> None:
    update_all = "--all" in sys.argv
    dsn = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    db  = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=5)

    async with db.acquire() as conn:
        if update_all:
            events = await conn.fetch(
                "SELECT id, code, detected_at FROM feature_events ORDER BY detected_at"
            )
        else:
            events = await conn.fetch(
                "SELECT id, code, detected_at FROM feature_events "
                "WHERE pattern_vector IS NULL ORDER BY detected_at"
            )

    total = len(events)
    logger.info(f"벡터 생성 대상: {total}개")
    if not total:
        await db.close()
        return

    # 필요한 종목 코드만 daily_bars 일괄 조회
    codes = list({e["code"] for e in events})
    async with db.acquire() as conn:
        bar_rows = await conn.fetch(
            """
            SELECT code, date, close, high, low, volume, foreign_net_buy, inst_net_buy
            FROM daily_bars
            WHERE code = ANY($1)
            ORDER BY code, date
            """,
            codes,
        )
    bars_by_code: dict[str, list[dict]] = {}
    for r in bar_rows:
        bars_by_code.setdefault(r["code"], []).append(dict(r))

    done = 0
    BATCH = 500
    async with db.acquire() as conn:
        for i in range(0, total, BATCH):
            batch = [dict(e) for e in events[i : i + BATCH]]
            n = await process_batch(conn, batch, bars_by_code)
            done += n
            logger.info(f"진행: {i + len(batch)}/{total} (벡터생성: {done})")

    await db.close()
    logger.info(f"완료: {done}개 feature_events.pattern_vector 생성")


if __name__ == "__main__":
    asyncio.run(main())
