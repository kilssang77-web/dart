"""
Feature Event 역사적 백필 (2020~현재)

daily_bars 기반으로 BatchScanner 동일 로직을 과거 전체 거래일에 적용.
- result_1d/3d/5d: 사후 실제 수익률 계산 (유사사례 학습 품질 향상)
- ON CONFLICT DO NOTHING: 재실행 안전
- 1회 실행으로 feature_events 5,000+ 목표
"""

import asyncio
import asyncpg
import logging
import os
import json
import argparse
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [backfill] %(levelname)s - %(message)s",
)
logger = logging.getLogger("backfill")

# 탐지 임계값 (batch_scanner와 동일)
VOL_SURGE_RATIO    = float(os.environ.get("BATCH_VOL_SURGE_RATIO",    "3.0"))
AMOUNT_SURGE_RATIO = float(os.environ.get("BATCH_AMOUNT_SURGE_RATIO", "3.0"))
SUPPLY_SURGE_RATIO = float(os.environ.get("BATCH_SUPPLY_SURGE_RATIO", "3.0"))
BREAKOUT_MIN_PCT   = float(os.environ.get("BATCH_BREAKOUT_MIN_PCT",   "0.001"))
MIN_AMOUNT         = int(os.environ.get("BATCH_MIN_AMOUNT",            "500000000"))

CANDLE_BODY_RATIO  = float(os.environ.get("CANDLE_LONG_WHITE_BODY_RATIO", "0.65"))
CANDLE_MIN_CHANGE  = float(os.environ.get("CANDLE_LONG_WHITE_MIN_CHANGE", "3.0"))

BATCH_SIZE         = int(os.environ.get("BACKFILL_BATCH_SIZE", "30"))   # 한 번에 처리할 날짜 수
CONCURRENCY        = int(os.environ.get("BACKFILL_CONCURRENCY", "4"))   # 동시 날짜 처리 수

_BREAKOUT_CONF = [
    ("BREAKOUT_52W", "high_52w", 0.80),
    ("BREAKOUT_26W", "high_26w", 0.70),
    ("BREAKOUT_13W", "high_13w", 0.60),
    ("BREAKOUT_20D", "high_20d", 0.50),
]


def _detect_events(row: dict) -> list[dict]:
    """단일 종목/날짜 row에서 이벤트 탐지 — batch_scanner._detect와 동일 로직."""
    results = []
    code        = row["code"]
    price       = row["close"]   or 0
    o           = row["open"]    or 0
    h           = row["high"]    or 0
    l           = row["low"]     or 0
    volume      = row["volume"]  or 0
    amount      = row["amount"]  or 0
    change_rate = float(row["change_rate"] or 0)
    foreign     = row["foreign_net_buy"] or 0
    inst        = row["inst_net_buy"]    or 0

    avg_vol    = float(row["avg_vol_20d"]    or 0)
    avg_amt    = float(row["avg_amount_20d"] or 0)
    avg_f      = float(row["avg_foreign_20d"] or 0)
    avg_i      = float(row["avg_inst_20d"]   or 0)

    base = dict(code=code, price=price, change_rate=change_rate,
                volume=volume, amount=amount)

    # 1. 거래량 급증
    if avg_vol > 0 and volume > avg_vol * VOL_SURGE_RATIO:
        ratio = volume / avg_vol
        score = min(0.95, 0.50 + (ratio - VOL_SURGE_RATIO) / (VOL_SURGE_RATIO * 4))
        results.append({**base,
            "event_type":   "VOLUME_SURGE",
            "volume_ratio": round(ratio, 2),
            "signal_score": round(score, 3),
            "signal_data":  {"avg_vol_20d": int(avg_vol), "vol_ratio": round(ratio, 2)},
        })

    # 2. 거래대금 급증
    if avg_amt > 0 and amount > avg_amt * AMOUNT_SURGE_RATIO:
        ratio = amount / avg_amt
        score = min(0.90, 0.45 + (ratio - AMOUNT_SURGE_RATIO) / (AMOUNT_SURGE_RATIO * 4))
        results.append({**base,
            "event_type":   "AMOUNT_SURGE",
            "volume_ratio": round(ratio, 2),
            "signal_score": round(score, 3),
            "signal_data":  {"avg_amount_20d": int(avg_amt), "amount_ratio": round(ratio, 2)},
        })

    # 3. 신고가 돌파
    for evt_type, key, base_score in _BREAKOUT_CONF:
        prev_high = float(row.get(key) or 0)
        if prev_high > 0 and price > prev_high * (1 + BREAKOUT_MIN_PCT):
            excess_pct = (price - prev_high) / prev_high * 100
            score = min(0.95, base_score + excess_pct / 20.0)
            results.append({**base,
                "event_type":   evt_type,
                "volume_ratio": None,
                "signal_score": round(score, 3),
                "signal_data":  {"prev_high": int(prev_high), "excess_pct": round(excess_pct, 2)},
            })

    # 4. 장대양봉
    if price > 0 and o > 0 and h > l:
        body   = abs(price - o)
        rng    = h - l
        body_r = body / rng if rng else 0
        chg_pct = (price - o) / o * 100
        if body_r >= CANDLE_BODY_RATIO and chg_pct >= CANDLE_MIN_CHANGE and price > o:
            score = min(0.92, 0.50 + body_r * 0.4 + min(chg_pct / 20.0, 0.10))
            results.append({**base,
                "event_type":   "LONG_WHITE_CANDLE",
                "volume_ratio": None,
                "signal_score": round(score, 3),
                "signal_data":  {"body_ratio": round(body_r, 3), "change_pct": round(chg_pct, 2)},
            })

        # 5. 망치형 캔들
        lower_shadow = min(o, price) - l
        upper_shadow = h - max(o, price)
        if body > 0 and lower_shadow >= 2 * body and upper_shadow <= 0.1 * body:
            ratio_val = lower_shadow / body
            score = min(0.72, 0.45 + ratio_val * 0.05)
            results.append({**base,
                "event_type":   "HAMMER_CANDLE",
                "volume_ratio": None,
                "signal_score": round(score, 3),
                "signal_data":  {"lower_shadow_ratio": round(ratio_val, 2)},
            })

    # 6. 수급 이상
    surge_n, max_ratio = 0, 0.0
    if avg_f > 0 and foreign > avg_f * SUPPLY_SURGE_RATIO:
        r = foreign / avg_f; surge_n += 1; max_ratio = max(max_ratio, r)
    if avg_i > 0 and inst > avg_i * SUPPLY_SURGE_RATIO:
        r = inst / avg_i; surge_n += 1; max_ratio = max(max_ratio, r)
    if surge_n:
        score = min(0.95, 0.35 + max_ratio / (SUPPLY_SURGE_RATIO * 4) + surge_n * 0.10)
        results.append({**base,
            "event_type":   "SUPPLY_ANOMALY",
            "volume_ratio": None,
            "signal_score": round(score, 3),
            "signal_data":  {
                "foreign_net": int(foreign), "inst_net": int(inst),
                "f_ratio": round(foreign / avg_f if avg_f else 0, 2),
                "i_ratio": round(inst    / avg_i if avg_i else 0, 2),
            },
        })

    # risk_score 보정
    for ev in results:
        ev["risk_score"] = round(max(0.15, 0.80 - ev["signal_score"]), 3)

    return results


