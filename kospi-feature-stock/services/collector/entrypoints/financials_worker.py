"""
독립 서비스: 전체 종목 분기별 재무 데이터 수집.
주기: 매주 1회 (일요일 02:00 KST), 또는 마지막 수집 후 6일 이상 경과 시 즉시 실행.
수집 항목: 재무비율(EPS/BPS/PER/PBR/ROE/부채비율) + 손익계산서(매출/영업이익/순이익)
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import StockCollector, load_all_stocks
from db.writer import write_financials

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("collector-financials")

_KST = timezone(timedelta(hours=9))
_REDIS_KEY_LAST_RUN = "financials:last_run"
_REDIS_KEY_SKIP     = "financials:skip:{code}"   # KIS 조회 불가 종목 24h 스킵
_RUN_INTERVAL_DAYS  = 6
_REQ_DELAY          = 1.0   # 초 / 종목 (2회 API 호출 포함, KIS 초당 20회 제한 준수)
_BATCH_LOG_EVERY    = 100


async def _collect_one(svc: StockCollector, code: str) -> list[dict]:
    """단일 종목 재무비율 + 손익계산서 조회 후 분기 키로 병합."""
    ratio_rows  = await svc.rest.get_financial_ratio(code)
    income_rows = await svc.rest.get_income_statement(code)

    # (year, quarter) 키로 인덱스 구성
    merged: dict[tuple, dict] = {}
    for r in ratio_rows:
        key = (r["year"], r["quarter"])
        merged[key] = r.copy()
    for r in income_rows:
        key = (r["year"], r["quarter"])
        if key in merged:
            merged[key].update({k: v for k, v in r.items() if v is not None})
        else:
            merged[key] = r.copy()

    return list(merged.values())


async def _should_run(redis) -> bool:
    """마지막 실행 후 6일 이상 지났으면 True."""
    last_raw = await redis.get(_REDIS_KEY_LAST_RUN)
    if not last_raw:
        return True
    try:
        last_dt = datetime.fromisoformat(last_raw.decode() if isinstance(last_raw, bytes) else last_raw)
        return (datetime.utcnow() - last_dt).days >= _RUN_INTERVAL_DAYS
    except Exception:
        return True


async def run_collection(svc: StockCollector, codes: list[str]) -> None:
    logger.info(f"[financials] 수집 시작 — {len(codes)}개 종목")
    total_records = 0
    skip_count    = 0
    error_count   = 0

    for i, code in enumerate(codes):
        # KIS 조회 불가 종목 스킵 (이전 수집에서 0행 반환된 종목, 24h TTL)
        if await svc.redis.exists(_REDIS_KEY_SKIP.format(code=code)):
            skip_count += 1
            continue

        try:
            records = await _collect_one(svc, code)
            if records:
                n = await write_financials(svc.db, records)
                total_records += n
            else:
                # 연속 0행 → 24h 스킵 마킹 (비상장/ETF/조회불가 종목)
                await svc.redis.set(_REDIS_KEY_SKIP.format(code=code), "1", ex=86400)
                skip_count += 1
        except Exception as e:
            logger.warning(f"[financials] {code} 오류: {e}")
            error_count += 1

        await asyncio.sleep(_REQ_DELAY)

        if (i + 1) % _BATCH_LOG_EVERY == 0:
            logger.info(
                f"[financials] 진행 {i+1}/{len(codes)} "
                f"— 적재 {total_records}건 / 스킵 {skip_count} / 오류 {error_count}"
            )

    # 완료 마킹
    await svc.redis.set(_REDIS_KEY_LAST_RUN, datetime.utcnow().isoformat(), ex=86400 * 8)
    logger.info(
        f"[financials] 완료 — 총 {total_records}건 적재 "
        f"/ {skip_count}개 스킵 / {error_count}개 오류"
    )


async def run():
    svc = StockCollector()
    await svc.setup()
    codes = await load_all_stocks(svc.db)
    logger.info(f"[financials] 활성 종목 {len(codes)}개 로드 완료")

    while True:
        now_kst = datetime.now(_KST)

        if await _should_run(svc.redis):
            # 주중에는 장외 시간(22:00~06:00 KST)에만 실행 — API 부하 분산
            if now_kst.weekday() < 5 and 6 <= now_kst.hour < 22:
                logger.info(
                    f"[financials] 장중 시간대 ({now_kst.strftime('%H:%M')}) — "
                    "장외 시간(22:00~)까지 대기"
                )
                await asyncio.sleep(3600)
                continue

            await run_collection(svc, codes)
            # 수집 완료 후 종목 리스트 갱신 (신규 상장 반영)
            codes = await load_all_stocks(svc.db)
        else:
            next_check_h = 6
            logger.info(
                f"[financials] 대기 중 (마지막 수집 후 {_RUN_INTERVAL_DAYS}일 미경과) "
                f"— {next_check_h}시간 후 재확인"
            )
            await asyncio.sleep(next_check_h * 3600)


if __name__ == "__main__":
    asyncio.run(run())
