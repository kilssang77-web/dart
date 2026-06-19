import asyncio
import logging
import orjson
import redis.asyncio as redis_lib

logger = logging.getLogger(__name__)


class RedisEventBus:
    """Redis Pub/Sub 기반 이벤트 버스."""

    def __init__(self, redis: redis_lib.Redis):
        self._redis = redis

    async def send(self, topic: str, value: dict, key: str = "") -> None:
        try:
            await self._redis.publish(f"ch:{topic}", orjson.dumps(value).decode())
        except Exception as e:
            logger.error(f"Redis publish failed topic={topic} key={key}: {e}")
            raise

    async def close(self):
        pass


# backward compatibility alias
KafkaProducerWrapper = RedisEventBus
