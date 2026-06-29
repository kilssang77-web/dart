import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from telegram.sender import TelegramSender
from kafka.consumer import NotifierConsumer
from price_alert import PriceAlertMonitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("notifier")

_sender:       TelegramSender    | None = None
_task:         asyncio.Task      | None = None
_alert_task:   asyncio.Task      | None = None
_reconnect_task: asyncio.Task   | None = None


async def _try_create_db_pool():
    dsn = os.environ.get("POSTGRES_DSN", "")
    if not dsn:
        return None
    try:
        import asyncpg
        pool = await asyncpg.create_pool(
            dsn=dsn.replace("+asyncpg", ""), min_size=1, max_size=3
        )
        logger.info("DB pool created — telegram_logs 기록 활성화")
        return pool
    except Exception as e:
        logger.warning(f"DB pool 생성 실패 (로그 기록 비활성화): {e}")
        return None


async def _db_reconnect_loop(sender: TelegramSender, alert_monitor: PriceAlertMonitor):
    """DB pool 없을 때 30초마다 재연결 시도."""
    while True:
        await asyncio.sleep(30)
        if sender._db is None:
            pool = await _try_create_db_pool()
            if pool:
                sender.set_db_pool(pool)
                alert_monitor.set_db_pool(pool)
                logger.info("DB pool 재연결 성공 — telegram_logs 기록 및 가격 알림 재활성화")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _sender, _task, _alert_task, _reconnect_task
    db_pool  = await _try_create_db_pool()
    _sender  = TelegramSender(db_pool=db_pool)

    # 매수 신호·공시 Telegram 컨슈머
    consumer = NotifierConsumer(_sender)
    _task = asyncio.create_task(consumer.run())

    # 익절가/손절가 실시간 가격 알림 모니터
    alert_monitor = PriceAlertMonitor(_sender, db_pool)
    _alert_task = asyncio.create_task(alert_monitor.run())

    # DB pool 재연결 루프 (시작 시 실패한 경우 복구)
    _reconnect_task = asyncio.create_task(_db_reconnect_loop(_sender, alert_monitor))

    logger.info("Notifier service started (consumer + price alert monitor)")
    yield

    for t in [_task, _alert_task, _reconnect_task]:
        if t:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
    if _sender:
        await _sender.close()
    if _sender and _sender._db:
        await _sender._db.close()


app = FastAPI(title="notifier", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "notifier"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("NOTIFIER_PORT", "8003")))
