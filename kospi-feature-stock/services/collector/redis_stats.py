"""
Redis 탐지 통계 초기화/갱신 모듈.

탐지 규칙(volume_surge, breakout, supply_anomaly 등)이 Redis 통계에 의존함.
daily_bars가 수집된 후 이 함수를 호출하여 모든 탐지 규칙이 정상 동작하도록 보장.

저장 키:
    stats:{code}:avg_vol_20d   — 20일 평균 거래량
    stats:{code}:avg_amt_20d   — 20일 평균 거래대금
    stats:{code}:high_52w      — 52주 최고가 (260 영업일)
    stats:{code}:high_26w      — 26주 최고가 (130 영업일)
    stats:{code}:high_13w      — 13주 최고가 (65 영업일)
    stats:{code}:high_20d      — 20일 최고가
    stats:{code}:atr14         — ATR(14) — 평균진폭

TTL: 72시간 (주말 포함 — 금요일 갱신 후 월요일 장 전까지 유효)

최적화 (2026-07-21):
    이전: 종목당 개별 DB 쿼리 (2,600회) + 개별 Redis 파이프라인 (2,600회)
          + _backup_stats_to_db에서 순차 Redis GET (18,200회) → 총 20분+
    현재: 단일 배치 DB 쿼리 1회 + 단일 Redis 파이프라인 1회
          + computed 값 직접 전달로 Redis 재조회 0회 → 총 수십 초
"""
import logging
from collections import defaultdict
from datetime import datetime
from statistics import mean
from typing import Sequence

logger = logging.getLogger(__name__)

_TTL = 60 * 60 * 72  # 72시간 (주말 포함)


def _compute_stats(rows: list) -> dict | None:
    """종목 row 리스트(최신→과거 순)에서 통계를 계산. 데이터 부족 시 None."""
    if len(rows) < 5:
        return None

    closes = [r["close"]  for r in rows]
    vols   = [r["volume"] for r in rows]
    amts   = [r["amount"] for r in rows]
    highs  = [r["high"]   for r in rows]
    lows   = [r["low"]    for r in rows]

    avg_vol_20 = mean(vols[:20]) if len(vols) >= 20 else mean(vols)
    avg_amt_20 = mean(amts[:20]) if len(amts) >= 20 else mean(amts)
    high_20d   = max(highs[:20])  if len(highs) >= 20  else max(highs)
    high_13w   = max(highs[:65])  if len(highs) >= 65  else max(highs)
    high_26w   = max(highs[:130]) if len(highs) >= 130 else max(highs)
    high_52w   = max(highs[:260]) if len(highs) >= 260 else max(highs)

    tr_list = []
    for j in range(min(14, len(rows) - 1)):
        tr = max(
            highs[j] - lows[j],
            abs(highs[j] - closes[j + 1]),
            abs(lows[j]  - closes[j + 1]),
        )
        tr_list.append(tr)
    atr14 = mean(tr_list) if tr_list else (highs[0] - lows[0])

    return {
        "avg_vol_20d": int(avg_vol_20),
        "avg_amt_20d": int(avg_amt_20),
        "high_20d":    int(high_20d),
        "high_13w":    int(high_13w),
        "high_26w":    int(high_26w),
        "high_52w":    int(high_52w),
        "atr14":       round(atr14, 2),
    }


