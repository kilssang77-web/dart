"""
컨테이너 내부에서 실행: feature_events 복구
signals_raw.txt 파싱 → daily_bars에서 가격 조회 → feature_events 삽입
"""
import asyncio
import asyncpg
import os
import re
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

DB_DSN = os.getenv("POSTGRES_DSN", "postgresql://stockuser:StrongPass123!@postgres:5432/feature_stock").replace("+asyncpg", "")

SIGNAL_PAT = re.compile(
    r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \[detector\] INFO - \[SIGNAL\] (\w+) (\w+) score=([\d.]+)'
)


def parse_signals(filepath: str):
    signals = []
    seen = set()
    with open(filepath) as f:
        for line in f:
            m = SIGNAL_PAT.search(line)
            if not m:
                continue
            dt_str, code, event_type, score = m.groups()
            date = dt_str[:10]
            key = (code, event_type, date)
            if key in seen:
                continue
            seen.add(key)
            detected_at = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            signals.append({
                "code": code,
                "event_type": event_type,
                "detected_at": detected_at,
                "signal_score": float(score),
            })
    by_date = defaultdict(int)
    by_type = defaultdict(int)
    for s in signals:
        by_date[s["detected_at"].strftime("%Y-%m-%d")] += 1
        by_type[s["event_type"]] += 1
    logger.info(f"추출된 고유 신호: {len(signals)}건")
    for d in sorted(by_date): logger.info(f"  {d}: {by_date[d]}건")
    for t, c in sorted(by_type.items(), key=lambda x: -x[1]): logger.info(f"  {t}: {c}건")
    return signals


async def recover(signals: list):
    pool = await asyncpg.create_pool(DB_DSN, min_size=3, max_size=8)
    inserted = 0
    skipped = 0
    failed = 0

    async def process(sig: dict):
        nonlocal inserted, skipped, failed
        code = sig["code"]
        event_type = sig["event_type"]
        detected_at = sig["detected_at"]
        date_str = detected_at.strftime("%Y-%m-%d")

        try:
            async with pool.acquire() as conn:
                existing = await conn.fetchval(
                    """SELECT id FROM feature_events
                       WHERE code::text = $1
                         AND event_type::text = $2
                         AND detected_at >= DATE_TRUNC('day', $3::timestamptz)
                         AND detected_at <  DATE_TRUNC('day', $3::timestamptz) + INTERVAL '1 day'
                       LIMIT 1""",
                    code, event_type, detected_at
                )
                if existing:
                    skipped += 1
                    return

                bar = await conn.fetchrow(
                    """SELECT close, volume, amount, change_rate
                       FROM daily_bars
                       WHERE code=$1 AND date <= $2
                       ORDER BY date DESC LIMIT 1""",
                    code, detected_at.date()
                )
                price = int(bar["close"]) if bar else 0
                volume = int(bar["volume"]) if bar and bar["volume"] else None
                amount = int(bar["amount"]) if bar and bar["amount"] else None
                change_rate = float(bar["change_rate"]) if bar and bar["change_rate"] else 0.0
                risk_score = round(max(0.1, 1.0 - sig["signal_score"]), 3)

                await conn.execute(
                    """INSERT INTO feature_events (
                           code, detected_at, event_type, price, change_rate,
                           volume, volume_ratio, amount, signal_score, risk_score
                       ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
                    code, detected_at, event_type, price, change_rate,
                    volume, None, amount, sig["signal_score"], risk_score
                )
                inserted += 1
                if inserted % 50 == 0:
                    logger.info(f"  진행: inserted={inserted}, skipped={skipped}, failed={failed}")
        except Exception as e:
            failed += 1
            if failed <= 10:
                logger.warning(f"  실패 {code} {event_type}: {e}")

    batch_size = 20
    for i in range(0, len(signals), batch_size):
        batch = signals[i:i + batch_size]
        await asyncio.gather(*[process(s) for s in batch])

    await pool.close()
    logger.info(f"완료: inserted={inserted}, skipped={skipped}, failed={failed}")
    return inserted, skipped, failed


async def main():
    logger.info("=== feature_events 복구 시작 ===")
    signals_file = "/app/signals_raw.txt"
    if not os.path.exists(signals_file):
        logger.error(f"파일 없음: {signals_file}")
        return
    signals = parse_signals(signals_file)
    if not signals:
        logger.warning("복구할 신호 없음")
        return
    await recover(signals)

    # 결과 확인
    pool = await asyncpg.create_pool(DB_DSN, min_size=1, max_size=2)
    count = await pool.fetchval("SELECT COUNT(*) FROM feature_events WHERE detected_at >= '2026-07-01'")
    logger.info(f"7/1 이후 feature_events 총: {count}건")
    await pool.close()
    logger.info("=== 복구 완료 ===")


if __name__ == "__main__":
    asyncio.run(main())
