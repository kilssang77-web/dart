import asyncio
import logging
import orjson
from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)


class KafkaProducerWrapper:

    def __init__(self, bootstrap_servers: str):
        self._servers = bootstrap_servers
        self._producer: AIOKafkaProducer | None = None
        self._lock = asyncio.Lock()

    async def _ensure_started(self):
        if self._producer:
            return
        async with self._lock:
            if self._producer:
                return
            p = AIOKafkaProducer(
                bootstrap_servers=self._servers,
                value_serializer=lambda v: orjson.dumps(v),
                key_serializer=lambda k: k.encode() if k else None,
                compression_type="gzip",
                acks="all",
                max_batch_size=65536,
                linger_ms=5,
                request_timeout_ms=30000,
                retry_backoff_ms=500,
            )
            await p.start()
            self._producer = p   # start() 완료 후 할당 (race condition 방지)
            logger.info(f"Kafka producer started: {self._servers}")

    async def send(self, topic: str, value: dict, key: str = "") -> None:
        await self._ensure_started()
        try:
            await self._producer.send(topic, value=value, key=key or None)
        except Exception as e:
            logger.error(f"Kafka send failed topic={topic} key={key}: {e}")
            raise

    async def send_batch(self, topic: str, items: list[dict], key_field: str = "code") -> None:
        await self._ensure_started()
        tasks = [
            self.send(topic, item, item.get(key_field, ""))
            for item in items
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = [r for r in results if isinstance(r, Exception)]
        if errors:
            logger.error(f"Batch send errors ({len(errors)}/{len(items)}): {errors[0]}")

    async def close(self):
        if self._producer:
            await self._producer.stop()
            self._producer = None
