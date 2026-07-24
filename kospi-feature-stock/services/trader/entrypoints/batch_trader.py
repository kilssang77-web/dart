"""
배치 자동매매 실행기 — GitHub Actions 10분 간격 1회성 실행.

흐름:
  1. 최근 LOOKBACK_MIN분 내 BUY 추천 중 미체결 건 조회
  2. 각 추천에 대해 조건 검증 (설정, 손실가드, 중복 포지션)
  3. 포지션 사이징 후 주문 실행 (paper 기본 / KIS_IS_PAPER=false 시 실전)
  4. 실행 결과 Telegram 알림
"""
import asyncio
import logging
import os
import ssl
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

import asyncpg
import orjson
import redis.asyncio as redis_lib

# 트레이더 서비스 모듈 경로 추가
_TRADER_SVC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _TRADER_SVC)

from kis.order_client import KISConfig, KISAuthManager, KISOrderClient
from risk.position_sizer import calc_qty
from risk.daily_loss_guard import DailyLossGuard

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [batch-trader] %(levelname)s %(message)s",
)
logger = logging.getLogger("batch-trader")

_KST         = timezone(timedelta(hours=9))
_TG_TOKEN    = os.environ.get("TELEGRAM_TOKEN", "")
_TG_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")
LOOKBACK_MIN = int(os.environ.get("TRADER_LOOKBACK_MIN", "30"))
MAX_TRADES   = int(os.environ.get("TRADER_MAX_TRADES",   "3"))
IS_PAPER     = os.environ.get("KIS_IS_PAPER", "true").lower() != "false"

_DEFAULT_CFG = {
    "is_active":           False,
    "mode":                "paper",
    "sizing_method":       "fixed_fraction",
    "max_invest_per_trade": 500_000,
    "max_total_invest":    3_000_000,
    "max_positions":       5,
    "daily_loss_limit":    100_000,
    "min_prob":            0.45,
    "kelly_fraction":      0.25,
    "fixed_fraction_pct":  10.0,
    "auto_sell":           True,
}


def _send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = orjson.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            resp.read()
    except Exception as e:
        logger.warning(f"Telegram 전송 실패: {e}")


async def _load_settings(db: asyncpg.Pool) -> dict:
    row = await db.fetchrow("SELECT * FROM trader_settings WHERE id=1")
    return dict(row) if row else _DEFAULT_CFG


async def _get_available_cash(db: asyncpg.Pool, kc: KISOrderClient, cfg: dict) -> int:
    if cfg["mode"] == "paper":
        invested = await db.fetchval(
            "SELECT COALESCE(SUM(avg_price * qty), 0) FROM positions WHERE status='HOLDING' AND mode='paper'"
        )
        return max(0, cfg["max_total_invest"] - int(invested))
    bal = await kc.get_balance()
    return bal.deposit if bal.success else 0


async def _process_recommendation(
    db: asyncpg.Pool,
    redis: redis_lib.Redis,
    kc: KISOrderClient,
    guard: DailyLossGuard,
    rec: dict,
    cfg: dict,
) -> dict | None:
    """단일 추천 처리. 매수 체결 시 결과 dict, 스킵/실패 시 None."""
    code    = rec["code"]
    rec_id  = rec["id"]
    prob    = float(rec["success_prob"] or 0)
    price   = int(rec["entry_price"] or 0)
    target  = int(rec["target_price"] or 0) or None
    stop    = int(rec["stop_loss_price"] or 0) or None

    if prob < cfg["min_prob"]:
        logger.info(f"[{code}] SKIP — 확률 미달 ({prob:.2f} < {cfg['min_prob']:.2f})")
        return None

    if await guard.is_limit_hit():
        logger.info(f"[{code}] SKIP — 일일 손실 한도 초과")
        return None

    active_cnt = await db.fetchval(
        "SELECT COUNT(*) FROM positions WHERE status='HOLDING' AND mode=$1",
        cfg["mode"],
    )
    if active_cnt >= cfg["max_positions"]:
        logger.info(f"[{code}] SKIP — 최대 포지션 수 ({active_cnt}/{cfg['max_positions']})")
        return None

    exists = await db.fetchval(
        "SELECT 1 FROM positions WHERE code=$1 AND status='HOLDING' AND mode=$2",
        code, cfg["mode"],
    )
    if exists:
        logger.info(f"[{code}] SKIP — 이미 보유 중")
        return None

    available_cash = await _get_available_cash(db, kc, cfg)
    if available_cash <= 0:
        logger.info(f"[{code}] SKIP — 가용 현금 없음")
        return None

    qty = calc_qty(
        price=price,
        available_cash=available_cash,
        max_invest_per_trade=cfg["max_invest_per_trade"],
        sizing_method=cfg["sizing_method"],
        success_prob=prob,
        kelly_fraction=cfg["kelly_fraction"],
        total_capital=cfg["max_total_invest"],
        fixed_fraction_pct=cfg["fixed_fraction_pct"],
    )
    if qty <= 0:
        logger.info(f"[{code}] SKIP — 포지션 사이징 결과 0주 (price={price:,}, cash={available_cash:,})")
        return None

    # 주문 실행
    mode = cfg["mode"]
    if mode == "paper":
        order_no = f"PAPER-{datetime.now(_KST).strftime('%H%M%S%f')[:12]}"
        success  = True
        error_msg = None
    else:
        result    = await kc.place_buy_order(code, qty, price=0, order_type="MARKET")
        order_no  = result.order_no if result.success else None
        success   = result.success
        error_msg = result.error_msg if not result.success else None
        if not success:
            logger.error(f"[{code}] 매수 주문 실패: {error_msg}")

    order_id = await db.fetchval(
        """INSERT INTO orders
           (order_no, rec_id, code, side, order_type, order_price, order_qty,
            filled_qty, avg_filled_price, status, mode, error_msg)
           VALUES ($1,$2,$3,'BUY','MARKET',$4,$5,$5,$4,$6,$7,$8)
           RETURNING id""",
        order_no, rec_id, code, price, qty,
        "FILLED" if success else "FAILED", mode, error_msg,
    )

    if not success:
        return None

    name = await db.fetchval("SELECT name FROM stocks WHERE code=$1", code) or code
    await db.execute(
        """INSERT INTO positions
           (code, name, qty, avg_price, current_price,
            target_price, stop_loss_price, rec_id, entry_order_id, mode)
           VALUES ($1,$2,$3,$4,$4,$5,$6,$7,$8,$9)
           ON CONFLICT (code, status, mode) DO UPDATE
           SET qty=EXCLUDED.qty, avg_price=EXCLUDED.avg_price,
               target_price=EXCLUDED.target_price, stop_loss_price=EXCLUDED.stop_loss_price,
               updated_at=NOW()""",
        code, name, qty, price, target, stop, rec_id, order_id, mode,
    )

    today = datetime.now(_KST).date()
    await db.execute(
        """INSERT INTO daily_pnl (trade_date, mode, buy_amount, total_trades)
           VALUES ($1,$2,$3,1)
           ON CONFLICT (trade_date, mode) DO UPDATE SET
               buy_amount   = daily_pnl.buy_amount + EXCLUDED.buy_amount,
               total_trades = daily_pnl.total_trades + 1,
               updated_at   = NOW()""",
        today, mode, price * qty,
    )

    logger.info(f"[{code}] 매수 완료 — qty={qty}, price={price:,}원 ({mode})")
    return {"code": code, "name": name, "qty": qty, "price": price, "prob": prob, "mode": mode}


