"""
테마 확산 추적 API.
- /api/v1/themes/trending  : 최근 N시간 내 상위 테마 목록
- /api/v1/themes/{theme}   : 특정 테마 종목 + 시간별 탐지 추이
"""
import logging
from fastapi import APIRouter, Depends, Query
from deps import get_db, get_redis, enrich_live_prices
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
    db:    asyncpg.Pool       = Depends(get_db),
    redis: redis_lib.Redis    = Depends(get_redis),
):
    """최근 N시간 내 테마별 탐지 건수 + 평균 시그널 점수."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    # 테마 뉴스 → 그 뉴스에 주요 등장한 종목(relevance>=0.6) → 해당 종목의 최고 신호 점수
    # relevance < 0.6: 본문 1회 언급(0.45) 또는 미등장(0.20) → 제외
    # relevance >= 0.6: 제목 포함(0.70+) 또는 본문 3회 이상(0.60) → 해당 테마 주요 종목으로 간주
    rows = await db.fetch(
        """
        SELECT
            n.themes,
            nsl.code,
            fe_agg.max_score AS signal_score,
            n.published_at   AS detected_at
        FROM news n
        JOIN news_stock_links nsl ON nsl.news_id = n.id
            AND nsl.relevance >= 0.6
        JOIN (
            SELECT code, MAX(signal_score) AS max_score
            FROM feature_events
            WHERE detected_at >= $1
            GROUP BY code
        ) fe_agg ON fe_agg.code = nsl.code
        WHERE n.published_at >= $1
          AND n.themes IS NOT NULL
          AND n.themes != '[]'::jsonb
        ORDER BY n.published_at DESC
        LIMIT 5000
        """,
        since,
    )

    # 테마별 집계
    theme_stats: dict[str, dict] = {}
    for row in rows:
        themes = orjson.loads(row["themes"]) if isinstance(row["themes"], (str, bytes)) else (row["themes"] or [])
        for theme in themes:
            if theme not in theme_stats:
                theme_stats[theme] = {"count": 0, "scores": [], "codes": {}}
            theme_stats[theme]["count"] += 1
            theme_stats[theme]["scores"].append(float(row["signal_score"] or 0))
            code = row["code"]
            theme_stats[theme]["codes"][code] = theme_stats[theme]["codes"].get(code, 0) + 1

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
            sector_stats[sector] = {"count": 0, "scores": [], "codes": {}}
        sector_stats[sector]["count"] += 1
        sector_stats[sector]["scores"].append(float(row["signal_score"] or 0))
        code = row["code"]
        sector_stats[sector]["codes"][code] = sector_stats[sector]["codes"].get(code, 0) + 1

    result: list[dict] = []
    seen: set[str] = set()

    # 이벤트 빈도 기준 상위 10개 코드 추출 (이름 조회용)
    def _top_codes(codes_freq: dict, n: int = 10) -> list[str]:
        return [c for c, _ in sorted(codes_freq.items(), key=lambda x: -x[1])[:n]]

    for theme, stat in sorted(theme_stats.items(), key=lambda x: -x[1]["count"]):
        scores = stat["scores"]
        result.append({
            "theme":        theme,
            "count":        stat["count"],
            "stock_count":  len(stat["codes"]),
            "avg_score":    round(sum(scores) / len(scores), 3) if scores else 0,
            "source":       "news",
            "_codes":       _top_codes(stat["codes"]),
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
            "_codes":       _top_codes(stat["codes"]),
        })
        seen.add(sector)

    result.sort(key=lambda x: -x["count"])
    result = result[:20]

    all_codes = list({c for item in result for c in item["_codes"]})

    # 종목명 + 등락률 일괄 조회 → Redis 실시간 현재가 보정
    name_map: dict[str, str] = {}
    price_map: dict[str, dict] = {}   # code → {change_pct, is_rising}
    if all_codes:
        name_rows = await db.fetch(
            "SELECT code, name FROM stocks WHERE code = ANY($1::text[])", all_codes
        )
        name_map = {r["code"]: r["name"] for r in name_rows}

        # daily_bars.change_rate: 전일 종가 대비 등락률 (표준 기준)
        price_rows = await db.fetch(
            """
            SELECT DISTINCT ON (code)
                code,
                close::int     AS current_price,
                COALESCE(change_rate, 0)::float AS change_rate
            FROM daily_bars
            WHERE code = ANY($1::text[])
            ORDER BY code, date DESC
            """,
            all_codes,
        )
        # Redis quote:{code} 로 실시간 보정 (장중 현재가 반영)
        price_dicts = [dict(r) for r in price_rows]
        await enrich_live_prices(
            redis, price_dicts,
            price_field="current_price",
            rate_field="change_rate",
        )
        for d in price_dicts:
            cp = d.get("change_rate") or 0.0
            price_map[d["code"]] = {"change_pct": round(cp, 2), "is_rising": cp >= 0}

    for item in result:
        codes = item.pop("_codes")
        links = []
        rising = falling = 0
        for c in codes:
            pd = price_map.get(c, {})
            cp = pd.get("change_pct")
            is_r = pd.get("is_rising", None)
            links.append({
                "code":       c,
                "name":       name_map.get(c, c),
                "change_pct": cp,
                "is_rising":  is_r,
            })
            if is_r is True:  rising  += 1
            elif is_r is False: falling += 1
        item["stock_links"]   = links
        item["rising_count"]  = rising
        item["falling_count"] = falling

    return {
        "hours":   hours,
        "since":   since.isoformat(),
        "themes":  result,
    }


@router.get("/clusters")
async def get_theme_clusters(
    redis: redis_lib.Redis = Depends(get_redis),
    db: asyncpg.Pool = Depends(get_db),
):
    """ThemeClusterer가 생성한 K-Means 동적 테마 클러스터 반환.
    stock_codes에 해당하는 종목명을 DB에서 조회해 stock_links(code+name)로 보강.
    """
    try:
        raw = await redis.get("themes:clusters")
        updated_at = await redis.get("themes:updated_at")
        if raw:
            clusters = orjson.loads(raw)
            # 전체 code 집합 수집 후 일괄 조회 (N+1 방지)
            all_codes = list({c for cl in clusters for c in cl.get("stock_codes", [])})
            name_map: dict[str, str] = {}
            if all_codes:
                rows = await db.fetch(
                    "SELECT code, name FROM stocks WHERE code = ANY($1::text[])",
                    all_codes,
                )
                name_map = {r["code"]: r["name"] for r in rows}
            for cl in clusters:
                cl["stock_links"] = [
                    {"code": c, "name": name_map.get(c, c)}
                    for c in cl.get("stock_codes", [])
                ]
            return {
                "clusters":   clusters,
                "updated_at": updated_at.decode() if updated_at else None,
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


@router.get("/spread/history")
async def get_spread_history(
    theme: str = Query(description="테마 이름"),
    days:  int  = Query(default=30, ge=1, le=180),
    db: asyncpg.Pool = Depends(get_db),
):
    """테마별 일별 스냅쌏 이력 — momentum_score·velocity·lead_codes 포함."""
    rows = await db.fetch(
        """
        SELECT snap_date::TEXT, stock_count, avg_return,
               momentum_score, velocity, lead_codes, top_codes
        FROM theme_snapshots
        WHERE theme_name = $1
          AND snap_date >= CURRENT_DATE - ($2 * INTERVAL '1 day')
        ORDER BY snap_date
        """,
        theme, days,
    )
    result = []
    all_lead_codes: set[str] = set()
    for r in rows:
        d = dict(r)
        for col in ("lead_codes", "top_codes"):
            if d.get(col):
                d[col] = [c.strip() for c in d[col].split(",") if c.strip()]
            else:
                d[col] = []
        all_lead_codes.update(d["lead_codes"])
        result.append(d)

    name_map: dict[str, str] = {}
    if all_lead_codes:
        name_rows = await db.fetch(
            "SELECT code, name FROM stocks WHERE code = ANY($1::text[])",
            list(all_lead_codes),
        )
        name_map = {r["code"]: r["name"] for r in name_rows}

    for d in result:
        d["lead_links"] = [
            {"code": c, "name": name_map.get(c, c)} for c in d["lead_codes"]
        ]

    return {"theme": theme, "days": days, "history": result}


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
