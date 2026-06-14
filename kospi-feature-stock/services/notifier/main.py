import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from telegram.sender import TelegramSender
from kafka.consumer import NotifierConsumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("notifier")

_sender: TelegramSender | None = None
_task:   asyncio.Task     | None = None


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _sender, _task
    db_pool  = await _try_create_db_pool()
    _sender  = TelegramSender(db_pool=db_pool)
    consumer = NotifierConsumer(_sender)
    _task = asyncio.create_task(consumer.run())
    logger.info("Notifier service started")
    yield
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    if _sender:
        await _sender.close()
    if db_pool:
        await db_pool.close()


app = FastAPI(title="notifier", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "notifier"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("NOTIFIER_PORT", "8003")))
