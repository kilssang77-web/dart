import asyncio
import logging
import orjson
from aiokafka import AIOKafkaConsumer
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


class KafkaConsumerWrapper:

    def __init__(self, bootstrap_servers: str, group_id: str):
        self._servers  = bootstrap_servers
        self._group_id = group_id

    async def consume(
        self,
        topics: list[str],
        batch_size: int = 100,
        timeout_ms: int = 500,
    ) -> AsyncGenerator[list[dict], None]:
        consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self._servers,
            group_id=self._group_id,
            value_deserializer=lambda v: orjson.loads(v),
            auto_offset_reset="latest",
            enable_auto_commit=True,
            max_poll_records=batch_size,
            fetch_max_wait_ms=timeout_ms,
        )
        await consumer.start()
        logger.info(f"Kafka consumer started: {topics}")
        try:
            while True:
                result = await consumer.getmany(
                    timeout_ms=timeout_ms, max_records=batch_size
                )
                batch = [msg.value for msgs in result.values() for msg in msgs]
                if batch:
                    yield batch
                else:
                    await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass
        finally:
            await consumer.stop()
