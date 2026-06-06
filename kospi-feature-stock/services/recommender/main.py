import asyncio
import logging
import os
import traceback
import orjson
import asyncpg
import redis.asyncio as redis_lib
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from datetime import datetime, timedelta, timezone
from pattern_vector import update_pattern_vector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("recommender")

# 기동 시 재처리할 최대 과거 범위 (기본 24시간)
_RECOVERY_HOURS = int(os.environ.get("REC_RECOVERY_HOURS", "24"))


class RecommenderService:

    def __init__(self):
        self._db: asyncpg.Pool | None = None
        self._redis: redis_lib.Redis | None = None

    async def setup(self):
        self._db = await asyncpg.create_pool(
            dsn=os.environ["POSTGRES_DSN"].replace("+asyncpg", ""),
            min_size=3,
            max_size=10,
        )
        self._redis = redis_lib.from_url(os.environ["REDIS_URL"])

    async def run(self):
        await self.setup()
        from entry_recommender import EntryRecommender
        recommender = EntryRecommender()

        producer = AIOKafkaProducer(
            bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            value_serializer=lambda v: orjson.dumps(v),
            key_serializer=lambda k: k.encode() if k else None,
        )
        await producer.start()

        # 기동 시 미처리 이벤트 복구 (Kafka 재시작으로 놓친 신호 처리)
        await self._recover_missed_events(recommender, producer)

        consumer = AIOKafkaConsumer(
            "feature-detected",
            bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            group_id="recommender-group",
            value_deserializer=lambda v: orjson.loads(v),
            auto_offset_reset="latest",
        )
        await consumer.start()
        logger.info("Recommender service started")

        try:
            async for msg in consumer:
                event = msg.value
                if not event or not event.get("code"):
                    continue
                try:
                    event_id = await self._save_feature_event(event)
                    rec = await self._generate(event, recommender)
                    if rec:
                        await self._emit(rec, event, producer, feature_event_id=event_id)
                except Exception as e:
                    logger.error(f"Recommend error {event.get('code')}: {e}")
        finally:
            await consumer.stop()
            await producer.stop()

    async def _recover_missed_events(self, recommender, producer):
        """
        기동 시 추천이 없는 feature_events를 재처리한다.
        recommender-group이 latest 오프셋을 사용하므로, 재시작 중 놓친
        이벤트를 DB에서 직접 조회해 추천을 생성한다.
        """
        since = datetime.now(timezone.utc) - timedelta(hours=_RECOVERY_HOURS)
        async with self._db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT fe.id, fe.code, fe.detected_at::TEXT AS detected_at,
                       fe.event_type, fe.price, fe.change_rate,
                       fe.volume, fe.volume_ratio, fe.amount,
                       fe.signal_score, fe.risk_score, fe.signal_data
                FROM feature_events fe
                WHERE fe.detected_at >= $1
                  AND NOT EXISTS (
                      SELECT 1 FROM recommendations r
                      WHERE r.feature_event_id = fe.id
                  )
                ORDER BY fe.detected_at ASC
                LIMIT 500
                """,
                since,
            )

        if not rows:
            logger.info("Recovery: no missed events found")
            return

        logger.info(f"Recovery: processing {len(rows)} missed events")
        processed = 0
        for row in rows:
            try:
                def _f(v, default=0.0):
                    return float(v) if v is not None else default

                event = {
                    "code":         row["code"],
                    "detected_at":  row["detected_at"],
                    "event_type":   row["event_type"],
                    "price":        int(row["price"]) if row["price"] else 0,
                    "change_rate":  _f(row["change_rate"]),
                    "volume":       int(row["volume"]) if row["volume"] else None,
                    "volume_ratio": _f(row["volume_ratio"], None),
                    "amount":       int(row["amount"]) if row["amount"] else None,
                    "signal_score": _f(row["signal_score"], 0.5),
                    "risk_score":   _f(row["risk_score"], 0.3),
                    "signal_data":  orjson.loads(row["signal_data"]) if row["signal_data"] else {},
                }
                rec = await self._generate(event, recommender)
                if rec:
                    await self._emit(rec, event, producer, feature_event_id=row["id"])
                    processed += 1
                asyncio.create_task(update_pattern_vector(self._db, row["id"], row["code"]))
            except Exception as e:
                logger.error(f"Recovery error {row['code']}: {e}\n{traceback.format_exc()}")

        logger.info(f"Recovery: completed {processed}/{len(rows)} events")

    async def _emit(self, rec: dict, event: dict, producer, feature_event_id: int | None = None):
        await producer.send("recommendation", value=rec, key=rec["code"])
        await self._save(rec, feature_event_id=feature_event_id)
        await self._publish_redis(rec)
        await self._redis.publish("channel:features", orjson.dumps(event).decode())

        if rec["action"] == "BUY":
            await producer.send(
                "signal-generated",
                value={
                    "code":            rec["code"],
                    "created_at":      rec["created_at"],
                    "action":          rec["action"],
                    "entry_price":     rec["entry_price"],
                    "target_price":    rec["target_price"],
                    "stop_loss_price": rec["stop_loss_price"],
                    "success_prob":    rec["success_prob"],
                    "risk_score":      rec["risk_score"],
                },
                key=rec["code"],
            )
            logger.info(
                f"[BUY] {rec['code']} entry={rec['entry_price']} "
                f"target={rec['target_price']} prob={rec['success_prob']:.2f}"
            )

    async def _generate(self, event: dict, recommender) -> dict | None:
        from ml_client import get_ml_result, get_similar_cases
        ml_result    = await get_ml_result(event, self._db)
        cases, stats = await get_similar_cases(event, self._db)
        rec = recommender.recommend(event, ml_result, stats, cases)

        return {
            "code":               rec.code,
            "created_at":         datetime.now(timezone.utc),
            "action":             rec.action,
            "entry_price":        rec.entry_price,
            "entry_price_low":    rec.entry_price_low,
            "entry_price_high":   rec.entry_price_high,
            "target_price":       rec.target_price,
            "stop_loss_price":    rec.stop_loss_price,
            "expected_hold_days": rec.expected_hold_days,
            "success_prob":       rec.success_prob,
            "expected_return":    rec.expected_return,
            "risk_score":         rec.risk_score,
            "risk_reward_ratio":  rec.risk_reward_ratio,
            "rationale":          rec.rationale,
            "similar_cases":      rec.similar_cases,
        }

    async def _save_feature_event(self, event: dict) -> int | None:
        code = event.get("code", "")
        if not code:
            return None
        signal_data = event.get("signal_data") or {}
        try:
            async with self._db.acquire() as conn:
                event_id = await conn.fetchval(
                    """
                    INSERT INTO feature_events (
                        code, detected_at, event_type, price, change_rate,
                        volume, volume_ratio, amount, signal_score, risk_score,
                        signal_data
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                    RETURNING id
                    """,
                    code,
                    datetime.fromisoformat(event.get("detected_at", datetime.now().isoformat())),
                    event.get("event_type", "UNKNOWN"),
                    int(event.get("price", 0)),
                    float(event.get("change_rate", 0)),
                    int(event.get("volume", 0)) if event.get("volume") else None,
                    float(event.get("volume_ratio", 0)) if event.get("volume_ratio") else None,
                    int(event.get("amount", 0)) if event.get("amount") else None,
                    float(event.get("signal_score", 0.5)),
                    float(event.get("risk_score", 0.3)),
                    orjson.dumps(signal_data).decode() if signal_data else None,
                )
            logger.info(f"Feature event saved: {code} {event.get('event_type')} (id={event_id})")

            if event_id:
                asyncio.create_task(update_pattern_vector(self._db, event_id, code))

            return event_id
        except Exception as e:
            logger.error(f"Feature event save error {code}: {e}")
            return None

    async def _save(self, rec: dict, feature_event_id: int | None = None):
        async with self._db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO recommendations (
                    code, created_at, action,
                    entry_price, entry_price_low, entry_price_high,
                    target_price, stop_loss_price, expected_hold_days,
                    success_prob, expected_return, risk_score,
                    risk_reward_ratio, rationale, similar_cases,
                    expired_at, feature_event_id
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,
                    NOW() + ($16 * INTERVAL '1 day'), $17)
                ON CONFLICT DO NOTHING
                """,
                rec["code"], rec["created_at"], rec["action"],
                rec["entry_price"], rec["entry_price_low"], rec["entry_price_high"],
                rec["target_price"], rec["stop_loss_price"], rec["expected_hold_days"],
                rec["success_prob"], rec["expected_return"], rec["risk_score"],
                rec["risk_reward_ratio"],
                orjson.dumps(rec["rationale"]).decode(),
                orjson.dumps(rec["similar_cases"]).decode(),
                float(rec["expected_hold_days"]),
                feature_event_id,
            )

    async def _publish_redis(self, rec: dict):
        await self._redis.publish(
            "channel:recommendations",
            orjson.dumps(rec).decode(),
        )


if __name__ == "__main__":
    asyncio.run(RecommenderService().run())
