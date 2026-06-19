"""
실시간 가격 알림 모니터.
활성 추천(recommendations)의 현재가를 Redis에서 60초마다 확인하여
익절가 도달·손절가 접근·손절가 도달 시 Telegram 알림을 발송한다.

알림 상태는 Redis에 TTL 키로 관리하여 중복 발송을 방지한다.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta

import asyncpg
import orjson
import redis.asyncio as redis_lib

from telegram.sender import TelegramSender
from telegram.formatter import format_price_alert

logger = logging.getLogger("notifier.price_alert")

_KST = timezone(timedelta(hours=9))

# 환경 변수
_POLL_INTERVAL   = int(os.environ.get("PRICE_ALERT_INTERVAL_SEC",   "60"))
_STOP_WARN_PCT   = float(os.environ.get("PRICE_ALERT_STOP_WARN_PCT", "0.03"))  # 손절가 3% 이내
_TARGET_DEDUP_TTL = int(os.environ.get("PRICE_ALERT_TARGET_TTL",    "86400"))  # 익절 알림 24시간 중복 방지
_STOP_WARN_TTL   = int(os.environ.get("PRICE_ALERT_STOP_WARN_TTL",  "3600"))   # 경고 1시간 중복 방지
_STOP_HIT_TTL    = int(os.environ.get("PRICE_ALERT_STOP_HIT_TTL",   "86400"))  # 손절 알림 24시간 중복 방지

# 장 시간: 09:00~15:30 KST 만 동작 (야간 오알림 방지)
_MARKET_OPEN  = (9, 0)
_MARKET_CLOSE = (15, 30)


def _is_market_hours() -> bool:
    now = datetime.now(_KST)
    if now.weekday() >= 5:  # 주말
        return False
    t = (now.hour, now.minute)
    return _MARKET_OPEN <= t <= _MARKET_CLOSE


class PriceAlertMonitor:
    """
    활성 추천 건별로 익절/손절 조건 모니터링 및 Telegram 알림.
    """

    def __init__(self, sender: TelegramSender, db_pool: asyncpg.Pool | None):
        self._sender  = sender
        self._db      = db_pool
        self._redis: redis_lib.Redis | None = None

    async def run(self):
        if self._db is None:
            logger.warning("[PriceAlert] DB pool 없음 — 가격 알림 비활성화")
            return

        self._redis = redis_lib.from_url(os.environ["REDIS_URL"])
        logger.info("[PriceAlert] 가격 알림 모니터 시작")

        while True:
            try:
                if _is_market_hours():
                    await self._check_all_active()
                else:
                    logger.debug("[PriceAlert] 장외 시간 — 스킵")
            except Exception as e:
                logger.error(f"[PriceAlert] check error: {e}")
            await asyncio.sleep(_POLL_INTERVAL)

    async def _check_all_active(self):
        """활성 추천 전체 조회 후 각 건 가격 조건 확인."""
        try:
            rows = await self._db.fetch(
                """
                SELECT
                    r.id, r.code, s.name,
                    r.entry_price, r.target_price, r.stop_loss_price,
                    r.created_at
                FROM recommendations r
                JOIN stocks s ON s.code = r.code
                LEFT JOIN recommendation_performance rp ON rp.rec_id = r.id
                WHERE r.action = 'BUY'
                  AND r.created_at >= NOW() - INTERVAL '10 days'
                  AND (rp.tracking_complete IS NULL OR rp.tracking_complete = FALSE)
                  AND EXISTS (
                      SELECT 1 FROM telegram_logs tl
                      WHERE tl.code = r.code
                        AND tl.msg_type = 'signal'
                        AND tl.success = TRUE
                        AND tl.sent_at BETWEEN r.created_at - INTERVAL '5 minutes'
                                            AND r.created_at + INTERVAL '30 minutes'
                  )
                ORDER BY r.created_at DESC
                LIMIT 200
                """
            )
        except Exception as e:
            logger.error(f"[PriceAlert] DB query error: {e}")
            return

        for row in rows:
            rec_id  = row["id"]
            code    = row["code"]
            name    = row["name"] or code
            entry   = int(row["entry_price"] or 0)
            target  = int(row["target_price"] or 0)
            stop    = int(row["stop_loss_price"] or 0)

            if not entry or not target or not stop:
                continue

            # Redis에서 실시간 현재가 조회 (키 형식: stats:{code}:last_price)
            price_raw = await self._redis.get(f"stats:{code}:last_price")
            if not price_raw:
                continue
            current = int(float(price_raw))

            hold_days = max(0, (datetime.now(_KST) - row["created_at"].astimezone(_KST)).days)

            await self._evaluate(rec_id, code, name, entry, target, stop, current, hold_days)

    async def _evaluate(
        self,
        rec_id: int,
        code: str,
        name: str,
        entry: int,
        target: int,
        stop: int,
        current: int,
        hold_days: int,
    ):
        payload = {
            "code": code, "name": name,
            "entry_price": entry, "target_price": target,
            "stop_loss_price": stop, "current_price": current,
            "hold_days": hold_days,
        }

        # ① 익절가 도달
        if current >= target:
            key = f"alert:target:{rec_id}"
            if not await self._redis.exists(key):
                await self._send(payload, "target_hit")
                await self._redis.set(key, "1", ex=_TARGET_DEDUP_TTL)
            return

        # ② 손절가 도달
        if current <= stop:
            key = f"alert:stop_hit:{rec_id}"
            if not await self._redis.exists(key):
                await self._send(payload, "stop_hit")
                await self._redis.set(key, "1", ex=_STOP_HIT_TTL)
            return

        # ③ 손절가 _STOP_WARN_PCT 이내 접근 (손절가 대비 거리)
        if stop > 0:
            dist = (current - stop) / stop
            if 0 < dist < _STOP_WARN_PCT:
                key = f"alert:stop_warn:{rec_id}"
                if not await self._redis.exists(key):
                    await self._send(payload, "stop_approach")
                    await self._redis.set(key, "1", ex=_STOP_WARN_TTL)

    async def _send(self, payload: dict, alert_type: str):
        payload["alert_type"] = alert_type
        text = format_price_alert(payload)
        code = payload.get("code", "")
        name = payload.get("name", code)

        _label = {"target_hit": "익절가 도달", "stop_approach": "손절가 접근", "stop_hit": "손절가 도달"}
        logger.info(f"[PriceAlert] {_label.get(alert_type, alert_type)}: {name}({code}) "
                    f"현재가={payload.get('current_price')}")

        await self._sender.send_message(
            text,
            msg_type=f"price_alert_{alert_type}",
            code=code,
            name=name,
            title=f"{name} {_label.get(alert_type, alert_type)}",
        )
