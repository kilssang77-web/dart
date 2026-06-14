from fastapi import APIRouter, Request, Query
from typing import Optional
from datetime import datetime

router = APIRouter()


@router.get("")
async def list_logs(
    request:  Request,
    msg_type: Optional[str] = Query(None, description="signal | disclosure"),
    code:     Optional[str] = Query(None),
    success:  Optional[bool] = Query(None),
    limit:    int = Query(50, ge=1, le=200),
    offset:   int = Query(0, ge=0),
):
    conditions = []
    params: list = []

    if msg_type:
        params.append(msg_type)
        conditions.append(f"msg_type = ${len(params)}")
    if code:
        params.append(code)
        conditions.append(f"code = ${len(params)}")
    if success is not None:
        params.append(success)
        conditions.append(f"success = ${len(params)}")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params += [limit, offset]

    sql_total = f"SELECT COUNT(*) FROM telegram_logs {where}"
    sql_rows  = f"""
        SELECT id, msg_type, code, name, title, message, success, error_msg,
               sent_at AT TIME ZONE 'Asia/Seoul' AS sent_at
        FROM telegram_logs
        {where}
        ORDER BY sent_at DESC
        LIMIT ${len(params) - 1} OFFSET ${len(params)}
    """

    async with request.app.state.db.acquire() as conn:
        total = await conn.fetchval(sql_total, *params[:-2])
        rows  = await conn.fetch(sql_rows, *params)

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
