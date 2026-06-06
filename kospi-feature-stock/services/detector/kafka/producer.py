import asyncio
import logging
import orjson
from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)


class KafkaProducerWrapper:

    def __init__(self, bootstrap_servers: str):
        self._servers  = bootstrap_servers
        self._producer: AIOKafkaProducer | None = None
        self._lock     = asyncio.Lock()

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
                acks="all",
                compression_type="gzip",
            )
            await p.start()
            self._producer = p  # start() 완료 후 할당 (race condition 방지)

    async def send(self, topic: str, value: dict, key: str = "") -> None:
        await self._ensure_started()
        await self._producer.send(topic, value=value, key=key or None)

    async def close(self):
        if self._producer:
            await self._producer.stop()
