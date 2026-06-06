from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import asyncpg
from deps import get_db

router = APIRouter()


class FilterCreate(BaseModel):
    type: str   # "keyword" | "stock"
    value: str


@router.get("")
async def list_filters(db: asyncpg.Pool = Depends(get_db)):
    rows = await db.fetch(
        "SELECT id, type, value, created_at::TEXT FROM disclosure_filters ORDER BY type, value"
    )
    return [dict(r) for r in rows]


@router.post("", status_code=201)
async def create_filter(body: FilterCreate, db: asyncpg.Pool = Depends(get_db)):
    if body.type not in ("keyword", "stock"):
        raise HTTPException(400, "type은 'keyword' 또는 'stock'이어야 합니다")
    value = body.value.strip()
    if not value:
        raise HTTPException(400, "value가 비어있습니다")
    try:
        row = await db.fetchrow(
            """
            INSERT INTO disclosure_filters (type, value)
            VALUES ($1, $2)
            ON CONFLICT (type, value) DO NOTHING
            RETURNING id, type, value, created_at::TEXT
            """,
            body.type, value,
        )
    except Exception as e:
        raise HTTPException(500, str(e))
    if not row:
        raise HTTPException(409, "이미 등록된 필터입니다")
    return dict(row)


@router.delete("/{filter_id}", status_code=204)
async def delete_filter(filter_id: int, db: asyncpg.Pool = Depends(get_db)):
    result = await db.execute(
        "DELETE FROM disclosure_filters WHERE id = $1", filter_id
    )
    if result == "DELETE 0":
        raise HTTPException(404, "필터를 찾을 수 없습니다")
