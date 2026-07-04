"""
Trader 서비스 — FastAPI + 자동매매 실행기
- Port 8004
- GET /health
- 잔고, 포지션, 주문, 설정, 손익 API 제공
- Redis Pub/Sub 기반 자동 매수 + 목표/손절 자동 매도
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional

import asyncpg
import redis.asyncio as redis_lib
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from kis.order_client import KISConfig, KISAuthManager, KISOrderClient
from risk.position_sizer import calc_qty, describe
from risk.daily_loss_guard import DailyLossGuard
from auto_executor import AutoExecutor
from schemas import (
    TraderSettings, TraderSettingsUpdate,
    ManualOrderRequest, OrderResponse, PositionResponse,
    BalanceResponse, HoldingItem, DailyPnlResponse,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("trader")

_KST = timezone(timedelta(hours=9))
_PORT = int(os.environ.get("TRADER_PORT", 8004))


def _make_kis_config() -> KISConfig:
    return KISConfig(
        app_key=os.environ["KIS_APP_KEY"],
        app_secret=os.environ["KIS_APP_SECRET"],
        account_no=os.environ["KIS_ACCOUNT_NO"],
        is_paper=os.environ.get("KIS_IS_PAPER", "true").lower() == "true",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    dsn = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
    app.state.db = await asyncpg.create_pool(
        dsn=dsn, min_size=3, max_size=15, command_timeout=15,
    )
    app.state.redis = redis_lib.from_url(
        os.environ["REDIS_URL"], decode_responses=False
    )

    # 트레이더 스키마 자동 생성 (idempotent)
    sql_path = "/app/../../infra/postgres/V19__trader.sql"
    try:
        import pathlib
        for p in [
            pathlib.Path(sql_path),
            pathlib.Path("/infra/postgres/V19__trader.sql"),
            pathlib.Path(os.path.dirname(__file__)) / "../../infra/postgres/V19__trader.sql",
        ]:
            if p.exists():
                await app.state.db.execute(p.read_text())
                logger.info(f"V19 스키마 적용: {p}")
                break
    except Exception as e:
        logger.warning(f"V19 스키마 자동 적용 실패 (무시): {e}")

    # KIS 클라이언트 초기화
    kis_cfg  = _make_kis_config()
    auth_mgr = KISAuthManager(kis_cfg, app.state.redis)
    order_client = KISOrderClient(kis_cfg, auth_mgr)
    app.state.order_client = order_client

    # 손실 가드
    daily_limit = int((await app.state.db.fetchval(
        "SELECT daily_loss_limit FROM trader_settings WHERE id=1"
    ) or 100_000))
    loss_guard = DailyLossGuard(app.state.redis, daily_limit)
    app.state.loss_guard = loss_guard

    # 자동 매매 실행기
    executor = AutoExecutor(
        db=app.state.db,
        redis_client=app.state.redis,
        order_client=order_client,
        loss_guard=loss_guard,
    )
    app.state.executor = executor
    app.state.executor_task = asyncio.create_task(executor.run())
    logger.info(f"Trader 서비스 시작 (mode={'paper' if kis_cfg.is_paper else 'live'})")

    yield

    executor.stop()
    app.state.executor_task.cancel()
    await app.state.db.close()
    await app.state.redis.close()
    logger.info("Trader 서비스 종료")


app = FastAPI(title="Trader Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db(request: Request) -> asyncpg.Pool:
    return request.app.state.db

def get_redis(request: Request) -> redis_lib.Redis:
    return request.app.state.redis

def get_order_client(request: Request) -> KISOrderClient:
    return request.app.state.order_client

def get_loss_guard(request: Request) -> DailyLossGuard:
    return request.app.state.loss_guard


@app.get("/health")
async def health():
    return {"status": "ok", "service": "trader", "ts": datetime.now(_KST).isoformat()}


# ── 설정 ──────────────────────────────────────────────────────────────────────
@app.get("/settings", response_model=TraderSettings)
async def get_settings(db: asyncpg.Pool = Depends(get_db)):
    row = await db.fetchrow("SELECT * FROM trader_settings WHERE id=1")
    if not row:
        return TraderSettings()
    return TraderSettings(**dict(row))


@app.put("/settings", response_model=TraderSettings)
async def update_settings(
    body: TraderSettingsUpdate,
    db: asyncpg.Pool = Depends(get_db),
    loss_guard: DailyLossGuard = Depends(get_loss_guard),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "변경할 항목 없음")

    set_clause = ", ".join(f"{k}=${i+2}" for i, k in enumerate(updates))
    vals = list(updates.values())
    await db.execute(
        f"UPDATE trader_settings SET {set_clause}, updated_at=NOW() WHERE id=1",
        *vals,
    )
    # 손실 한도 변경 시 가드 업데이트
    if "daily_loss_limit" in updates:
        loss_guard.limit = abs(updates["daily_loss_limit"])

    row = await db.fetchrow("SELECT * FROM trader_settings WHERE id=1")
    return TraderSettings(**dict(row))


# ── 잔고 ──────────────────────────────────────────────────────────────────────
@app.get("/balance", response_model=BalanceResponse)
async def get_balance(
    db: asyncpg.Pool = Depends(get_db),
    order_client: KISOrderClient = Depends(get_order_client),
):
    row = await db.fetchrow("SELECT mode FROM trader_settings WHERE id=1")
    mode = row["mode"] if row else "paper"

    if mode == "paper":
        # paper 모드: DB에서 계산
        positions = await db.fetch(
            "SELECT code, name, qty, avg_price, current_price FROM positions WHERE status='HOLDING' AND mode='paper'"
        )
        invested = sum(int(p["avg_price"]) * p["qty"] for p in positions)
        total_invest_limit = await db.fetchval(
            "SELECT max_total_invest FROM trader_settings WHERE id=1"
        ) or 3_000_000
        deposit = max(0, int(total_invest_limit) - invested)
        total_eval = deposit + sum(
            int(p["current_price"] or p["avg_price"]) * p["qty"] for p in positions
        )
        holdings = [
            HoldingItem(
                code=p["code"], name=p["name"] or p["code"],
                qty=p["qty"],
                avg_price=int(p["avg_price"]),
                current_price=int(p["current_price"] or p["avg_price"]),
                eval_amount=int(p["current_price"] or p["avg_price"]) * p["qty"],
                pnl_pct=round(
                    (float(p["current_price"] or p["avg_price"]) - float(p["avg_price"]))
                    / float(p["avg_price"]) * 100, 2
                ) if p["avg_price"] else 0.0,
                pnl_amount=(int(p["current_price"] or p["avg_price"]) - int(p["avg_price"])) * p["qty"],
            )
            for p in positions
        ]
        return BalanceResponse(
            success=True,
            deposit=deposit,
            total_eval=total_eval,
            total_buy=invested,
            holdings=holdings,
        )
    else:
        result = await order_client.get_balance()
        holdings = [HoldingItem(**h) for h in result.holdings]
        return BalanceResponse(
            success=result.success,
            deposit=result.deposit,
            total_eval=result.total_eval,
            total_buy=result.total_buy,
            holdings=holdings,
            error_msg=result.error_msg,
        )


# ── 보유 포지션 ───────────────────────────────────────────────────────────────
@app.get("/positions", response_model=list[PositionResponse])
async def get_positions(
    status: str = "HOLDING",
    db: asyncpg.Pool = Depends(get_db),
):
    rows = await db.fetch(
        """SELECT p.*, COALESCE(s.name, p.name, p.code) AS name
           FROM positions p
           LEFT JOIN stocks s ON s.code = p.code
           WHERE p.status = $1
           ORDER BY p.created_at DESC""",
        status,
    )
    result = []
    for r in rows:
        avg_p = float(r["avg_price"])
        cur_p = float(r["current_price"]) if r["current_price"] else avg_p
        result.append(PositionResponse(
            id=r["id"],
            code=r["code"],
            name=r["name"],
            qty=r["qty"],
            avg_price=avg_p,
            current_price=cur_p,
            target_price=float(r["target_price"]) if r["target_price"] else None,
            stop_loss_price=float(r["stop_loss_price"]) if r["stop_loss_price"] else None,
            unrealized_pct=round((cur_p - avg_p) / avg_p * 100, 2) if avg_p else None,
            unrealized_amount=round((cur_p - avg_p) * r["qty"], 0),
            invest_amount=avg_p * r["qty"],
            entry_date=str(r["entry_date"]),
            mode=r["mode"],
            rec_id=r["rec_id"],
        ))
    return result


# ── 주문 내역 ─────────────────────────────────────────────────────────────────
@app.get("/orders", response_model=list[OrderResponse])
async def get_orders(
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    db: asyncpg.Pool = Depends(get_db),
):
    where = "WHERE o.status = $2" if status else ""
    params = [limit] if not status else [limit, status]
    rows = await db.fetch(
        f"""SELECT o.*, COALESCE(s.name, o.name, o.code) AS name
            FROM orders o
            LEFT JOIN stocks s ON s.code = o.code
            {where}
            ORDER BY o.created_at DESC
            LIMIT $1""",
        *params,
    )
    return [OrderResponse(**dict(r)) for r in rows]


# ── 수동 주문 ─────────────────────────────────────────────────────────────────
@app.post("/orders", response_model=OrderResponse)
async def place_manual_order(
    body: ManualOrderRequest,
    db: asyncpg.Pool = Depends(get_db),
    order_client: KISOrderClient = Depends(get_order_client),
):
    cfg_row = await db.fetchrow("SELECT * FROM trader_settings WHERE id=1")
    if not cfg_row:
        raise HTTPException(500, "트레이더 설정 없음")
    if not cfg_row["allow_manual_order"]:
        raise HTTPException(403, "수동 주문이 비활성 상태입니다")

    mode = cfg_row["mode"]
    if mode == "paper":
        order_no = f"PAPER-MANUAL-{datetime.now(_KST).strftime('%H%M%S%f')[:12]}"
        success, err = True, None
    else:
        if body.side == "BUY":
            res = await order_client.place_buy_order(body.code, body.qty, body.price, body.order_type)
        else:
            res = await order_client.place_sell_order(body.code, body.qty, body.price, body.order_type)
        order_no = res.order_no if res.success else None
        success  = res.success
        err      = res.error_msg if not res.success else None

    name = await db.fetchval("SELECT name FROM stocks WHERE code=$1", body.code)
    row = await db.fetchrow(
        """INSERT INTO orders
           (order_no, rec_id, code, name, side, order_type, order_price, order_qty,
            filled_qty, avg_filled_price, status, mode, error_msg)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$8,$7,$9,$10,$11)
           RETURNING *""",
        order_no, body.rec_id, body.code, name, body.side, body.order_type,
        body.price, body.qty, "FILLED" if success else "FAILED", mode, err,
    )
    return OrderResponse(**dict(row))


# ── 주문 취소 ─────────────────────────────────────────────────────────────────
@app.delete("/orders/{order_id}")
async def cancel_order(
    order_id: int,
    db: asyncpg.Pool = Depends(get_db),
    order_client: KISOrderClient = Depends(get_order_client),
):
    row = await db.fetchrow("SELECT * FROM orders WHERE id=$1", order_id)
    if not row:
        raise HTTPException(404, "주문을 찾을 수 없음")
    if row["status"] not in ("PENDING", "PARTIAL"):
        raise HTTPException(400, f"취소 불가 상태: {row['status']}")

    if row["mode"] != "paper" and row["order_no"]:
        result = await order_client.cancel_order(
            row["order_no"], row["code"], row["order_qty"] - row["filled_qty"]
        )
        if not result.success:
            raise HTTPException(500, f"취소 실패: {result.error_msg}")

    await db.execute(
        "UPDATE orders SET status='CANCELLED', updated_at=NOW() WHERE id=$1", order_id
    )
    return {"success": True, "order_id": order_id}


# ── 포지션 수동 매도 ──────────────────────────────────────────────────────────
@app.post("/positions/{position_id}/sell")
async def sell_position(
    position_id: int,
    db: asyncpg.Pool = Depends(get_db),
    order_client: KISOrderClient = Depends(get_order_client),
    loss_guard: DailyLossGuard = Depends(get_loss_guard),
):
    pos = await db.fetchrow("SELECT * FROM positions WHERE id=$1 AND status='HOLDING'", position_id)
    if not pos:
        raise HTTPException(404, "포지션을 찾을 수 없음")

    cfg_row = await db.fetchrow("SELECT mode FROM trader_settings WHERE id=1")
    mode = cfg_row["mode"] if cfg_row else "paper"
    code = pos["code"]
    qty  = pos["qty"]

    if mode == "paper":
        # Redis에서 현재가 조회
        cur_val = await app.state.redis.get(f"price:{code}")
        sell_price = int(cur_val) if cur_val else int(pos["avg_price"])
        order_no   = f"PAPER-SELL-MANUAL-{datetime.now(_KST).strftime('%H%M%S%f')[:12]}"
        success, err = True, None
    else:
        res = await order_client.place_sell_order(code, qty, price=0, order_type="MARKET")
        order_no   = res.order_no if res.success else None
        success    = res.success
        err        = res.error_msg if not res.success else None
        sell_price = int(pos["avg_price"])  # 시장가라 정확한 체결가는 이후 조회 필요

    if not success:
        raise HTTPException(500, f"매도 실패: {err}")

    pnl_pct    = round((sell_price - float(pos["avg_price"])) / float(pos["avg_price"]) * 100, 2)
    pnl_amount = (sell_price - int(pos["avg_price"])) * qty

    order_id = await db.fetchval(
        """INSERT INTO orders
           (order_no, rec_id, code, side, order_type, order_price, order_qty,
            filled_qty, avg_filled_price, status, mode)
           VALUES ($1,$2,$3,'SELL','MARKET',$4,$5,$5,$4,'FILLED',$6)
           RETURNING id""",
        order_no, pos["rec_id"], code, sell_price, qty, mode,
    )
    await db.execute(
        """UPDATE positions SET
           status='CLOSED', close_reason='MANUAL', exit_order_id=$1,
           closed_at=NOW(), closed_price=$2, pnl_pct=$3, pnl_amount=$4, updated_at=NOW()
           WHERE id=$5""",
        order_id, sell_price, pnl_pct, pnl_amount, position_id,
    )
    if pnl_amount < 0:
        await loss_guard.record_loss(pnl_amount)

    return {"success": True, "pnl_pct": pnl_pct, "pnl_amount": pnl_amount}


# ── 일일 손익 ─────────────────────────────────────────────────────────────────
@app.get("/daily-pnl", response_model=list[DailyPnlResponse])
async def get_daily_pnl(
    days: int = Query(default=30, le=90),
    db: asyncpg.Pool = Depends(get_db),
    loss_guard: DailyLossGuard = Depends(get_loss_guard),
):
    rows = await db.fetch(
        """SELECT * FROM daily_pnl
           ORDER BY trade_date DESC LIMIT $1""",
        days,
    )
    guard_status = await loss_guard.get_status()
    result = []
    for r in rows:
        total = r["total_trades"]
        win   = r["win_trades"]
        result.append(DailyPnlResponse(
            trade_date=str(r["trade_date"]),
            mode=r["mode"],
            realized_pnl=int(r["realized_pnl"]),
            unrealized_pnl=int(r["unrealized_pnl"]),
            total_trades=total,
            win_trades=win,
            loss_trades=r["loss_trades"],
            buy_amount=int(r["buy_amount"]),
            sell_amount=int(r["sell_amount"]),
            is_limit_hit=r["is_limit_hit"],
            win_rate=round(win / total * 100, 1) if total > 0 else None,
            today_loss_guard=guard_status if str(r["trade_date"]) == str(datetime.now(_KST).date()) else None,
        ))
    return result


# ── 손실 가드 리셋 (관리자) ───────────────────────────────────────────────────
@app.post("/loss-guard/reset")
async def reset_loss_guard(loss_guard: DailyLossGuard = Depends(get_loss_guard)):
    await loss_guard.reset()
    return {"success": True, "message": "일일 손실 가드 리셋 완료"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=_PORT, reload=False)
