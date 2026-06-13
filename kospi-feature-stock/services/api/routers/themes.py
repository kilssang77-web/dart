"""
테마 확산 추적 API.
- /api/v1/themes/trending  : 최근 N시간 내 상위 테마 목록
- /api/v1/themes/{theme}   : 특정 테마 종목 + 시간별 탐지 추이
"""
import logging
from fastapi import APIRouter, Depends, Query
from deps import get_db, get_redis
import asyncpg
import redis.asyncio as redis_lib
import orjson
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

router = APIRouter()

_TRACKED_THEMES = [
    "2차전지", "반도체", "AI", "바이오", "방산", "친환경", "로봇", "원전",
]


@router.get("/trending")
async def get_trending_themes(
    hours: int = Query(default=72, ge=1, le=168),
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

    result: list[dict] = []
    seen: set[str] = set()

    for theme, stat in sorted(theme_stats.items(), key=lambda x: -x[1]["count"]):
        scores = stat["scores"]
        result.append({
            "theme":        theme,
            "count":        stat["count"],
            "stock_count":  len(stat["codes"]),
            "avg_score":    round(sum(scores) / len(scores), 3) if scores else 0,
            "source":       "news",
        })
        seen.add(theme)

    for sector, stat in sorted(sector_stats.items(), key=lambda x: -x[1]["count"]):
        if sector in seen:
            continue
        scores = stat["scores"]
        result.append({
            "theme":        sector,
            "count":        stat["count"],
            "stock_count":  len(stat["codes"]),
            "avg_score":    round(sum(scores) / len(scores), 3) if scores else 0,
            "source":       "sector",
        })
        seen.add(sector)

    result.sort(key=lambda x: -x["count"])
    return {
        "hours":   hours,
        "since":   since.isoformat(),
        "themes":  result[:20],
    }


@router.get("/clusters")
async def get_theme_clusters(
    redis: redis_lib.Redis = Depends(get_redis),
):
    """ThemeClusterer가 생성한 K-Means 동적 테마 클러스터 반환."""
    try:
        raw = await redis.get("themes:clusters")
        updated_at = await redis.get("themes:updated_at")
        if raw:
            return {
                "clusters":    orjson.loads(raw),
                "updated_at":  updated_at.decode() if updated_at else None,
            }
    except Exception as e:
        logger.warning(f"themes:clusters redis error: {e}")
    return {"clusters": [], "updated_at": None}


@router.get("/spread/daily")
async def get_spread_daily(
    theme: str = Query(description="테마 이름"),
    days:  int  = Query(default=14, ge=1, le=90),
    db: asyncpg.Pool = Depends(get_db),
):
    """일별 테마 확산 추이 (theme_snapshots 테이블 기반)."""
    rows = await db.fetch(
        """
        SELECT snap_date::TEXT, stock_count, avg_return, top_codes
        FROM theme_snapshots
        WHERE theme_name = $1
          AND snap_date >= CURRENT_DATE - ($2 * INTERVAL '1 day')
        ORDER BY snap_date
        """,
        theme, days,
    )
    if not rows:
        # 스냅쌏 데이터 없으면 리엝타임 집계로 대체
        since = datetime.now(timezone.utc) - timedelta(days=days)
        live  = await db.fetch(
            """
            SELECT
                (fe.detected_at AT TIME ZONE 'Asia/Seoul')::DATE::TEXT AS snap_date,
                COUNT(DISTINCT fe.code) AS stock_count,
                ROUND(AVG(fe.result_1d)::NUMERIC, 4) AS avg_return
            FROM feature_events fe
            JOIN stocks s ON s.code = fe.code
            JOIN news_stock_links nsl ON nsl.code = fe.code
            JOIN news n ON n.id = nsl.news_id
            WHERE fe.detected_at >= $1
              AND n.themes::text ILIKE $2
            GROUP BY snap_date
            ORDER BY snap_date
            """,
            since, f'%{theme}%',
        )
        return {"theme": theme, "days": days, "snapshots": [dict(r) for r in live], "source": "realtime"}

    result = []
    for r in rows:
        d = dict(r)
        if d.get("top_codes"):
            try:
                d["top_codes"] = d["top_codes"].split(",")
            except Exception:
                d["top_codes"] = []
        result.append(d)
    return {"theme": theme, "days": days, "snapshots": result, "source": "snapshots"}


@router.post("/spread/snapshot")
async def save_spread_snapshot(
    db: asyncpg.Pool = Depends(get_db),
):
    """테마별 일별 스냅쌏 저장 (직접 호출 또는 스케줄러 사용 가능)."""
    today = datetime.now(timezone(timedelta(hours=9))).date()
    saved = 0

    # feature_events + news 기반 테마 집계
    rows = await db.fetch(
        """
        SELECT
            theme_name,
            COUNT(DISTINCT fe.code) AS stock_count,
            ROUND(AVG(fe.result_1d)::NUMERIC, 4) AS avg_return,
            STRING_AGG(DISTINCT fe.code, ',' ORDER BY fe.code) AS top_codes
        FROM (
            SELECT fe.code, fe.result_1d,
                   jsonb_array_elements_text(n.themes::jsonb) AS theme_name
            FROM feature_events fe
            JOIN news_stock_links nsl ON nsl.code = fe.code
            JOIN news n ON n.id = nsl.news_id
            WHERE fe.detected_at::date = $1
              AND n.themes IS NOT NULL AND n.themes != '[]'
        ) sub
        GROUP BY theme_name
        HAVING COUNT(DISTINCT code) >= 2
        """,
        today,
    )
    for row in rows:
        try:
            await db.execute(
                """
                INSERT INTO theme_snapshots (theme_name, snap_date, stock_count, avg_return, top_codes)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (theme_name, snap_date) DO UPDATE
                  SET stock_count = EXCLUDED.stock_count,
                      avg_return  = EXCLUDED.avg_return,
                      top_codes   = EXCLUDED.top_codes
                """,
                row["theme_name"], today,
                int(row["stock_count"]), row["avg_return"], row["top_codes"],
            )
            saved += 1
        except Exception as e:
            logger.warning(f"[ThemeSnapshot] save error {row['theme_name']}: {e}")
    return {"saved": saved, "date": str(today)}


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
