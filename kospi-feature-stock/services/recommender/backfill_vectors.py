"""
pattern_vector 대량 백필.

최적화: 종목별로 일봉 전체 로드 → 이벤트 날짜별로 슬라이딩 윈도우 벡터 계산.
DB 쿼리 수: 이벤트 수(730K) → 종목 수(~3000) 수준으로 감소.
"""
import asyncio
import asyncpg
import logging
import os
import sys
sys.path.insert(0, '/app')

from pattern_vector import build_vector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [vec_backfill] %(levelname)s %(message)s",
)
logger = logging.getLogger("vec_backfill")

BATCH_CODES = int(os.environ.get("VEC_BATCH_CODES", "4"))
WINDOW = 60   # 벡터 생성에 필요한 이전 일봉 수


async def process_code(conn: asyncpg.Connection, code: str) -> int:
    """단일 종목의 모든 이벤트에 벡터 계산 후 업데이트."""
    # 이 종목의 이벤트 날짜 목록 (pattern_vector 없는 것만)
    event_rows = await conn.fetch(
        """
        SELECT id, DATE(detected_at) AS event_date
        FROM feature_events
        WHERE code = $1 AND pattern_vector IS NULL
        ORDER BY event_date
        """,
        code,
    )
    if not event_rows:
        return 0

    # 일봉 전체 로드 (종목 전체 기간)
    bar_rows = await conn.fetch(
        """
        SELECT date, open, high, low, close, volume, amount,
               COALESCE(foreign_net_buy, 0) AS foreign_net_buy,
               COALESCE(inst_net_buy, 0)    AS inst_net_buy
        FROM daily_bars
        WHERE code = $1
        ORDER BY date
        """,
        code,
    )
    if len(bar_rows) < WINDOW:
        return 0

    bars_list = [dict(r) for r in bar_rows]
    date_to_idx = {b["date"]: i for i, b in enumerate(bars_list)}

    updates = []
    for ev in event_rows:
        ed = ev["event_date"]
        idx = date_to_idx.get(ed)
        if idx is None or idx < WINDOW:
            continue
        window_bars = bars_list[idx - WINDOW + 1: idx + 1]
        vec = build_vector(window_bars)
        if vec is None:
            continue
        vec_str = "[" + ",".join(f"{v:.6f}" for v in vec.tolist()) + "]"
        updates.append((vec_str, ev["id"]))

    if updates:
        await conn.executemany(
            "UPDATE feature_events SET pattern_vector = $1::vector WHERE id = $2",
            updates,
        )
    return len(updates)


async def main():
    dsn = os.environ.get("POSTGRES_DSN", "postgresql://stockuser:StrongPass123!@postgres:5432/feature_stock")
    dsn = dsn.replace("+asyncpg", "")
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=BATCH_CODES + 2)

    # 이벤트가 있는 종목 목록
    async with pool.acquire() as conn:
        codes = [r["code"] for r in await conn.fetch(
            "SELECT DISTINCT code FROM feature_events WHERE pattern_vector IS NULL ORDER BY code"
        )]
    total_codes = len(codes)
    logger.info(f"벡터 계산 대상: {total_codes}개 종목")

    sem = asyncio.Semaphore(BATCH_CODES)
    total_updated = 0

    async def do_code(code):
        async with sem:
            async with pool.acquire() as conn:
                n = await process_code(conn, code)
            return n

    for i in range(0, len(codes), 50):
        batch = codes[i: i + 50]
        results = await asyncio.gather(*[do_code(c) for c in batch], return_exceptions=True)
        batch_n = sum(r for r in results if isinstance(r, int))
        total_updated += batch_n
        if (i // 50) % 20 == 0:
            logger.info(f"진행: {i+len(batch)}/{total_codes}종목  갱신: {total_updated}건")

    async with pool.acquire() as conn:
        final_count = await conn.fetchval(
            "SELECT COUNT(*) FROM feature_events WHERE pattern_vector IS NOT NULL"
        )
    logger.info(f"=== 완료 === 총 갱신: {total_updated}건  최종 벡터 보유: {final_count}건")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
