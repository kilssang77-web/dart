"""
추천 종목 성과 추적 워커
- 1시간마다 미완료 추천의 가격 업데이트
- tick_data / daily_bars / Redis quote 에서 가격 조회
"""
import asyncio
import logging
import orjson
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("perf_tracker")

_KST  = timezone(timedelta(hours=9))
# 추적 기준: 신호 발생 후 영업일 기준 일수
_DAY_COLS = [("r_1d","t_1d",1),("r_2d","t_2d",2),("r_3d","t_3d",3),
             ("r_4d","t_4d",4),("r_5d","t_5d",5),
             ("r_7d","t_7d",7),("r_10d","t_10d",10)]


def _pct(current: float, entry: float) -> float:
    return round((current - entry) / entry * 100, 3) if entry else 0.0


async def _get_price_at(db, redis, code: str, ts: datetime) -> float | None:
    """ts 시각 가장 가까운 가격 조회 — tick_data → daily_bars 순"""
    try:
        # 1) Redis 현재가 (실시간 근접)
        now = datetime.now(_KST)
        if abs((ts - now).total_seconds()) < 3600:
            raw = await redis.get(f"quote:{code}")
            if raw:
                return float(orjson.loads(raw).get("price", 0)) or None

        # 2) tick_data (분봉 이내)
        row = await db.fetchrow(
            """SELECT price FROM tick_data
               WHERE code=$1 AND time <= $2
               ORDER BY time DESC LIMIT 1""",
            code, ts,
        )
        if row:
            return float(row["price"])

        # 3) daily_bars
        row = await db.fetchrow(
            """SELECT close FROM daily_bars
               WHERE code=$1 AND date <= $2::DATE
               ORDER BY date DESC LIMIT 1""",
            code, ts.date(),
        )
        if row:
            return float(row["close"])
    except Exception as e:
        logger.debug(f"price lookup error {code}: {e}")
    return None


async def _add_trading_days(db, code: str, base: datetime, n: int) -> datetime:
    """base 이후 n 영업일 시각 반환 (daily_bars 기준)"""
    try:
        row = await db.fetchrow(
            """SELECT date FROM daily_bars
               WHERE code=$1 AND date > $2::DATE
               ORDER BY date ASC
               LIMIT 1
               OFFSET $3""",
            code, base.date(), n - 1,
        )
        if row:
            d = row["date"]
            return datetime(d.year, d.month, d.day, 15, 30, tzinfo=_KST)
    except Exception as e:
        logger.debug(f"trading days error: {e}")
    return base + timedelta(days=int(n * 1.4))


async def run_once(db, redis) -> int:
    """미완료 추적 1회 처리 — 업데이트된 건수 반환"""
    rows = await db.fetch(
        """SELECT rp.id, rp.rec_id, rp.code, rp.entry_price,
                  rp.event_type, rp.signal_time,
                  rp.t_1h, rp.t_3h, rp.t_5h,
                  rp.t_1d, rp.t_2d, rp.t_3d, rp.t_4d,
                  rp.t_5d, rp.t_7d, rp.t_10d,
                  rp.hit_target, rp.hit_stop,
                  r.target_price, r.stop_loss_price
           FROM recommendation_performance rp
           JOIN recommendations r ON r.id = rp.rec_id
           WHERE rp.tracking_complete = FALSE
           LIMIT 200"""
    )
    updated = 0
    now = datetime.now(_KST)

    for row in rows:
        pid        = row["id"]
        code       = row["code"]
        entry      = float(row["entry_price"])
        signal_t   = row["signal_time"]
        target_p   = float(row["target_price"])
        stop_p     = float(row["stop_loss_price"])
        updates: dict = {}

        # ── 시간 기반 (1h, 3h, 5h)
        for col_r, col_t, hrs in [("r_1h","t_1h",1),("r_3h","t_3h",3),("r_5h","t_5h",5)]:
            if row[col_t] is None:
                ts = signal_t + timedelta(hours=hrs)
                if ts <= now:
                    p = await _get_price_at(db, redis, code, ts)
                    if p:
                        updates[col_r] = _pct(p, entry)
                        updates[col_t] = ts
                        if p >= target_p: updates["hit_target"] = True
                        if p <= stop_p:   updates["hit_stop"]   = True

        # ── 일 기반
        for col_r, col_t, days in _DAY_COLS:
            if row[col_t] is None:
                ts = await _add_trading_days(db, code, signal_t, days)
                if ts <= now:
                    p = await _get_price_at(db, redis, code, ts)
                    if p:
                        updates[col_r] = _pct(p, entry)
                        updates[col_t] = ts
                        if p >= target_p: updates["hit_target"] = True
                        if p <= stop_p:   updates["hit_stop"]   = True

        # ── 완료 판정 (10일치 모두 기록)
        all_day_cols = [c for _, c, _ in _DAY_COLS]
        current_t10 = updates.get("t_10d") or row["t_10d"]
        if current_t10:
            updates["tracking_complete"] = True
            # is_success: 1d~5d 중 목표가 달성 또는 평균 양수
            returns = [updates.get(c) or row[c] for c, _, _ in
                       [("r_1d","t_1d",1),("r_2d","t_2d",2),("r_3d","t_3d",3),
                        ("r_4d","t_4d",4),("r_5d","t_5d",5)]]
            valid = [r for r in returns if r is not None]
            updates["is_success"] = (
                bool(updates.get("hit_target") or row["hit_target"]) or
                (bool(valid) and sum(valid) / len(valid) > 0)
            )
            non_none = [r for r in [
                updates.get("r_1h") or row["r_1h"],
                updates.get("r_3h") or row["r_3h"],
                updates.get("r_5h") or row["r_5h"],
            ] + valid if r is not None]
            if non_none:
                updates["max_return"] = max(non_none)

        if updates:
            set_clause = ", ".join(f"{k}=${i+2}" for i, k in enumerate(updates.keys()))
            vals = [pid] + list(updates.values())
            await db.execute(
                f"UPDATE recommendation_performance SET {set_clause}, last_updated=NOW() WHERE id=$1",
                *vals
            )
            updated += 1

    return updated


async def tracker_loop(db, redis) -> None:
    """API lifespan 에서 asyncio.create_task 로 실행"""
    while True:
        try:
            n = await run_once(db, redis)
            if n:
                logger.info(f"[perf_tracker] updated {n} records")
        except Exception as e:
            logger.error(f"[perf_tracker] error: {e}")
        await asyncio.sleep(3600)  # 1시간마다