async def refresh_all_stats(db, redis, codes: Sequence[str]) -> int:
    """전체 종목의 Redis 통계를 단일 배치 쿼리로 갱신하고 갱신된 종목 수를 반환.

    최적화: 개별 종목 쿼리 N회 대신 윈도우 함수 단일 쿼리로 전체 조회.
    """
    # 단일 배치 쿼리 — 종목당 최신 260행을 윈도우 함수로 한 번에 조회
    rows = await db.fetch(
        """
        SELECT code, close, volume, amount, high, low
        FROM (
            SELECT code, close, volume, amount, high, low,
                   ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) AS rn
            FROM daily_bars
            WHERE code = ANY($1::varchar[])
              AND close > 0
        ) sub
        WHERE rn <= 260
        ORDER BY code, rn
        """,
        list(codes),
    )

    # code별로 그룹핑 (이미 code, rn 순 정렬이므로 순서 보장)
    code_rows: dict[str, list] = defaultdict(list)
    for r in rows:
        code_rows[r["code"]].append(r)

    # 통계 계산 + 단일 Redis 파이프라인으로 일괄 SET
    pipe = redis.pipeline()
    computed: dict[str, dict] = {}

    for code, data in code_rows.items():
        stats = _compute_stats(data)
        if stats is None:
            continue
        computed[code] = stats
        pipe.set(f"stats:{code}:avg_vol_20d", stats["avg_vol_20d"], ex=_TTL)
        pipe.set(f"stats:{code}:avg_amt_20d", stats["avg_amt_20d"], ex=_TTL)
        pipe.set(f"stats:{code}:high_20d",    stats["high_20d"],    ex=_TTL)
        pipe.set(f"stats:{code}:high_13w",    stats["high_13w"],    ex=_TTL)
        pipe.set(f"stats:{code}:high_26w",    stats["high_26w"],    ex=_TTL)
        pipe.set(f"stats:{code}:high_52w",    stats["high_52w"],    ex=_TTL)
        pipe.set(f"stats:{code}:atr14",       stats["atr14"],       ex=_TTL)

    await pipe.execute()

    total = len(computed)
    errors = len(codes) - len(code_rows)
    logger.info(f"Redis 통계 갱신 완료: {total}/{len(codes)}개 성공, {errors}개 데이터 없음")

    await redis.set("stats:last_refresh", datetime.utcnow().isoformat(), ex=_TTL)
    await redis.set("stats:refresh_count", total, ex=_TTL)

    # 계산된 값을 직접 전달 — Redis 재조회 없음
    try:
        await _backup_stats_to_db(db, computed)
    except Exception as e:
        logger.warning(f"DB 백업 실패 (비필수): {e}")

    return total


async def refresh_market_returns(db, redis) -> None:
    """KOSPI 지수 수익률·변동성을 Redis에 저장 — ml_client의 per-event DB 쿼리 대체."""
    import numpy as np
    rows = await db.fetch(
        "SELECT close FROM daily_bars WHERE code='0001' ORDER BY date DESC LIMIT 25"
    )
    kc = [float(r["close"]) for r in rows if r.get("close")]
    if len(kc) < 2:
        return
    ret_1d  = (kc[0] / kc[1]  - 1) * 100 if kc[1]  else 0.0
    ret_3d  = (kc[0] / kc[3]  - 1) * 100 if len(kc) >  3 and kc[3]  else 0.0
    ret_5d  = (kc[0] / kc[5]  - 1) * 100 if len(kc) >  5 and kc[5]  else 0.0
    ret_10d = (kc[0] / kc[10] - 1) * 100 if len(kc) > 10 and kc[10] else 0.0
    ret_20d = (kc[0] / kc[20] - 1) * 100 if len(kc) > 20 and kc[20] else 0.0
    _ks5    = kc[:5]
    vol_5d  = float(np.std([(_ks5[j] / _ks5[j+1] - 1) * 100 for j in range(len(_ks5)-1)])) if len(_ks5) >= 2 else 0.0
    pipe = redis.pipeline()
    pipe.set("market:kospi_return_1d",  ret_1d,  ex=_TTL)
    pipe.set("market:kospi_return_3d",  ret_3d,  ex=_TTL)
    pipe.set("market:kospi_return_5d",  ret_5d,  ex=_TTL)
    pipe.set("market:kospi_return_10d", ret_10d, ex=_TTL)
    pipe.set("market:kospi_return_20d", ret_20d, ex=_TTL)
    pipe.set("market:kospi_vol_5d",     vol_5d,  ex=_TTL)
    await pipe.execute()
    logger.info(f"[redis_stats] KOSPI 갱신: 1d={ret_1d:.2f}% 5d={ret_5d:.2f}% vol5d={vol_5d:.2f}%")


async def _backup_stats_to_db(db, computed: dict[str, dict]) -> None:
    """계산된 통계를 DB에 백업 (redis_stats_snapshot 테이블).

    computed 값을 직접 받아 Redis 재조회를 완전히 제거.
    이전: codes × stat_keys = 18,200회 순차 Redis GET → 현재: 0회
    """
    stat_keys = ["avg_vol_20d", "avg_amt_20d", "high_20d", "high_13w", "high_26w", "high_52w", "atr14"]
    records = [
        (code, key, float(stats[key]))
        for code, stats in computed.items()
        for key in stat_keys
        if key in stats
    ]

    if not records:
        return

    await db.executemany(
        """
        INSERT INTO redis_stats_snapshot (code, stat_key, stat_value, computed_at)
        VALUES ($1, $2, $3, NOW())
        ON CONFLICT (code, stat_key) DO UPDATE SET
            stat_value  = EXCLUDED.stat_value,
            computed_at = NOW()
        """,
        records,
    )
    logger.info(f"DB 백업 완료: {len(records)}개 레코드")
