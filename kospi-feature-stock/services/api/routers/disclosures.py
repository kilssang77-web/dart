from fastapi import APIRouter, Depends, Query
import asyncpg
import redis.asyncio as redis_lib
from deps import get_db, get_redis
from services.disclosure_service import DisclosureService

router = APIRouter()


def _svc(db: asyncpg.Pool = Depends(get_db), redis: redis_lib.Redis = Depends(get_redis)) -> DisclosureService:
    return DisclosureService(db, redis)


@router.get("")
async def list_disclosures(
    code:     str | None = None,
    category: str | None = None,
    market:   str | None = None,
    flagged:  bool | None = None,
    hours:    int = Query(default=72, le=168),
    limit:    int = Query(default=50, le=200),
    svc: DisclosureService = Depends(_svc),
):
    return await svc.list_disclosures(code, category, market, flagged, hours, limit)


@router.get("/favorable")
async def favorable_disclosures(
    hours:  int = Query(default=48, le=168),
    market: str | None = None,
    svc: DisclosureService = Depends(_svc),
):
    return await svc.list_favorable(hours, market)


@router.get("/{rcept_no}/predict-impact")
async def predict_disclosure_impact(
    rcept_no: str,
    top_k: int = Query(default=5, ge=1, le=20),
    db: asyncpg.Pool = Depends(get_db),
):
    """유사 공시 기반 가격 충격 예측 (pgvector 코사인 유사도)."""
    anchor = await db.fetchrow(
        "SELECT id, code, embedding, category, sentiment_score FROM disclosures WHERE rcept_no=$1",
        rcept_no,
    )
    if not anchor:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Disclosure not found")

    if anchor["embedding"] is None:
        return {"predicted_1d": None, "predicted_3d": None, "confidence": 0.0,
                "similar_count": 0, "note": "embedding_not_computed"}

    rows = await db.fetch(
        """
        SELECT d.rcept_no, d.title, d.sentiment_score, d.category,
               d.post_1d_change, d.post_3d_change,
               ROUND((1 - (d.embedding <=> $2::vector))::NUMERIC, 4) AS similarity
        FROM disclosures d
        WHERE d.rcept_no != $1
          AND d.embedding IS NOT NULL
          AND d.post_1d_change IS NOT NULL
        ORDER BY d.embedding <=> $2::vector
        LIMIT $3
        """,
        rcept_no, anchor["embedding"], top_k,
    )

    if not rows:
        return {"predicted_1d": None, "predicted_3d": None, "confidence": 0.0,
                "similar_count": 0, "note": "no_similar_found"}

    import statistics
    changes_1d = [float(r["post_1d_change"]) for r in rows if r["post_1d_change"] is not None]
    changes_3d = [float(r["post_3d_change"]) for r in rows if r["post_3d_change"] is not None]
    sims       = [float(r["similarity"]) for r in rows if r["similarity"] is not None]

    avg_sim = statistics.mean(sims) if sims else 0.0
    confidence = round(min(1.0, avg_sim * len(rows) / top_k), 3)

    return {
        "predicted_1d":   round(statistics.mean(changes_1d), 3) if changes_1d else None,
        "predicted_3d":   round(statistics.mean(changes_3d), 3) if changes_3d else None,
        "std_1d":         round(statistics.stdev(changes_1d), 3) if len(changes_1d) > 1 else 0.0,
        "confidence":     confidence,
        "avg_similarity": round(avg_sim, 4),
        "similar_count":  len(rows),
        "similar": [
            {
                "rcept_no":       r["rcept_no"],
                "title":          r["title"],
                "category":       r["category"],
                "similarity":     float(r["similarity"] or 0),
                "post_1d_change": float(r["post_1d_change"] or 0),
            }
            for r in rows[:3]
        ],
    }


@router.get("/{rcept_no}")
async def get_disclosure(rcept_no: str, svc: DisclosureService = Depends(_svc)):
    return await svc.get_by_rcept_no(rcept_no)
