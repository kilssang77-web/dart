"""
테마 확산 추적 API.
- /api/v1/themes/trending  : 최근 N시간 내 상위 테마 목록
- /api/v1/themes/{theme}   : 특정 테마 종목 + 시간별 탐지 추이
"""
from fastapi import APIRouter, Depends, Query
from deps import get_db, get_redis
import asyncpg
import redis.asyncio as redis_lib
import orjson
from datetime import datetime, timedelta, timezone

router = APIRouter()

_TRACKED_THEMES = [
    "2차전지", "반도체", "AI", "바이오", "방산", "친환경", "로봇", "원전",
]


@router.get("/trending")
async def get_trending_themes(
    hours: int = Query(default=24, ge=1, le=168),
    db: asyncpg.Pool = Depends(get_db),
):
    """최근 N시간 내 테마별 탐지 건수 + 평균 시그널 점수."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    rows = await db.fetch(
        """
        SELECT
            n.themes,
            fe.code,
            fe.signal_score,
            fe.detected_at
        FROM feature_events fe
        JOIN news_stock_links nsl ON nsl.code = fe.code
        JOIN news n ON n.id = nsl.news_id
        WHERE fe.detected_at >= $1
          AND n.themes IS NOT NULL
          AND n.themes != '[]'::jsonb
        ORDER BY fe.detected_at DESC
        LIMIT 2000
        """,
        since,
    )

    # 테마별 집계
    theme_stats: dict[str, dict] = {}
    for row in rows:
        themes = orjson.loads(row["themes"]) if isinstance(row["themes"], (str, bytes)) else (row["themes"] or [])
        for theme in themes:
            if theme not in theme_stats:
                theme_stats[theme] = {"count": 0, "scores": [], "codes": set()}
            theme_stats[theme]["count"] += 1
            theme_stats[theme]["scores"].append(float(row["signal_score"] or 0))
            theme_stats[theme]["codes"].add(row["code"])

    # 테마별 이벤트 수(DB에서 직접 집계) — 뉴스 연결 없는 경우도 포함
    event_rows = await db.fetch(
        """
        SELECT fe.code, s.sector, fe.signal_score, fe.detected_at
        FROM feature_events fe
        JOIN stocks s ON s.code = fe.code
        WHERE fe.detected_at >= $1
        ORDER BY fe.detected_at DESC
        LIMIT 5000
        """,
        since,
    )

    sector_stats: dict[str, dict] = {}
    for row in event_rows:
        sector = row["sector"] or "기타"
        if sector not in sector_stats:
            sector_stats[sector] = {"count": 0, "scores": [], "codes": set()}
        sector_stats[sector]["count"] += 1
        sector_stats[sector]["scores"].append(float(row["signal_score"] or 0))
        sector_stats[sector]["codes"].add(row["code"])

    result = []
    for theme, stat in sorted(theme_stats.items(), key=lambda x: -x[1]["count"]):
        scores = stat["scores"]
        result.append({
            "theme":        theme,
            "count":        stat["count"],
            "stock_count":  len(stat["codes"]),
            "avg_score":    round(sum(scores) / len(scores), 3) if scores else 0,
            "source":       "news",
        })

    for sector, stat in sorted(sector_stats.items(), key=lambda x: -x[1]["count"]):
        scores = stat["scores"]
        result.append({
            "theme":        sector,
            "count":        stat["count"],
            "stock_count":  len(stat["codes"]),
            "avg_score":    round(sum(scores) / len(scores), 3) if scores else 0,
            "source":       "sector",
        })

    return {
        "hours":   hours,
        "since":   since.isoformat(),
        "themes":  result[:20],
    }


@router.get("/{theme}")
async def get_theme_detail(
    theme: str,
    hours: int = Query(default=48, ge=1, le=336),
    db: asyncpg.Pool = Depends(get_db),
):
    """특정 테마의 종목 목록 + 시간별 탐지 건수 추이."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    # 뉴스 테마 기반 종목
    news_rows = await db.fetch(
        """
        SELECT DISTINCT
            fe.code,
            s.name,
            s.sector,
            MAX(fe.signal_score) AS max_score,
            COUNT(*) AS event_count,
            MAX(fe.detected_at) AS last_detected
        FROM feature_events fe
        JOIN stocks s ON s.code = fe.code
        JOIN news_stock_links nsl ON nsl.code = fe.code
        JOIN news n ON n.id = nsl.news_id
        WHERE fe.detected_at >= $1
          AND n.themes::text ILIKE $2
        GROUP BY fe.code, s.name, s.sector
        ORDER BY max_score DESC
        LIMIT 30
        """,
        since,
        f'%{theme}%',
    )

    # 시간별 추이 (6시간 단위)
    hourly_rows = await db.fetch(
        """
        SELECT
            date_trunc('hour', fe.detected_at) +
                INTERVAL '6 hours' * (EXTRACT(HOUR FROM fe.detected_at)::int / 6) AS bucket,
            COUNT(*) AS count
        FROM feature_events fe
        JOIN news_stock_links nsl ON nsl.code = fe.code
        JOIN news n ON n.id = nsl.news_id
        WHERE fe.detected_at >= $1
          AND n.themes::text ILIKE $2
        GROUP BY bucket
        ORDER BY bucket
        """,
        since,
        f'%{theme}%',
    )

    return {
        "theme":   theme,
        "hours":   hours,
        "stocks":  [dict(r) for r in news_rows],
        "hourly":  [{"bucket": str(r["bucket"]), "count": r["count"]} for r in hourly_rows],
    }
