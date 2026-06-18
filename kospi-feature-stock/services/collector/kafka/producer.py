import asyncio
import logging
import orjson
import redis.asyncio as redis_lib

logger = logging.getLogger(__name__)


class KafkaProducerWrapper:
    """Redis Pub/Sub 기반 이벤트 버스 — Kafka 인터페이스 호환."""

    def __init__(self, redis: redis_lib.Redis):
        self._redis = redis

    async def send(self, topic: str, value: dict, key: str = "") -> None:
        try:
            await self._redis.publish(f"ch:{topic}", orjson.dumps(value).decode())
        except Exception as e:
            logger.error(f"Redis publish failed topic={topic} key={key}: {e}")
            raise

    async def send_batch(self, topic: str, items: list[dict], key_field: str = "code") -> None:
        tasks = [self.send(topic, item, item.get(key_field, "")) for item in items]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = [r for r in results if isinstance(r, Exception)]
        if errors:
            logger.error(f"Batch send errors ({len(errors)}/{len(items)}): {errors[0]}")

    async def close(self):
        pass
