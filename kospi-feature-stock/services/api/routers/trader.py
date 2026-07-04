"""
Trader API 라우터 — /api/v1/trader/*
트레이더 서비스(port 8004)에 HTTP 프록시 + DB 직접 조회 혼합
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import asyncpg
import httpx
import redis.asyncio as redis_lib
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()

_TRADER_URL = os.environ.get("TRADER_SERVICE_URL", "http://trader:8004")
_KST = timezone(timedelta(hours=9))


def get_db(request: Request) -> asyncpg.Pool:
    return request.app.state.db

def get_redis(request: Request) -> redis_lib.Redis:
    return request.app.state.redis


# ── 프록시 헬퍼 ───────────────────────────────────────────────────────────────
async def _proxy_get(path: str, params: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{_TRADER_URL}{path}", params=params)
        resp.raise_for_status()
        return resp.json()


async def _proxy_post(path: str, body: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(f"{_TRADER_URL}{path}", json=body or {})
        resp.raise_for_status()
        return resp.json()


async def _proxy_put(path: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.put(f"{_TRADER_URL}{path}", json=body)
        resp.raise_for_status()
        return resp.json()


async def _proxy_delete(path: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.delete(f"{_TRADER_URL}{path}")
        resp.raise_for_status()
        return resp.json()


# ── 트레이더 서비스 상태 확인 헬퍼 ─────────────────────────────────────────
async def _trader_health() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{_TRADER_URL}/health")
            return resp.status_code == 200
    except Exception:
        return False


# ── 헬스 ──────────────────────────────────────────────────────────────────────
@router.get("/health")
async def trader_health():
    ok = await _trader_health()
    return {"trader_service": "ok" if ok else "unavailable", "trader_url": _TRADER_URL}


# ── 설정 ──────────────────────────────────────────────────────────────────────
@router.get("/settings")
async def get_settings():
    try:
        return await _proxy_get("/settings")
    except Exception:
        # trader 서비스 다운 시 DB 직접 조회
        raise HTTPException(503, "Trader 서비스 연결 불가")


class TraderSettingsUpdate(BaseModel):
    is_active: Optional[bool] = None
    mode: Optional[str] = None
    sizing_method: Optional[str] = None
    max_invest_per_trade: Optional[int] = None
    max_total_invest: Optional[int] = None
    max_positions: Optional[int] = None
    daily_loss_limit: Optional[int] = None
    min_prob: Optional[float] = None
    kelly_fraction: Optional[float] = None
    fixed_fraction_pct: Optional[float] = None
    auto_sell: Optional[bool] = None
    allow_manual_order: Optional[bool] = None


@router.put("/settings")
async def update_settings(body: TraderSettingsUpdate):
    try:
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        return await _proxy_put("/settings", updates)
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text)
    except Exception as e:
        raise HTTPException(503, f"Trader 서비스 오류: {e}")


# ── 잔고 ──────────────────────────────────────────────────────────────────────
@router.get("/balance")
async def get_balance():
    try:
        return await _proxy_get("/balance")
    except Exception as e:
        raise HTTPException(503, f"잔고 조회 실패: {e}")


# ── 보유 포지션 ───────────────────────────────────────────────────────────────
@router.get("/positions")
async def get_positions(
    status: str = "HOLDING",
    db: asyncpg.Pool = Depends(get_db),
):
    # DB 직접 조회 (항상 최신 데이터)
    rows = await db.fetch(
        """SELECT p.*,
               COALESCE(s.name, p.name, p.code) AS name,
               COALESCE(s.market, '-') AS market,
               CASE WHEN p.current_price IS NOT NULL
                    THEN ROUND((p.current_price - p.avg_price) / p.avg_price * 100, 2)
                    ELSE NULL END AS unrealized_pct,
               CASE WHEN p.current_price IS NOT NULL
                    THEN (p.current_price - p.avg_price) * p.qty
                    ELSE NULL END AS unrealized_amount,
               p.avg_price * p.qty AS invest_amount
           FROM positions p
           LEFT JOIN stocks s ON s.code = p.code
           WHERE p.status = $1
           ORDER BY p.created_at DESC""",
        status,
    )
    return [dict(r) for r in rows]


# ── 주문 내역 ─────────────────────────────────────────────────────────────────
@router.get("/orders")
async def get_orders(
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    db: asyncpg.Pool = Depends(get_db),
):
    where = "WHERE o.status = $2" if status else ""
    params = [limit] if not status else [limit, status]
    rows = await db.fetch(
        f"""SELECT o.*,
               COALESCE(s.name, o.name, o.code) AS name,
               r.action AS rec_action,
               r.success_prob AS rec_prob
           FROM orders o
           LEFT JOIN stocks s ON s.code = o.code
           LEFT JOIN recommendations r ON r.id = o.rec_id
           {where}
           ORDER BY o.created_at DESC
           LIMIT $1""",
        *params,
    )
    return [dict(r) for r in rows]


# ── 수동 주문 ─────────────────────────────────────────────────────────────────
class ManualOrderRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=10)
    side: str = Field(..., pattern="^(BUY|SELL)$")
    qty: int = Field(..., ge=1)
    price: int = Field(default=0, ge=0)
    order_type: str = Field(default="MARKET", pattern="^(MARKET|LIMIT)$")
    rec_id: Optional[int] = None


@router.post("/orders")
async def place_manual_order(body: ManualOrderRequest):
    try:
        return await _proxy_post("/orders", body.model_dump())
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text)
    except Exception as e:
        raise HTTPException(503, f"주문 실패: {e}")


@router.delete("/orders/{order_id}")
async def cancel_order(order_id: int):
    try:
        return await _proxy_delete(f"/orders/{order_id}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text)
    except Exception as e:
        raise HTTPException(503, f"취소 실패: {e}")


# ── 포지션 수동 매도 ──────────────────────────────────────────────────────────
@router.post("/positions/{position_id}/sell")
async def sell_position(position_id: int):
    try:
        return await _proxy_post(f"/positions/{position_id}/sell")
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, e.response.text)
    except Exception as e:
        raise HTTPException(503, f"매도 실패: {e}")


# ── 일일 손익 ─────────────────────────────────────────────────────────────────
@router.get("/daily-pnl")
async def get_daily_pnl(
    days: int = Query(default=30, le=90),
    db: asyncpg.Pool = Depends(get_db),
):
    rows = await db.fetch(
        """SELECT dp.*,
               CASE WHEN dp.total_trades > 0
                    THEN ROUND(dp.win_trades::NUMERIC / dp.total_trades * 100, 1)
                    ELSE NULL END AS win_rate
           FROM daily_pnl dp
           ORDER BY dp.trade_date DESC LIMIT $1""",
        days,
    )
    return [dict(r) for r in rows]


# ── 손실 가드 상태 ────────────────────────────────────────────────────────────
@router.get("/loss-guard")
async def get_loss_guard_status():
    try:
        return await _proxy_get("/daily-pnl")
    except Exception:
        return {"error": "Trader 서비스 연결 불가"}


@router.post("/loss-guard/reset")
async def reset_loss_guard():
    try:
        return await _proxy_post("/loss-guard/reset")
    except Exception as e:
        raise HTTPException(503, f"리셋 실패: {e}")


# ── 자동 실행 로그 (DB 조회) ─────────────────────────────────────────────────
@router.get("/execution-log")
async def get_execution_log(
    limit: int = Query(default=50, le=200),
    db: asyncpg.Pool = Depends(get_db),
):
    rows = await db.fetch(
        """SELECT o.*,
               COALESCE(s.name, o.name, o.code) AS name,
               r.success_prob, r.target_price AS rec_target, r.stop_loss_price AS rec_stop
           FROM orders o
           LEFT JOIN stocks s ON s.code = o.code
           LEFT JOIN recommendations r ON r.id = o.rec_id
           WHERE o.rec_id IS NOT NULL
           ORDER BY o.created_at DESC LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


# ── 포지션 통계 요약 ──────────────────────────────────────────────────────────
@router.get("/summary")
async def get_summary(db: asyncpg.Pool = Depends(get_db)):
    today = datetime.now(_KST).date()
    active_positions = await db.fetchval(
        "SELECT COUNT(*) FROM positions WHERE status='HOLDING'"
    )
    today_pnl = await db.fetchrow(
        "SELECT * FROM daily_pnl WHERE trade_date=$1", today
    )
    total_closed = await db.fetchrow(
        """SELECT COUNT(*) AS cnt,
               ROUND(AVG(pnl_pct)::NUMERIC, 2) AS avg_pnl,
               COUNT(*) FILTER (WHERE pnl_pct > 0) AS wins
           FROM positions WHERE status='CLOSED'"""
    )
    return {
        "active_positions": active_positions,
        "today": dict(today_pnl) if today_pnl else None,
        "all_time": dict(total_closed) if total_closed else None,
    }