async def run(db: asyncpg.Pool, redis_client: redis_lib.Redis, kc: KISOrderClient) -> None:
    cfg = await _load_settings(db)

    if not cfg["is_active"]:
        logger.info("자동매매 비활성 상태 — 실행 스킵 (trader_settings.is_active=false)")
        return

    guard = DailyLossGuard(redis_client, cfg["daily_loss_limit"])
    since = datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MIN)

    # 미체결 BUY 추천 조회 (최근 LOOKBACK_MIN분, 확률 높은 순)
    recs = await db.fetch(
        """
        SELECT r.id, r.code, r.success_prob, r.entry_price,
               r.target_price, r.stop_loss_price
        FROM   recommendations r
        LEFT JOIN orders o ON o.rec_id = r.id AND o.side = 'BUY'
        WHERE  r.action = 'BUY'
          AND  r.created_at >= $1
          AND  o.id IS NULL
        ORDER BY r.success_prob DESC
        LIMIT  $2
        """,
        since, MAX_TRADES * 3,   # 여분을 가져와 skip 후에도 MAX_TRADES 채움
    )

    if not recs:
        logger.info(f"최근 {LOOKBACK_MIN}분 내 미처리 BUY 추천 없음")
        return

    logger.info(f"처리 대상 추천 {len(recs)}건")
    executed = []
    for rec in recs:
        if len(executed) >= MAX_TRADES:
            break
        result = await _process_recommendation(db, redis_client, kc, guard, dict(rec), cfg)
        if result:
            executed.append(result)

    if not executed:
        logger.info("실행된 매수 주문 없음")
        return

    # Telegram 알림
    if _TG_TOKEN and _TG_CHAT_ID:
        now_kst = datetime.now(timezone.utc) + timedelta(hours=9)
        mode_tag = "📄 모의" if cfg["mode"] == "paper" else "💰 실전"
        lines = [f"🤖 <b>[자동매매] {now_kst.strftime('%H:%M')} KST — {mode_tag}</b>", ""]
        for r in executed:
            lines.append(
                f"✅ <b>{r['code']}</b> {r['name']}"
                f"\n   {r['qty']}주 × {r['price']:,}원 = {r['qty']*r['price']:,}원"
                f" | 확률 {r['prob']:.2f}"
            )
        lines.append(f"\n총 {len(executed)}건 매수 체결")
        _send_telegram(_TG_TOKEN, _TG_CHAT_ID, "\n".join(lines))


async def main() -> None:
    dsn = os.environ.get("POSTGRES_DSN", "")
    if not dsn:
        logger.error("POSTGRES_DSN 환경변수 없음")
        sys.exit(1)
    dsn = dsn.replace("+asyncpg", "")
    ssl_val = "require" if "supabase" in dsn else False

    db = await asyncpg.create_pool(
        dsn=dsn, min_size=1, max_size=3,
        ssl=ssl_val, statement_cache_size=0,
    )
    redis_client = redis_lib.from_url(os.environ["REDIS_URL"])

    config = KISConfig(
        app_key=os.environ["KIS_APP_KEY"],
        app_secret=os.environ["KIS_APP_SECRET"],
        account_no=os.environ.get("KIS_ACCOUNT_NO", ""),
        is_paper=IS_PAPER,
    )
    auth = KISAuthManager(config, redis_client)
    kc   = KISOrderClient(config, auth)

    try:
        await run(db, redis_client, kc)
    finally:
        await db.close()
        await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
