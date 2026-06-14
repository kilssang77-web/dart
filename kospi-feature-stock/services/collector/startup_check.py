"""
서비스 시작 시 Redis 통계 유효성 확인 및 DB에서 자동 복구.
daily_bar_worker, detector, recommender 시작 시 호출.
"""
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


async def ensure_redis_stats(db, redis) -> bool:
    """Redis 통계가 없거나 오래된 경우 DB에서 자동 복구.

    Returns:
        True if stats are valid or recovered, False if recovery failed.
    """
    try:
        last_refresh = await redis.get("stats:last_refresh")
        if last_refresh:
            # 마지막 갱신이 48시간 이내면 유효
            last_dt = datetime.fromisoformat(
                last_refresh.decode() if isinstance(last_refresh, bytes) else last_refresh
            )
            age_hours = (datetime.utcnow() - last_dt).total_seconds() / 3600
            if age_hours < 48:
                # 샘플 확인
                sample_count = len(await redis.keys("stats:*:avg_vol_20d"))
                if sample_count > 100:
                    logger.info(f"Redis 통계 유효: {sample_count}개 종목, {age_hours:.1f}시간 전 갱신")
                    return True

        logger.warning("Redis 통계 없음 또는 만료 → DB에서 긴급 복구 시작")
        return await _recover_from_db(db, redis)

    except Exception as e:
        logger.error(f"Redis 통계 확인 실패: {e}")
        return False


async def _recover_from_db(db, redis) -> bool:
    """redis_stats_snapshot 테이블에서 Redis 복구."""
    try:
        # V10 마이그레이션 테이블에서 복구
        rows = await db.fetch("""
            SELECT code, stat_key, stat_value
            FROM redis_stats_snapshot
            WHERE computed_at >= NOW() - INTERVAL '3 days'
        """)

        if rows:
            pipe = redis.pipeline()
            ttl = 60 * 60 * 72
            for row in rows:
                pipe.set(f"stats:{row['code']}:{row['stat_key']}", row['stat_value'], ex=ttl)
            pipe.set("stats:last_refresh", datetime.utcnow().isoformat(), ex=ttl)
            await pipe.execute()
            logger.info(f"redis_stats_snapshot에서 복구 완료: {len(rows)}개 키")
            return True

        # 스냅샷도 없으면 daily_bars에서 직접 계산 (제한적)
        logger.warning("redis_stats_snapshot 없음 → daily_bars에서 직접 계산 (상위 500 종목)")
        codes = [r['code'] for r in await db.fetch(
            "SELECT code FROM stocks WHERE is_active ORDER BY code LIMIT 500"
        )]
        if codes:
            from redis_stats import refresh_all_stats
            refreshed = await refresh_all_stats(db, redis, codes)
            logger.info(f"DB 직접 계산으로 복구: {refreshed}개 종목")
            return refreshed > 0

        return False

    except Exception as e:
        logger.error(f"Redis 통계 복구 실패: {e}")
        return False
