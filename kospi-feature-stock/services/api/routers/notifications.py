import json
import os
import httpx
from fastapi import APIRouter, HTTPException, Request, Query
from typing import Optional

router = APIRouter()

TELEGRAM_API = "https://api.telegram.org"


@router.get("")
async def list_logs(
    request:  Request,
    msg_type: Optional[str] = Query(None, description="signal | disclosure"),
    code:     Optional[str] = Query(None),
    success:  Optional[bool] = Query(None),
    limit:    int = Query(50, ge=1, le=200),
    offset:   int = Query(0, ge=0),
):
    filter_params: list = []
    conditions:    list = []

    if msg_type:
        filter_params.append(msg_type)
        conditions.append(f"msg_type = ${len(filter_params)}")
    if code:
        filter_params.append(code)
        conditions.append(f"code = ${len(filter_params)}")
    if success is not None:
        filter_params.append(success)
        conditions.append(f"success = ${len(filter_params)}")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    n = len(filter_params)  # 필터 파라미터 수 — LIMIT/OFFSET 인덱스 기준점

    sql_total = f"SELECT COUNT(*) FROM telegram_logs {where}"
    sql_rows  = f"""
        SELECT id, msg_type, code, name, title, message, success, error_msg,
               sent_at AT TIME ZONE 'Asia/Seoul' AS sent_at
        FROM telegram_logs
        {where}
        ORDER BY sent_at DESC
        LIMIT ${n + 1} OFFSET ${n + 2}
    """
    page_params = filter_params + [limit, offset]

    async with request.app.state.db.acquire() as conn:
        total = await conn.fetchval(sql_total, *filter_params)
        rows  = await conn.fetch(sql_rows, *page_params)

    return {
        "total":  total,
        "offset": offset,
        "limit":  limit,
        "items":  [dict(r) for r in rows],
    }


@router.get("/stats")
async def log_stats(request: Request):
    sql = """
        SELECT
            COUNT(*)                                              AS total,
            COUNT(*) FILTER (WHERE success = TRUE)               AS success_count,
            COUNT(*) FILTER (WHERE success = FALSE)              AS fail_count,
            COUNT(*) FILTER (WHERE msg_type = 'signal')          AS signal_count,
            COUNT(*) FILTER (WHERE msg_type = 'disclosure')      AS disclosure_count,
            COUNT(*) FILTER (WHERE sent_at >= NOW() - INTERVAL '24 hours') AS today_count,
            MAX(sent_at) AT TIME ZONE 'Asia/Seoul'               AS last_sent_at
        FROM telegram_logs
    """
    async with request.app.state.db.acquire() as conn:
        row = await conn.fetchrow(sql)
    return dict(row)


@router.post("/{log_id}/retry")
async def retry_log(log_id: int, request: Request):
    db = request.app.state.db

    row = await db.fetchrow(
        "SELECT id, msg_type, code, name, title, message FROM telegram_logs WHERE id = $1",
        log_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Log not found")

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id   = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        raise HTTPException(status_code=503, detail="Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 미설정)")

    url     = f"{TELEGRAM_API}/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": row["message"], "parse_mode": "HTML"}
    ok, err = True, None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
            resp.raise_for_status()
    except Exception as e:
        ok, err = False, str(e)

    await db.execute(
        """
        INSERT INTO telegram_logs (msg_type, code, name, title, message, success, error_msg)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        row["msg_type"], row["code"], row["name"], row["title"], row["message"], ok, err,
    )

    if not ok:
        raise HTTPException(status_code=502, detail=err)
    return {"success": True}
