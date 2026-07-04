"""
자동 매매 실행기
- Redis Pub/Sub ch:recommendation 구독
- BUY 신호 수신 → 조건 검증 → 포지션 사이징 → 주문 실행 → DB 기록
- 보유 포지션 목표가/손절가 모니터링 (paper 모드: Redis 가격 기준, live: KIS 잔고 기준)
"""
import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta

import asyncpg
import orjson
import redis.asyncio as redis_lib

from kis.order_client import KISOrderClient, KISAuthManager, KISConfig
from risk.position_sizer import calc_qty, describe
from risk.daily_loss_guard import DailyLossGuard

logger = logging.getLogger("auto_executor")

_KST = timezone(timedelta(hours=9))
_CHANNEL = "ch:recommendation"
_PRICE_KEY_TPL = "price:{code}"   # collector가 최신 체결가 저장하는 키


class AutoExecutor:

    def __init__(
        self,
        db: asyncpg.Pool,
        redis_client: redis_lib.Redis,
        order_client: KISOrderClient,
        loss_guard: DailyLossGuard,
    ):
        self.db = db
        self.redis = redis_client
        self.kc = order_client
        self.guard = loss_guard
        self._running = False

    # ── 외부 진입점 ───────────────────────────────────────────────────────────
    async def run(self) -> None:
        self._running = True
        tasks = [
            asyncio.create_task(self._subscribe_loop(), name="subscribe"),
            asyncio.create_task(self._position_monitor_loop(), name="pos_monitor"),
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for t in tasks:
                t.cancel()

    def stop(self) -> None:
        self._running = False

    # ── Redis Pub/Sub 구독 루프 ───────────────────────────────────────────────
    async def _subscribe_loop(self) -> None:
        backoff = 1
        while self._running:
            try:
                pubsub = self.redis.pubsub()
                await pubsub.subscribe(_CHANNEL)
                logger.info(f"Redis Pub/Sub 구독 시작: {_CHANNEL}")
                backoff = 1
                async for msg in pubsub.listen():
                    if not self._running:
                        break
                    if msg.get("type") != "message":
                        continue
                    try:
                        data = orjson.loads(msg["data"])
                        await self._handle_signal(data)
                    except Exception as e:
                        logger.error(f"신호 처리 오류: {e}")
            except Exception as e:
                logger.error(f"Pub/Sub 연결 오류 ({backoff}s 후 재시도): {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    # ── BUY 신호 처리 ─────────────────────────────────────────────────────────
    async def _handle_signal(self, signal: dict) -> None:
        action = signal.get("action", "")
        if action != "BUY":
            return

        code    = signal.get("code", "")
        rec_id  = signal.get("rec_id") or signal.get("id")
        prob    = float(signal.get("success_prob", 0))
        price   = int(signal.get("entry_price", 0))
        target  = int(signal.get("target_price", 0))
        stop    = int(signal.get("stop_loss_price", 0))

        logger.info(f"[{code}] BUY 신호 수신 — rec_id={rec_id}, prob={prob:.2f}, price={price:,}")

        # 1. 설정 로드
        cfg = await self._load_settings()
        if not cfg["is_active"]:
            logger.debug(f"[{code}] 자동매매 비활성 — SKIP")
            return

        # 2. 최소 확률 검증
        if prob < cfg["min_prob"]:
            await self._log_skip(rec_id, code, f"확률 미달 ({prob:.2f} < {cfg['min_prob']:.2f})")
            return

        # 3. 일일 손실 한도 확인
        if await self.guard.is_limit_hit():
            await self._log_skip(rec_id, code, "일일 손실 한도 초과")
            return

        # 4. 동시 포지션 수 확인
        active_cnt = await self.db.fetchval(
            "SELECT COUNT(*) FROM positions WHERE status='HOLDING' AND mode=$1",
            cfg["mode"],
        )
        if active_cnt >= cfg["max_positions"]:
            await self._log_skip(rec_id, code, f"최대 포지션 수 초과 ({active_cnt}/{cfg['max_positions']})")
            return

        # 5. 중복 포지션 확인 (이미 보유 중인 종목)
        exists = await self.db.fetchval(
            "SELECT 1 FROM positions WHERE code=$1 AND status='HOLDING' AND mode=$2",
            code, cfg["mode"],
        )
        if exists:
            await self._log_skip(rec_id, code, "이미 보유 중인 종목")
            return

        # 6. 잔고/가용 현금 조회
        available_cash = await self._get_available_cash(cfg)
        if available_cash <= 0:
            await self._log_skip(rec_id, code, "가용 현금 없음")
            return

        # 7. 포지션 사이징
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
            await self._log_skip(rec_id, code, "포지션 사이징 결과 0주")
            return

        size_info = describe(price, qty, prob, cfg["sizing_method"], cfg["max_invest_per_trade"])
        logger.info(f"[{code}] 사이징: {size_info}")

        # 8. 주문 실행
        await self._execute_buy(
            code=code, qty=qty, price=price,
            target=target, stop=stop,
            rec_id=rec_id, cfg=cfg, size_info=size_info,
        )

    # ── 매수 주문 실행 ────────────────────────────────────────────────────────
    async def _execute_buy(
        self, code: str, qty: int, price: int,
        target: int, stop: int,
        rec_id, cfg: dict, size_info: dict,
    ) -> None:
        mode = cfg["mode"]

        if mode == "paper":
            result_order_no = f"PAPER-{datetime.now(_KST).strftime('%H%M%S%f')[:12]}"
            success = True
            error_msg = None
        else:
            result = await self.kc.place_buy_order(code, qty, price=0, order_type="MARKET")
            result_order_no = result.order_no if result.success else None
            success = result.success
            error_msg = result.error_msg if not result.success else None
            if not success:
                logger.error(f"[{code}] 매수 주문 실패: {error_msg}")

        # DB 주문 기록
        order_id = await self.db.fetchval(
            """INSERT INTO orders
               (order_no, rec_id, code, side, order_type, order_price, order_qty,
                filled_qty, avg_filled_price, status, mode, error_msg)
               VALUES ($1,$2,$3,'BUY','MARKET',$4,$5,$5,$4,$6,$7,$8)
               RETURNING id""",
            result_order_no, rec_id, code, price, qty,
            "FILLED" if success else "FAILED", mode, error_msg,
        )

        if not success:
            return

        # 포지션 기록
        name = await self.db.fetchval("SELECT name FROM stocks WHERE code=$1", code)
        await self.db.execute(
            """INSERT INTO positions
               (code, name, qty, avg_price, current_price, target_price, stop_loss_price,
                rec_id, entry_order_id, mode)
               VALUES ($1,$2,$3,$4,$4,$5,$6,$7,$8,$9)
               ON CONFLICT (code, status, mode) DO UPDATE
               SET qty=EXCLUDED.qty, avg_price=EXCLUDED.avg_price,
                   target_price=EXCLUDED.target_price, stop_loss_price=EXCLUDED.stop_loss_price,
                   updated_at=NOW()""",
            code, name, qty, price, target or None, stop or None,
            rec_id, order_id, mode,
        )

        # 일일 매수금액 기록
        await self._upsert_daily_pnl(mode, buy_amount=price * qty)
        logger.info(f"[{code}] 매수 완료 — qty={qty}, price={price:,}, order_id={order_id}")

    # ── 포지션 모니터링 루프 (30초 간격) ─────────────────────────────────────
    async def _position_monitor_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(30)
                cfg = await self._load_settings()
                if not cfg["is_active"] or not cfg["auto_sell"]:
                    continue
                await self._check_positions(cfg)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"포지션 모니터링 오류: {e}")

    async def _check_positions(self, cfg: dict) -> None:
        positions = await self.db.fetch(
            "SELECT * FROM positions WHERE status='HOLDING' AND mode=$1",
            cfg["mode"],
        )
        for pos in positions:
            code = pos["code"]
            # 현재가 조회 (Redis)
            cur_price = await self._get_current_price(code)
            if not cur_price:
                continue

            # current_price 업데이트
            await self.db.execute(
                "UPDATE positions SET current_price=$1, updated_at=NOW() WHERE id=$2",
                cur_price, pos["id"],
            )

            target = pos["target_price"]
            stop   = pos["stop_loss_price"]

            if target and cur_price >= target:
                logger.info(f"[{code}] 목표가 도달 ({cur_price:,} >= {target:,}) → 매도")
                await self._execute_sell(pos, cur_price, cfg, "TARGET_HIT")
            elif stop and cur_price <= stop:
                logger.info(f"[{code}] 손절가 도달 ({cur_price:,} <= {stop:,}) → 매도")
                await self._execute_sell(pos, cur_price, cfg, "STOP_HIT")

    # ── 매도 주문 실행 ────────────────────────────────────────────────────────
    async def _execute_sell(self, pos, sell_price: int, cfg: dict, reason: str) -> None:
        code = pos["code"]
        qty  = pos["qty"]
        mode = cfg["mode"]

        if mode == "paper":
            result_order_no = f"PAPER-SELL-{datetime.now(_KST).strftime('%H%M%S%f')[:12]}"
            success = True
            error_msg = None
        else:
            result = await self.kc.place_sell_order(code, qty, price=0, order_type="MARKET")
            result_order_no = result.order_no if result.success else None
            success = result.success
            error_msg = result.error_msg if not result.success else None

        order_id = await self.db.fetchval(
            """INSERT INTO orders
               (order_no, rec_id, code, side, order_type, order_price, order_qty,
                filled_qty, avg_filled_price, status, mode, error_msg)
               VALUES ($1,$2,$3,'SELL','MARKET',$4,$5,$5,$4,$6,$7,$8)
               RETURNING id""",
            result_order_no, pos["rec_id"], code, sell_price, qty,
            "FILLED" if success else "FAILED", mode, error_msg,
        )

        if not success:
            return

        avg_price = float(pos["avg_price"])
        pnl_pct   = round((sell_price - avg_price) / avg_price * 100, 2)
        pnl_amount = int((sell_price - avg_price) * qty)

        await self.db.execute(
            """UPDATE positions SET
               status='CLOSED', close_reason=$1, exit_order_id=$2,
               closed_at=NOW(), closed_price=$3, pnl_pct=$4, pnl_amount=$5, updated_at=NOW()
               WHERE id=$6""",
            reason, order_id, sell_price, pnl_pct, pnl_amount, pos["id"],
        )

        # 일일 손익 기록
        await self._upsert_daily_pnl(
            mode,
            realized_pnl=pnl_amount,
            sell_amount=sell_price * qty,
            win=(pnl_amount > 0),
        )

        # 손실 가드 갱신
        if pnl_amount < 0:
            await self.guard.record_loss(pnl_amount)

        logger.info(f"[{code}] 매도 완료 — reason={reason}, pnl={pnl_pct:+.2f}% ({pnl_amount:+,}원)")

    # ── 헬퍼 ─────────────────────────────────────────────────────────────────
    async def _load_settings(self) -> dict:
        row = await self.db.fetchrow("SELECT * FROM trader_settings WHERE id=1")
        if row:
            return dict(row)
        return {
            "is_active": False, "mode": "paper",
            "sizing_method": "fixed_fraction",
            "max_invest_per_trade": 500_000,
            "max_total_invest": 3_000_000,
            "max_positions": 5,
            "daily_loss_limit": 100_000,
            "min_prob": 0.45,
            "kelly_fraction": 0.25,
            "fixed_fraction_pct": 10.0,
            "auto_sell": True,
        }

    async def _get_available_cash(self, cfg: dict) -> int:
        if cfg["mode"] == "paper":
            # paper 모드: 최대 투자금 - 현재 투입금
            invested = await self.db.fetchval(
                "SELECT COALESCE(SUM(avg_price * qty), 0) FROM positions WHERE status='HOLDING' AND mode='paper'"
            )
            return max(0, cfg["max_total_invest"] - int(invested))
        else:
            bal = await self.kc.get_balance()
            return bal.deposit if bal.success else 0

    async def _get_current_price(self, code: str) -> int:
        val = await self.redis.get(f"price:{code}")
        if val:
            return int(val)
        # daily_bars 최신가 fallback
        row = await self.db.fetchrow(
            "SELECT close FROM daily_bars WHERE code=$1 ORDER BY date DESC LIMIT 1", code
        )
        return int(row["close"]) if row else 0

    async def _log_skip(self, rec_id, code: str, reason: str) -> None:
        logger.info(f"[{code}] SKIP — {reason}")

    async def _upsert_daily_pnl(
        self, mode: str,
        realized_pnl: int = 0,
        buy_amount: int = 0,
        sell_amount: int = 0,
        win: bool = False,
    ) -> None:
        today = datetime.now(_KST).date()
        await self.db.execute(
            """INSERT INTO daily_pnl (trade_date, mode, realized_pnl, buy_amount, sell_amount,
                   total_trades, win_trades, loss_trades)
               VALUES ($1, $2, $3, $4, $5,
                   CASE WHEN $5>0 OR $4>0 THEN 1 ELSE 0 END,
                   CASE WHEN $6 THEN 1 ELSE 0 END,
                   CASE WHEN NOT $6 AND ($5>0) THEN 1 ELSE 0 END)
               ON CONFLICT (trade_date, mode) DO UPDATE SET
                   realized_pnl  = daily_pnl.realized_pnl + EXCLUDED.realized_pnl,
                   buy_amount    = daily_pnl.buy_amount   + EXCLUDED.buy_amount,
                   sell_amount   = daily_pnl.sell_amount  + EXCLUDED.sell_amount,
                   total_trades  = daily_pnl.total_trades + EXCLUDED.total_trades,
                   win_trades    = daily_pnl.win_trades   + EXCLUDED.win_trades,
                   loss_trades   = daily_pnl.loss_trades  + EXCLUDED.loss_trades,
                   updated_at    = NOW()""",
            today, mode, realized_pnl, buy_amount, sell_amount, win,
        )