async def process_date(pool: asyncpg.Pool, target_date, sem: asyncio.Semaphore) -> int:
    """단일 날짜 처리: 탐지 + 결과 수익률 계산 + 저장."""
    async with sem:
        async with pool.acquire() as conn:
            # ── 1. 당일 바 + 20일 롤링 통계 + 신고가 기준 ──────────
            rows = await conn.fetch(
                """
                WITH base AS (
                    SELECT
                        b.code, b.date, b.open, b.high, b.low, b.close,
                        b.volume, b.amount, b.change_rate,
                        COALESCE(b.foreign_net_buy, 0) AS foreign_net_buy,
                        COALESCE(b.inst_net_buy,    0) AS inst_net_buy,
                        AVG(b.volume)              OVER w AS avg_vol_20d,
                        AVG(b.amount)              OVER w AS avg_amount_20d,
                        AVG(b.foreign_net_buy::float) OVER w AS avg_foreign_20d,
                        AVG(b.inst_net_buy::float)    OVER w AS avg_inst_20d
                    FROM daily_bars b
                    WHERE b.code IN (
                        SELECT code FROM daily_bars WHERE date = $1 AND amount >= $2
                    )
                      AND b.date >= $1 - INTERVAL '120 days'
                      AND b.date <= $1
                    WINDOW w AS (
                        PARTITION BY b.code ORDER BY b.date
                        ROWS BETWEEN 21 PRECEDING AND 1 PRECEDING
                    )
                ),
                highs AS (
                    SELECT
                        code,
                        MAX(close) FILTER (WHERE date >= $1 - INTERVAL '30 days')  AS high_20d,
                        MAX(close) FILTER (WHERE date >= $1 - INTERVAL '100 days') AS high_13w,
                        MAX(close) FILTER (WHERE date >= $1 - INTERVAL '200 days') AS high_26w,
                        MAX(close) FILTER (WHERE date >= $1 - INTERVAL '400 days') AS high_52w
                    FROM daily_bars
                    WHERE date < $1
                      AND date >= $1 - INTERVAL '400 days'
                    GROUP BY code
                ),
                future AS (
                    SELECT
                        code,
                        date,
                        LEAD(close, 1) OVER (PARTITION BY code ORDER BY date) AS close_1d,
                        LEAD(close, 3) OVER (PARTITION BY code ORDER BY date) AS close_3d,
                        LEAD(close, 5) OVER (PARTITION BY code ORDER BY date) AS close_5d
                    FROM daily_bars
                    WHERE date >= $1
                      AND date <= $1 + INTERVAL '10 days'
                )
                SELECT
                    b.*,
                    h.high_20d, h.high_13w, h.high_26w, h.high_52w,
                    f.close_1d, f.close_3d, f.close_5d
                FROM base b
                LEFT JOIN highs   h ON h.code = b.code
                LEFT JOIN future  f ON f.code = b.code AND f.date = $1
                WHERE b.date = $1
                  AND b.close > 0
                  AND b.amount >= $2
                """,
                target_date, MIN_AMOUNT,
            )

            if not rows:
                return 0

            # ── 2. 탐지 실행 ────────────────────────────────────────
            all_events = []
            for row in rows:
                row_dict = dict(row)
                for ev in _detect_events(row_dict):
                    # 사후 수익률 계산
                    c0 = row_dict["close"]
                    c1 = row_dict.get("close_1d")
                    c3 = row_dict.get("close_3d")
                    c5 = row_dict.get("close_5d")
                    ev["result_1d"] = round((c1 / c0 - 1) * 100, 4) if c1 and c0 else None
                    ev["result_3d"] = round((c3 / c0 - 1) * 100, 4) if c3 and c0 else None
                    ev["result_5d"] = round((c5 / c0 - 1) * 100, 4) if c5 and c0 else None
                    ev["detected_at"] = datetime.combine(target_date,
                        datetime.min.time()).replace(tzinfo=timezone.utc)
                    all_events.append(ev)

            if not all_events:
                return 0

            # ── 3. 저장 ─────────────────────────────────────────────
            insert_rows = [
                (
                    ev["detected_at"],
                    ev["code"],
                    ev["event_type"],
                    ev.get("price"),
                    ev.get("change_rate"),
                    ev.get("volume"),
                    ev.get("volume_ratio"),
                    ev.get("amount"),
                    json.dumps(ev.get("signal_data", {})),
                    ev.get("signal_score"),
                    ev.get("risk_score", 0.3),
                    ev.get("result_1d"),
                    ev.get("result_3d"),
                    ev.get("result_5d"),
                )
                for ev in all_events
            ]
            result = await conn.executemany(
                """
                INSERT INTO feature_events
                    (detected_at, code, event_type, price, change_rate,
                     volume, volume_ratio, amount, signal_data,
                     signal_score, risk_score,
                     result_1d, result_3d, result_5d)
                SELECT $1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,$12,$13,$14
                WHERE NOT EXISTS (
                    SELECT 1 FROM feature_events
                    WHERE code       = $2
                      AND event_type = $3
                      AND detected_at >= DATE_TRUNC('day', $1)
                      AND detected_at <  DATE_TRUNC('day', $1) + INTERVAL '1 day'
                )
                """,
                insert_rows,
            )
            return len(all_events)


