"""
독립 서비스: 최근 1년(365일) 일봉이 250개 미만인 종목 지능형 재백필.
주기: 매일 장외 시간(22:00~06:00 KST) 1회. 이미 충분한 데이터가 있으면 스킵.
목표: 모든 활성 종목이 최소 1년치(250봉) 일봉을 보유하도록 보장.
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import StockCollector, load_all_stocks
from db.writer import write_daily_bars

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("collector-bars-backfill")

_KST              = timezone(timedelta(hours=9))
_REDIS_KEY_LAST   = "bars_backfill:last_run"
_REDIS_KEY_SKIP   = "bars_backfill:skip:{code}"       # KIS 조회 불가 종목 7일 스킵
_REDIS_KEY_FAIL   = "bars_backfill:fail_count:{code}" # 연속 조회 불가 카운터 (30일 TTL)
_MIN_BARS_1Y      = 250      # 최근 365일 기준 최소 봉 수
_MAX_FAIL_COUNT   = 3        # N회 연속 0행 → stocks.is_active = FALSE
_BACKFILL_DAYS    = int(os.environ.get("BARS_BACKFILL_DAYS", "1825"))  # 5년 (기본)
_REQ_DELAY        = 0.5      # 초 / 종목
_BATCH_LOG_EVERY  = 200


async def _get_sparse_codes(db, all_codes: list[str]) -> list[str]:
    """최근 365일 일봉이 250개 미만인 활성 종목 코드 반환 (데이터 없는 종목 포함)."""
    rows = await db.fetch(
        """
        SELECT s.code
        FROM stocks s
        LEFT JOIN (
            SELECT code, COUNT(*) AS cnt
            FROM daily_bars
            WHERE date >= NOW() - INTERVAL '400 days'
            GROUP BY code
        ) b ON s.code = b.code
        WHERE s.is_active = TRUE
          AND s.code = ANY($1::varchar[])
          AND (b.cnt IS NULL OR b.cnt < $2)
        ORDER BY COALESCE(b.cnt, 0) ASC
        """,
        all_codes, _MIN_BARS_1Y,
    )
    return [r["code"] for r in rows]


def _date_chunks(start_str: str, end_str: str, chunk_days: int = 90):
    """YYYYMMDD 문자열을 받아 chunk_days 단위로 (s, e) 쌍 생성."""
    from datetime import date as _date
    s = _date(int(start_str[:4]), int(start_str[4:6]), int(start_str[6:8]))
    e = _date(int(end_str[:4]),   int(end_str[4:6]),   int(end_str[6:8]))
    cur = s
    while cur <= e:
        nxt = min(cur + timedelta(days=chunk_days - 1), e)
        yield cur.strftime("%Y%m%d"), nxt.strftime("%Y%m%d")
        cur = nxt + timedelta(days=1)


async def run_backfill(svc: StockCollector, all_codes: list[str]) -> None:
    sparse = await _get_sparse_codes(svc.db, all_codes)
    if not sparse:
        logger.info("[bars-backfill] 모든 종목이 충분한 데이터 보유 — 스킵")
        return

    logger.info(f"[bars-backfill] 재백필 대상: {len(sparse)}개 종목 (최근 1년 250봉 미만)")

    end   = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=_BACKFILL_DAYS)).strftime("%Y%m%d")
    total_added  = 0
    zero_count   = 0
    error_count  = 0

    for i, code in enumerate(sparse):
        # 이전에 KIS 조회 불가로 마킹된 종목 스킵
        if await svc.redis.exists(_REDIS_KEY_SKIP.format(code=code)):
            zero_count += 1
            continue

        try:
            # 90일 청크로 분할 요청 — KIS API 100봉 한계 우회
            code_added = 0
            for chunk_s, chunk_e in _date_chunks(start, end):
                bars = await svc.rest.get_daily_bars(code, chunk_s, chunk_e)
                if bars:
                    code_added += await write_daily_bars(svc.db, bars)
                await asyncio.sleep(_REQ_DELAY)
            if code_added > 0:
                total_added += code_added
                await svc.redis.delete(_REDIS_KEY_FAIL.format(code=code))
            else:
                # 모든 청크에서 0행 → 조회 불가
                await svc.redis.set(
                    _REDIS_KEY_SKIP.format(code=code), "1", ex=86400 * 7
                )
                fail_key = _REDIS_KEY_FAIL.format(code=code)
                _raw     = await svc.redis.get(fail_key)
                fail_cnt = (int(_raw.decode() if isinstance(_raw, bytes) else _raw) if _raw else 0) + 1
                await svc.redis.set(fail_key, fail_cnt, ex=86400 * 30)
                if fail_cnt >= _MAX_FAIL_COUNT:
                    await svc.db.execute(
                        "UPDATE stocks SET is_active = FALSE WHERE code = $1", code
                    )
                    await svc.redis.delete(fail_key)
                    logger.info(f"[bars-backfill] {code} is_active=FALSE (연속 {fail_cnt}회 0봉)")
                zero_count += 1
        except Exception as e:
            logger.warning(f"[bars-backfill] {code} 오류: {e}")
            error_count += 1

        if (i + 1) % _BATCH_LOG_EVERY == 0:
            logger.info(
                f"[bars-backfill] 진행 {i+1}/{len(sparse)} "
                f"— 추가 {total_added:,}봉 / 조회불가 {zero_count} / 오류 {error_count}"
            )

    await svc.redis.set(_REDIS_KEY_LAST, datetime.utcnow().isoformat(), ex=86400 * 2)
    logger.info(
        f"[bars-backfill] 완료 — {total_added:,}봉 추가 "
        f"/ {zero_count}개 조회불가 / {error_count}개 오류"
    )


async def run():
    svc = StockCollector()
    await svc.setup()
    all_codes = await load_all_stocks(svc.db)
    logger.info(f"[bars-backfill] 활성 종목 {len(all_codes)}개 로드 완료")

    while True:
        now_kst = datetime.now(_KST)
        hour    = now_kst.hour

        # 장외 시간(22:00~다음날 06:00)에만 실행 — 장중 KIS API 부하 방지
        is_offhours = (hour >= 22) or (hour < 6)

        if is_offhours:
            last_raw = await svc.redis.get(_REDIS_KEY_LAST)
            already_done_today = False
            if last_raw:
                try:
                    last_dt = datetime.fromisoformat(
                        last_raw.decode() if isinstance(last_raw, bytes) else last_raw
                    )
                    already_done_today = (datetime.utcnow() - last_dt).total_seconds() < 86400
                except Exception:
                    pass

            if not already_done_today:
                all_codes = await load_all_stocks(svc.db)  # 신규 상장 반영
                await run_backfill(svc, all_codes)
            else:
                logger.info("[bars-backfill] 오늘 이미 실행 완료 — 내일 장외 시간 대기")
        else:
            remaining_h = 22 - hour if hour < 22 else 24 - hour + 22
            logger.info(
                f"[bars-backfill] 장중 시간대 ({now_kst.strftime('%H:%M')}) "
                f"— 장외 시간까지 약 {remaining_h}시간 대기"
            )

        await asyncio.sleep(3600)  # 1시간마다 조건 재확인


if __name__ == "__main__":
    asyncio.run(run())
