import logging
from dataclasses import dataclass
from typing import Optional
import asyncpg
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SimilarCase:
    id: int
    code: str
    detected_at: str
    event_type: str
    similarity: float
    result_1d: Optional[float]
    result_3d: Optional[float]
    result_5d: Optional[float]

    @property
    def is_success(self) -> bool:
        return (self.result_5d or 0.0) >= 5.0


class SimilarCaseSearcher:

    def __init__(self, db_pool: asyncpg.Pool):
        self.pool = db_pool

    async def search(
        self,
        vector: np.ndarray,
        event_type: Optional[str] = None,
        top_k: int = 30,
        min_sim: float = 0.65,
    ) -> list[SimilarCase]:
        vec_str = "[" + ",".join(f"{v:.6f}" for v in vector.tolist()) + "]"

        clause = ""
        params: list = [vec_str, top_k, min_sim]
        if event_type:
            clause = "AND event_type = $4"
            params.append(event_type)

        query = f"""
            SELECT
                id,
                code,
                detected_at::TEXT,
                event_type,
                1 - (pattern_vector <=> $1::vector) AS similarity,
                result_1d, result_3d, result_5d
            FROM feature_events
            WHERE
                pattern_vector IS NOT NULL
                AND result_5d IS NOT NULL
                AND 1 - (pattern_vector <=> $1::vector) >= $3
                {clause}
            ORDER BY pattern_vector <=> $1::vector
            LIMIT $2
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, *params)
        except Exception as e:
            logger.error(f"Similar case search error: {e}")
            return []

        return [
            SimilarCase(
                id=r["id"],
                code=r["code"],
                detected_at=r["detected_at"],
                event_type=r["event_type"],
                similarity=float(r["similarity"]),
                result_1d=r["result_1d"],
                result_3d=r["result_3d"],
                result_5d=r["result_5d"],
            )
            for r in rows
        ]

    def aggregate_stats(self, cases: list[SimilarCase]) -> dict:
        if not cases:
            return {"success_rate": 0.5, "avg_return_5d": 0.0, "count": 0}

        weights  = [c.similarity for c in cases]
        total_w  = sum(weights) or 1.0
        w_success = sum(c.similarity * c.is_success for c in cases)

        returns_5d = [c.result_5d for c in cases if c.result_5d is not None]
        returns_3d = [c.result_3d for c in cases if c.result_3d is not None]

        return {
            "success_rate":  round(w_success / total_w, 4),
            "avg_return_5d": round(float(np.mean(returns_5d)) if returns_5d else 0.0, 2),
            "avg_return_3d": round(float(np.mean(returns_3d)) if returns_3d else 0.0, 2),
            "count":         len(cases),
            "top3": [
                {
                    "code": c.code,
                    "date": c.detected_at[:10],
                    "similarity": round(c.similarity, 3),
                    "return_5d": c.result_5d,
                }
                for c in sorted(cases, key=lambda x: -x.similarity)[:3]
            ],
        }