async def main(args):
    dsn = os.environ.get("POSTGRES_DSN", "postgresql://stockuser:stockpass@postgres:5432/feature_stock")
    dsn = dsn.replace("+asyncpg", "")
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=CONCURRENCY + 2)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT date FROM daily_bars WHERE date >= $1 ORDER BY date",
            args.start_date,
        )
    all_dates = [r["date"] for r in rows]
    logger.info(f"총 {len(all_dates)}개 거래일 처리 예정 ({all_dates[0]} ~ {all_dates[-1]})")

    # 현재 feature_events 수
    async with pool.acquire() as conn:
        existing = await conn.fetchval("SELECT COUNT(*) FROM feature_events")
    logger.info(f"현재 feature_events: {existing}건")

    sem = asyncio.Semaphore(CONCURRENCY)
    total_new = 0
    batch_count = 0

    for i in range(0, len(all_dates), BATCH_SIZE):
        batch = all_dates[i:i + BATCH_SIZE]
        tasks = [process_date(pool, d, sem) for d in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        batch_new = sum(r for r in results if isinstance(r, int))
        total_new += batch_new
        batch_count += 1
        if batch_count % 10 == 0:
            logger.info(f"진행: {i+len(batch)}/{len(all_dates)}일 처리, "
                        f"누적 신규 이벤트: {total_new}건")

    async with pool.acquire() as conn:
        final = await conn.fetchval("SELECT COUNT(*) FROM feature_events")

    logger.info(f"=== 백필 완료 ===")
    logger.info(f"처리 날짜: {len(all_dates)}일")
    logger.info(f"신규 이벤트: {total_new}건")
    logger.info(f"최종 feature_events: {final}건")
    await pool.close()


if __name__ == "__main__":
    from datetime import date as _date
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=_date.fromisoformat,
                        default=_date(2020, 1, 1),
                        help="백필 시작일 (기본: 2020-01-01)")
    asyncio.run(main(parser.parse_args()))
