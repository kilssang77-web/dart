"""
누락된 feature_events 복구 스크립트
detector 로그에서 6/30~7/8 사이 신호를 추출 → feature_events DB에 삽입
"""
import asyncio
import asyncpg
import os
import re
import subprocess
import logging
from collections import defaultdict
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

DB_DSN = os.getenv("DATABASE_URL", "postgresql://fstock:fstock@postgres:5432/fstock")

SIGNAL_PAT = re.compile(
    r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \[detector\] INFO - \[SIGNAL\] (\w+) (\w+) score=([\d.]+)'
)


def parse_signals_from_docker():
    """docker logs에서 신호 추출 (7/1 이후 — 6/30은 마지막 정상 저장일)."""
    result = subprocess.run(
        ["docker", "logs", "fstock-detector", "--since", "2026-07-01T00:00:00"],
        capture_output=True, text=True
    )
    lines = result.stdout.splitlines() + result.stderr.splitlines()

    signals = []
    seen = set()
    for line in lines:
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
    for d in sorted(by_date):
        logger.info(f"  {d}: {by_date[d]}건")
    for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
        logger.info(f"  {t}: {c}건")
    return signals


async def get_daily_bar(conn, code: str, date: str):
    """해당 날짜 또는 가장 가까운 이전 일봉 조회."""
    row = await conn.fetchrow(
        """SELECT close, volume, amount, change_rate
           FROM daily_bars
           WHERE code=$1 AND date <= $2::date
           ORDER BY date DESC LIMIT 1""",
        code, date
    )
    return row


async def recover(signals: list):
    pool = await asyncpg.create_pool(DB_DSN, min_size=5, max_size=10)
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
                # 이미 존재하면 skip
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

                bar = await get_daily_bar(conn, code, date_str)
                price = int(bar["close"]) if bar else 0
                volume = int(bar["volume"]) if bar else None
                amount = int(bar["amount"]) if bar else None
                change_rate = float(bar["change_rate"]) if bar and bar["change_rate"] else 0.0
                risk_score = max(0.1, 1.0 - sig["signal_score"])

                event_id = await conn.fetchval(
                    """INSERT INTO feature_events (
                           code, detected_at, event_type, price, change_rate,
                           volume, volume_ratio, amount, signal_score, risk_score
                       ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                       RETURNING id""",
                    code, detected_at, event_type, price, change_rate,
                    volume, None, amount, sig["signal_score"], risk_score
                )
                inserted += 1
                if inserted % 100 == 0:
                    logger.info(f"  진행: inserted={inserted}, skipped={skipped}, failed={failed}")
        except Exception as e:
            failed += 1
            if failed <= 5:
                logger.warning(f"  실패 {code} {event_type}: {e}")

    # 배치 처리 (동시 10개)
    batch_size = 10
    for i in range(0, len(signals), batch_size):
        batch = signals[i:i + batch_size]
        await asyncio.gather(*[process(s) for s in batch])

    await pool.close()
    logger.info(f"\n완료: inserted={inserted}, skipped={skipped}, failed={failed}")
    return inserted, skipped, failed


async def main():
    logger.info("=== feature_events 복구 시작 ===")
    signals = parse_signals_from_docker()
    if not signals:
        logger.warning("복구할 신호 없음")
        return
    await recover(signals)
    logger.info("=== 복구 완료 ===")


if __name__ == "__main__":
    asyncio.run(main())
