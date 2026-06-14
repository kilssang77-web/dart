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

TTL: 36시간 (다음 장 마감 후 갱신 전까지 유효)
"""
import logging
from statistics import mean, median
from typing import Sequence

logger = logging.getLogger(__name__)

_TTL = 60 * 60 * 36  # 36시간
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
