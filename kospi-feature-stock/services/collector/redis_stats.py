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
"""
import logging
from datetime import datetime
from statistics import mean
from typing import Sequence

logger = logging.getLogger(__name__)

_TTL = 60 * 60 * 72  # 72시간 (주말 포함)
_BATCH = 50           # 동시 처리 배치 크기


async def refresh_all_stats(db, redis, codes: Sequence[str]) -> int:
    """전체 종목의 Redis 통계를 갱신하고 갱신된 종목 수를 반환."""
    total = 0
    errors = 0

    for i in range(0, len(codes), _BATCH):
        batch = codes[i:i + _BATCH]
        for code in batch:
            try:
                ok = await _refresh_one(db, redis, code)
                if ok:
                    total += 1
            except Exception as e:
                errors += 1
                logger.debug(f"stats 갱신 실패 {code}: {e}")

        if i % 500 == 0 and i > 0:
            logger.info(f"Redis 통계 갱신 진행: {i}/{len(codes)} ({errors}개 오류)")

    logger.info(f"Redis 통계 갱신 완료: {total}/{len(codes)}개 성공, {errors}개 오류")

    # 갱신 완료 마커 저장
    await redis.set("stats:last_refresh", datetime.utcnow().isoformat(), ex=_TTL)
    # admin 엔드포인트가 SCAN 없이 즉시 조회할 수 있도록 종목 수 저장
    await redis.set("stats:refresh_count", total, ex=_TTL)

    # 갱신된 데이터를 DB에 일괄 백업 (redis_stats_snapshot 테이블)
    try:
        await _backup_stats_to_db(db, redis, codes)
    except Exception as e:
        logger.warning(f"DB 백업 실패 (비필수): {e}")

    return total


async def _refresh_one(db, redis, code: str) -> bool:
    """단일 종목의 통계를 계산하여 Redis에 저장. 성공 시 True 반환."""
    rows = await db.fetch(
        """
        SELECT close, volume, amount, high, low
        FROM daily_bars
        WHERE code = $1
        ORDER BY date DESC
        LIMIT 260
        """,
        code,
    )
    if len(rows) < 5:
        return False

    closes  = [r["close"]  for r in rows]
    vols    = [r["volume"] for r in rows]
    amts    = [r["amount"] for r in rows]
    highs   = [r["high"]   for r in rows]
    lows    = [r["low"]    for r in rows]

    # 20일 평균
    avg_vol_20 = mean(vols[:20]) if len(vols) >= 20 else mean(vols)
    avg_amt_20 = mean(amts[:20]) if len(amts) >= 20 else mean(amts)

    # 신고가 (최근 N일)
    high_20d = max(highs[:20])  if len(highs) >= 20  else max(highs)
    high_13w = max(highs[:65])  if len(highs) >= 65  else max(highs)
    high_26w = max(highs[:130]) if len(highs) >= 130 else max(highs)
    high_52w = max(highs[:260]) if len(highs) >= 260 else max(highs)

    # ATR(14) — True Range 기반
    tr_list = []
    for j in range(min(14, len(rows) - 1)):
        tr = max(
            highs[j] - lows[j],
            abs(highs[j] - closes[j + 1]),
            abs(lows[j]  - closes[j + 1]),
        )
        tr_list.append(tr)
    atr14 = mean(tr_list) if tr_list else (highs[0] - lows[0])

    pipe = redis.pipeline()
    pipe.set(f"stats:{code}:avg_vol_20d", int(avg_vol_20),  ex=_TTL)
    pipe.set(f"stats:{code}:avg_amt_20d", int(avg_amt_20),  ex=_TTL)
    pipe.set(f"stats:{code}:high_20d",    int(high_20d),    ex=_TTL)
    pipe.set(f"stats:{code}:high_13w",    int(high_13w),    ex=_TTL)
    pipe.set(f"stats:{code}:high_26w",    int(high_26w),    ex=_TTL)
    pipe.set(f"stats:{code}:high_52w",    int(high_52w),    ex=_TTL)
    pipe.set(f"stats:{code}:atr14",       round(atr14, 2),  ex=_TTL)
    await pipe.execute()
    return True


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


async def _backup_stats_to_db(db, redis, codes: Sequence[str]) -> None:
    """갱신된 Redis 통계를 DB에 백업 (redis_stats_snapshot 테이블)."""
    stat_keys = ["avg_vol_20d", "avg_amt_20d", "high_20d", "high_13w", "high_26w", "high_52w", "atr14"]
    records = []

    for code in codes:
        for key in stat_keys:
            val = await redis.get(f"stats:{code}:{key}")
            if val is not None:
                records.append((code, key, float(val)))

    if not records:
        return

    # 배치 upsert
    await db.executemany("""
        INSERT INTO redis_stats_snapshot (code, stat_key, stat_value, computed_at)
        VALUES ($1, $2, $3, NOW())
        ON CONFLICT (code, stat_key) DO UPDATE SET
            stat_value = EXCLUDED.stat_value,
            computed_at = NOW()
    """, records)
    logger.info(f"DB 백업 완료: {len(records)}개 레코드")
