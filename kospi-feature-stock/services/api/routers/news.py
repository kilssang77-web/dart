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


_NEWS_SELECT = """
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
            SELECT json_agg(json_build_object('code', s.code, 'name', s.name) ORDER BY nsl.news_id, nsl.code)
            FROM news_stock_links nsl
            JOIN stocks s ON s.code = nsl.code
            WHERE nsl.news_id = n.id LIMIT 5
        ) AS stock_links_raw,
        (
            SELECT s.name FROM news_stock_links nsl
            JOIN stocks s ON s.code = nsl.code
            WHERE nsl.news_id = n.id LIMIT 1
        ) AS corp_name
    FROM news n
"""


def _parse_news_rows(rows) -> list[NewsItem]:
    result: list[NewsItem] = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("keywords"), str):
            try:
                d["keywords"] = json.loads(d["keywords"])
            except Exception as e:
                logger.warning(f"news keywords parse error id={d.get('id')}: {e}")
                d["keywords"] = []
        raw_links = d.pop("stock_links_raw", None)
        if raw_links:
            if isinstance(raw_links, str):
                try:
                    raw_links = json.loads(raw_links)
                except Exception:
                    raw_links = []
            d["stock_links"] = [{"code": x["code"], "name": x["name"]} for x in (raw_links or [])]
        result.append(NewsItem(**d))
    return result


@router.get("/sources")
async def list_news_sources(
    hours: int = Query(default=72, le=168),
    db: asyncpg.Pool = Depends(get_db),
):
    """뉴스 소스 목록 반환."""
    rows = await db.fetch(
        "SELECT DISTINCT source FROM news WHERE published_at >= NOW() - ($1 * INTERVAL '1 hour') ORDER BY source",
        hours,
    )
    return [r["source"] for r in rows if r["source"]]


@router.get("/{news_id}/similar")
async def similar_news(
    news_id: int,
    top_k: int = Query(default=5, ge=1, le=10),
    db: asyncpg.Pool = Depends(get_db),
):
    """임베딩 기반 유사 뉴스 (pgvector cosine)."""
    ref = await db.fetchrow("SELECT embedding FROM news WHERE id = $1", news_id)
    if not ref or ref["embedding"] is None:
        return []

    rows = await db.fetch(
        f"""
        {_NEWS_SELECT}
        WHERE n.id != $1 AND n.embedding IS NOT NULL
        ORDER BY n.embedding <=> $2::vector
        LIMIT $3
        """,
        news_id, ref["embedding"], top_k,
    )
    return _parse_news_rows(rows)


@router.get("", response_model=list[NewsItem])
async def list_news(
    code:     str | None = None,
    category: str | None = Query(default=None, pattern="^(favorable|unfavorable|neutral)$"),
    hours:    int        = Query(default=24, le=168),
    limit:    int        = Query(default=50, le=200),
    offset:   int        = Query(default=0, ge=0),
    source:   str | None = None,
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

    if source:
        params.append(source)
        where.append(f"n.source = ${len(params)}")

    params.append(limit)
    params.append(offset)
    rows = await db.fetch(
        f"""
        {_NEWS_SELECT}
        WHERE {' AND '.join(where)}
        ORDER BY n.published_at DESC
        LIMIT ${len(params) - 1} OFFSET ${len(params)}
        """,
        *params,
    )
    return _parse_news_rows(rows)
