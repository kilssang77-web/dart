"""
GitHub Actions 배치 전용: 일봉 수집 + Redis 통계 갱신 + 배치 탐지 (1회 실행 후 종료).

최적화:
  - 오늘 이미 수집된 종목 스킵 (재실행 시 속도 향상)
  - DAILY_CONCURRENT(기본 10) 종목 동시 수집 → 순차 대비 10× 속도
    (2721종목 × 2.8s/call → 순차 127분 → 동시 ~13분)
  - KIS 레이트 리밋: 10종목 동시 × (1/2.8s) ≈ 3.6 TPS << 20 TPS 한도
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import StockCollector, load_all_stocks
from db.writer import write_daily_bars
from redis_stats import refresh_all_stats, refresh_market_returns
from batch_scanner import BatchScanner
from kafka.producer import RedisEventBus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("collector-daily")

_KST             = timezone(timedelta(hours=9))
BACKFILL_DAYS    = int(os.environ.get("DAILY_BACKFILL_DAYS", "5"))
DAILY_CONCURRENT = int(os.environ.get("DAILY_CONCURRENT", "10"))
LOG_EVERY        = 200


async def _collect_one(
    svc: StockCollector,
    code: str,
    start: str,
    today: str,
    sem: asyncio.Semaphore,
    counters: dict,
) -> None:
    async with sem:
        try:
            bars = await svc.rest.get_daily_bars(code, start, today)
            if not bars and hasattr(svc, "_pykrx"):
                bars = await svc._pykrx.get_daily_bars(code, BACKFILL_DAYS + 3)
                if bars:
                    counters["pykrx"] += 1
            if bars:
                n = await write_daily_bars(svc.db, bars)
                counters["total"] += n
        except Exception as e:
            logger.error(f"[daily] {code}: {e}")
        finally:
            counters["done"] += 1
            if counters["done"] % LOG_EVERY == 0:
                logger.info(
                    f"[daily] 진행: {counters['done']}/{counters['target']} 완료,"
                    f" {counters['total']:,}행 저장"
                )


async def run():
    svc = StockCollector()
    await svc.setup()

    all_codes = await load_all_stocks(svc.db)
    if not all_codes:
        logger.warning("[daily] stocks table empty — skip")
        return

    logger.info(f"[daily] {len(all_codes)}개 종목 로드 완료")

    now_kst = datetime.now(_KST)
    today   = now_kst.strftime("%Y%m%d")
    start   = (now_kst - timedelta(days=BACKFILL_DAYS + 3)).strftime("%Y%m%d")

    # 오늘 이미 일봉이 있는 종목 제외
    try:
        rows = await svc.db.fetch(
            "SELECT DISTINCT code FROM daily_bars WHERE date = $1::date AND code = ANY($2::varchar[])",
            now_kst.date(), all_codes,
        )
        existing = {r["code"] for r in rows}
        logger.info(f"[daily] 오늘 이미 수집된 종목: {len(existing)}개 → 스킵")
    except Exception as e:
        logger.warning(f"[daily] 기존 데이터 확인 실패: {e}")
        existing = set()

    to_collect = [c for c in all_codes if c not in existing]
    logger.info(f"[daily] 수집 대상: {len(to_collect)}개 (동시={DAILY_CONCURRENT})")

    # ── 일봉 동시 수집 ────────────────────────────────────────
    sem      = asyncio.Semaphore(DAILY_CONCURRENT)
    counters = {"total": 0, "pykrx": 0, "done": 0, "target": len(to_collect)}

    await asyncio.gather(*[
        _collect_one(svc, code, start, today, sem, counters)
        for code in to_collect
    ])

    total        = counters["total"]
    pykrx_fallback = counters["pykrx"]

    # 지수 일봉 (KOSPI=0001, KOSDAQ=1001)
    for mkt_code in ["0001", "1001"]:
        try:
            idx_bars = await svc.rest.get_index_bars(mkt_code, start, today)
            if idx_bars:
                n = await write_daily_bars(svc.db, idx_bars)
                logger.info(f"[daily] 지수 {mkt_code}: {n}행")
        except Exception as e:
            logger.error(f"[daily] 지수 {mkt_code}: {e}")

    logger.info(
        f"[daily] 일봉 수집 완료 — {total:,}행 ({len(to_collect)}개 종목"
        + (f", pykrx fallback {pykrx_fallback}개" if pykrx_fallback else "") + ")"
    )

    # ── Redis 탐지 통계 갱신 ──────────────────────────────────
    logger.info("[daily] Redis 통계 갱신 시작")
    try:
        refreshed = await refresh_all_stats(svc.db, svc.redis, all_codes)
        logger.info(f"[daily] Redis 통계 갱신 완료: {refreshed}/{len(all_codes)}개")
    except Exception as e:
        logger.error(f"[daily] Redis 통계 갱신 실패: {e}")

    try:
        await refresh_market_returns(svc.db, svc.redis)
    except Exception as e:
        logger.error(f"[daily] KOSPI 수익률 갱신 실패: {e}")

    # ── 배치 탐지 ─────────────────────────────────────────────
    logger.info("[daily] 배치 탐지 시작")
    try:
        kafka  = RedisEventBus(svc.redis)
        scanner = BatchScanner(svc.db, svc.redis, kafka)
        events = await scanner.run(all_codes)
        logger.info(f"[daily] 배치 탐지 완료: {len(events)}개 신호")
    except Exception as e:
        logger.error(f"[daily] 배치 탐지 실패: {e}")

    # ── result_5d 백필 (7일+ 경과 이벤트 → 유사사례 검색에 필요) ──
    logger.info("[daily] result_5d 백필 시작")
    try:
        n_filled = await svc._backfill_result_5d()
        logger.info(f"[daily] result_5d 백필 완료: {n_filled}건")
    except Exception as e:
        logger.error(f"[daily] result_5d 백필 실패: {e}")

    # ── admin 카운터 캐시 갱신 (72h TTL) ──────────────────────
    try:
        _TTL = 60 * 60 * 72
        vc = await svc.db.fetchval(
            "SELECT COUNT(*) FROM feature_events WHERE pattern_vector IS NOT NULL"
        )
        rc = await svc.db.fetchval(
            "SELECT COUNT(*) FROM feature_events WHERE result_5d IS NOT NULL"
        )
        await svc.redis.set("stats:vector_count", int(vc or 0), ex=_TTL)
        await svc.redis.set("stats:result_count",  int(rc or 0), ex=_TTL)
        logger.info(f"[daily] 카운터 캐시 갱신: vector={vc}, result={rc}")
    except Exception as e:
        logger.error(f"[daily] 카운터 캐시 갱신 실패: {e}")

    # ── 완료 신호 ──────────────────────────────────────────────
    await svc.redis.set(f"daily_bars:ready:{today}", "1", ex=86400)
    logger.info(f"[daily] 완료 → daily_bars:ready:{today} 설정")


if __name__ == "__main__":
    asyncio.run(run())
