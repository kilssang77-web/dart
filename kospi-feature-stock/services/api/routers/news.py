from fastapi import APIRouter, Depends, Query
import asyncpg
import json
import logging
from deps import get_db
from schemas.responses import NewsItem

router = APIRouter()
logger = logging.getLogger("api.news")

_CATEGORY_CONDITIONS: dict[str, str] = {
    "favorable":   "n.sentiment_score > 0.1",
    "unfavorable": "n.sentiment_score < -0.1",
    "neutral":     "n.sentiment_score BETWEEN -0.1 AND 0.1",
}


@router.get("", response_model=list[NewsItem])
async def list_news(
    code:     str | None = None,
    category: str | None = Query(default=None, pattern="^(favorable|unfavorable|neutral)$"),
    hours:    int        = Query(default=24, le=168),
    limit:    int        = Query(default=50, le=200),
    db: asyncpg.Pool = Depends(get_db),
) -> list[NewsItem]:
    where: list[str] = ["n.published_at >= NOW() - ($1 * INTERVAL '1 hour')"]
    params: list = [hours]

    if category and category in _CATEGORY_CONDITIONS:
        where.append(_CATEGORY_CONDITIONS[category])

    if code:
        params.append(code)
        where.append(
            f"EXISTS ("
            f"SELECT 1 FROM news_stock_links nsl "
            f"WHERE nsl.news_id = n.id AND nsl.code = ${len(params)}"
            f")"
        )

    params.append(limit)
    rows = await db.fetch(
        f"""
        SELECT
            n.id, n.source,
            (n.published_at AT TIME ZONE 'Asia/Seoul')::TEXT AS published_at,
            n.title, n.content, n.url,
            n.sentiment_score,
            CASE
                WHEN n.sentiment_score >  0.1 THEN 'favorable'
                WHEN n.sentiment_score < -0.1 THEN 'unfavorable'
                ELSE 'neutral'
            END AS category,
            n.keywords,
            ARRAY(
                SELECT nsl.code FROM news_stock_links nsl WHERE nsl.news_id = n.id LIMIT 5
            ) AS codes,
            (
                SELECT s.name FROM news_stock_links nsl
                JOIN stocks s ON s.code = nsl.code
                WHERE nsl.news_id = n.id LIMIT 1
            ) AS corp_name
        FROM news n
        WHERE {' AND '.join(where)}
        ORDER BY n.published_at DESC
        LIMIT ${len(params)}
        """,
        *params,
    )

    result: list[NewsItem] = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("keywords"), str):
            try:
                d["keywords"] = json.loads(d["keywords"])
            except Exception as e:
                logger.warning(f"news keywords parse error id={d.get('id')}: {e}")
                d["keywords"] = []
        result.append(NewsItem(**d))
    return result
