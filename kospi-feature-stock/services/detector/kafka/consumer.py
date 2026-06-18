import asyncio
import logging
import orjson
import redis.asyncio as redis_lib
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


class KafkaConsumerWrapper:
    """Redis Pub/Sub 기반 배치 컨슈머 — Kafka 인터페이스 호환."""

    def __init__(self, redis: redis_lib.Redis, group_id: str = ""):
        self._redis = redis

    async def consume(
        self,
        topics: list[str],
        batch_size: int = 100,
        timeout_ms: int = 500,
    ) -> AsyncGenerator[list[dict], None]:
        pubsub = self._redis.pubsub()
        channels = [f"ch:{t}" for t in topics]
        await pubsub.subscribe(*channels)
        logger.info(f"Redis subscriber started: {channels}")
        try:
            while True:
                batch: list[dict] = []
                end = asyncio.get_event_loop().time() + timeout_ms / 1000
                while len(batch) < batch_size:
                    remaining = end - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        break
                    msg = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=min(remaining, 0.1),
                    )
                    if msg is None:
                        break
                    if msg.get("type") == "message":
                        try:
                            batch.append(orjson.loads(msg["data"]))
                        except Exception:
                            pass
                if batch:
                    yield batch
                else:
                    await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass
        finally:
            try:
                await pubsub.unsubscribe()
                await pubsub.aclose()
            except Exception:
                pass
