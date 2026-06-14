from fastapi import APIRouter, Request, Query
from typing import Optional

router = APIRouter()


@router.get("")
async def list_performance(
    request: Request,
    code:     Optional[str]  = None,
    event_type: Optional[str]= None,
    complete: Optional[bool] = None,
    success:  Optional[bool] = None,
    limit: int  = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conds, params = [], []
    def p(v):
        params.append(v); return f"${len(params)}"
    if code:       conds.append(f"rp.code={p(code)}")
    if event_type: conds.append(f"rp.event_type={p(event_type)}")
    if complete is not None: conds.append(f"rp.tracking_complete={p(complete)}")
    if success  is not None: conds.append(f"rp.is_success={p(success)}")
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    params += [limit, offset]
    sql = f"""
        SELECT rp.id, rp.rec_id, rp.code, s.name,
               rp.event_type, rp.entry_price, rp.signal_time,
               rp.r_1h, rp.r_3h, rp.r_5h,
               rp.r_1d, rp.r_2d, rp.r_3d, rp.r_4d,
               rp.r_5d, rp.r_7d, rp.r_10d,
               rp.r_special, rp.special_type, rp.special_date,
               rp.is_success, rp.max_return,
               rp.hit_target, rp.hit_stop,
               rp.tracking_complete, rp.last_updated
        FROM recommendation_performance rp
        LEFT JOIN stocks s ON s.code = rp.code
        {where}
        ORDER BY rp.signal_time DESC
        LIMIT ${len(params)-1} OFFSET ${len(params)}
    """
    sql_total = f"SELECT COUNT(*) FROM recommendation_performance rp {where}"
    async with request.app.state.db.acquire() as conn:
        total = await conn.fetchval(sql_total, *params[:-2])
        rows  = await conn.fetch(sql, *params)
    return {"total": total, "offset": offset, "limit": limit,
            "items": [dict(r) for r in rows]}


@router.get("/summary")
async def performance_summary(request: Request, days: int = Query(30, ge=1, le=365)):
    sql = """
        SELECT
            COUNT(*)                                              AS total,
            COUNT(*) FILTER (WHERE tracking_complete)            AS completed,
            COUNT(*) FILTER (WHERE is_success = TRUE)            AS success,
            COUNT(*) FILTER (WHERE is_success = FALSE)           AS fail,
            ROUND(AVG(r_1d)::NUMERIC,2)                          AS avg_r_1d,
            ROUND(AVG(r_3d)::NUMERIC,2)                          AS avg_r_3d,
            ROUND(AVG(r_5d)::NUMERIC,2)                          AS avg_r_5d,
            ROUND(AVG(r_10d)::NUMERIC,2)                         AS avg_r_10d,
            ROUND(AVG(max_return)::NUMERIC,2)                    AS avg_max_return,
            ROUND(
              100.0 * COUNT(*) FILTER (WHERE is_success=TRUE) /
              NULLIF(COUNT(*) FILTER (WHERE tracking_complete),0)
            ,1)                                                   AS success_rate,
            COUNT(*) FILTER (WHERE hit_target)                   AS hit_target_cnt,
            COUNT(*) FILTER (WHERE hit_stop)                     AS hit_stop_cnt
        FROM recommendation_performance
        WHERE signal_time >= NOW() - ($1 * INTERVAL '1 day')
    """
    by_event_sql = """
        SELECT event_type,
               COUNT(*) AS cnt,
               ROUND(100.0 * COUNT(*) FILTER (WHERE is_success) / NULLIF(COUNT(*) FILTER (WHERE tracking_complete),0),1) AS win_rate,
               ROUND(AVG(r_5d)::NUMERIC,2) AS avg_r5d
        FROM recommendation_performance
        WHERE signal_time >= NOW() - ($1 * INTERVAL '1 day')
          AND event_type IS NOT NULL
        GROUP BY event_type ORDER BY cnt DESC
    """
    async with request.app.state.db.acquire() as conn:
        row      = await conn.fetchrow(sql, days)
        ev_rows  = await conn.fetch(by_event_sql, days)
    return {
        **dict(row),
        "by_event": [dict(r) for r in ev_rows],
    }


@router.get("/ml-export")
async def ml_export(request: Request, days: int = Query(90, ge=7, le=365)):
    """ML 학습용 데이터 — tracking_complete=True 인 행만"""
    sql = """
        SELECT rp.code, rp.event_type, rp.entry_price,
               rp.r_1h, rp.r_3h, rp.r_5h,
               rp.r_1d, rp.r_2d, rp.r_3d, rp.r_5d, rp.r_7d, rp.r_10d,
               rp.is_success, rp.hit_target, rp.hit_stop, rp.max_return,
               r.success_prob, r.risk_score, r.risk_reward_ratio,
               r.expected_return, r.expected_hold_days,
               fe.signal_score, fe.volume_ratio, fe.change_rate,
               s.market, s.sector
        FROM recommendation_performance rp
        JOIN recommendations r ON r.id = rp.rec_id
        LEFT JOIN feature_events fe ON fe.id = r.feature_event_id
        LEFT JOIN stocks s ON s.code = rp.code
        WHERE rp.tracking_complete = TRUE
          AND rp.signal_time >= NOW() - ($1 * INTERVAL '1 day')
        ORDER BY rp.signal_time DESC
    """
    async with request.app.state.db.acquire() as conn:
        rows = await conn.fetch(sql, days)
    return {"count": len(rows), "rows": [dict(r) for r in rows]}
