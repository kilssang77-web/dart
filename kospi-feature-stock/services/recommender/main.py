import asyncio
import logging
import os
import traceback
import orjson
import asyncpg
import redis.asyncio as redis_lib
from datetime import datetime, timedelta, timezone
from pattern_vector import update_pattern_vector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("recommender")

# 기동 시 재처리할 최대 과거 범위 (기본 24시간)
_RECOVERY_HOURS   = int(os.environ.get("REC_RECOVERY_HOURS",   "24"))
# 동일 종목 재추천 억제 쿨다운 (분, 0=비활성) — 이벤트 타입과 무관하게 종목 단위로 적용
_COOLDOWN_MINUTES = int(os.environ.get("REC_COOLDOWN_MINUTES", "60"))
# 당일 세션 진입가 앵커 유효 시간 (시간)
_ANCHOR_HOURS     = int(os.environ.get("REC_ANCHOR_HOURS",     "8"))
# 앵커 가격과 현재가 허용 괴리율 (초과 시 앵커 무시)
_ANCHOR_BAND      = float(os.environ.get("REC_ANCHOR_BAND",    "0.03"))


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

        # 기동 시 미처리 이벤트 복구
        await self._recover_missed_events(recommender)

        pubsub = self._redis.pubsub()
        await pubsub.subscribe("ch:feature-detected")
        logger.info("Recommender service started")

        try:
            async for msg in pubsub.listen():
                if msg["type"] != "message":
                    continue
                event = orjson.loads(msg["data"])
                if not event or not event.get("code"):
                    continue
                try:
                    event_id = await self._save_feature_event(event)
                    if await self._on_cooldown(event.get("code", "")):
                        logger.debug(f"Cooldown skip: {event.get('code')} {event.get('event_type')}")
                        continue
                    rec = await self._generate(event, recommender)
                    if rec:
                        await self._emit(rec, event, feature_event_id=event_id)
                except Exception as e:
                    logger.error(f"Recommend error {event.get('code')}: {e}")
        finally:
            try:
                await pubsub.unsubscribe()
                await pubsub.aclose()
            except Exception:
                pass

    async def _recover_missed_events(self, recommender):
        """기동 시 추천이 없는 feature_events를 재처리한다."""
        since = datetime.now(timezone.utc) - timedelta(hours=_RECOVERY_HOURS)
        async with self._db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT fe.id, fe.code, fe.detected_at::TEXT AS detected_at,
                       fe.event_type, fe.price, fe.change_rate,
                       fe.volume, fe.volume_ratio, fe.amount,
                       fe.signal_score, fe.risk_score, fe.signal_data
                FROM feature_events fe
                LEFT JOIN recommendations r ON r.feature_event_id = fe.id
                WHERE fe.detected_at >= $1
                  AND r.id IS NULL
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
                # 복구 시에도 종목 단위 쿨다운 적용 (동일 종목 이벤트 중 최초 1건만 추천)
                if await self._on_cooldown(row["code"]):
                    logger.debug(f"Recovery cooldown skip: {row['code']} {row['event_type']}")
                    continue

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
                rec = await self._generate(event, recommender, use_anchor=False)
                if rec:
                    await self._emit(rec, event, feature_event_id=row["id"])
                    processed += 1
                await update_pattern_vector(self._db, row["id"], row["code"])
            except Exception as e:
                logger.error(f"Recovery error {row['code']}: {e}\n{traceback.format_exc()}")

        logger.info(f"Recovery: completed {processed}/{len(rows)} events")

    async def _emit(self, rec: dict, event: dict, feature_event_id: int | None = None):
        await self._redis.publish("ch:recommendation", orjson.dumps(rec).decode())
        await self._save(rec, feature_event_id=feature_event_id)
        await self._publish_redis(rec)
        await self._redis.publish("channel:features", orjson.dumps(event).decode())

        if rec["action"] == "BUY":
            try:
                await self._redis.set(f"rec:cd24:{rec['code']}", "1", ex=86400)
            except Exception:
                pass
            signal = {
                "code":              rec["code"],
                "name":              rec.get("name", rec["code"]),
                "created_at":        rec["created_at"],
                "action":            rec["action"],
                "entry_price":       rec["entry_price"],
                "target_price":      rec["target_price"],
                "stop_loss_price":   rec["stop_loss_price"],
                "success_prob":      rec["success_prob"],
                "risk_score":        rec["risk_score"],
                "risk_reward_ratio": rec["risk_reward_ratio"],
            }
            await self._redis.publish("ch:signal-generated", orjson.dumps(signal).decode())
            logger.info(
                f"[BUY] {rec['code']} entry={rec['entry_price']} "
                f"target={rec['target_price']} prob={rec['success_prob']:.2f}"
            )

    async def _on_cooldown(self, code: str) -> bool:
        """종목 단위 쿨다운 확인.
        1) Redis 단기 쿨다운 (60분) — 같은 세션 내 폭발적 중복 방지
        2) DB 24시간 쿨다운 — 날짜를 넘겨도 당일 이미 추천한 종목 재추천 방지
        둘 중 하나라도 쿨다운 중이면 True 반환."""
        if not code:
            return False
        # ① Redis 단기 쿨다운
        if _COOLDOWN_MINUTES:
            key = f"rec:cd:{code}"
            try:
                result = await self._redis.set(key, "1", nx=True, ex=_COOLDOWN_MINUTES * 60)
                if result is None:
                    return True
            except Exception:
                pass
        # ② Redis 기반 24시간 쿨다운 — DB 연결 오류에도 안정적으로 작동
        try:
            if await self._redis.get(f"rec:cd24:{code}"):
                return True
        except Exception:
            pass
        # ③ DB 기반 24시간 쿨다운 — Redis 미스 시 폴백 (DB 연결 실패 시 safe=False)
        try:
            since = datetime.now(timezone.utc) - timedelta(hours=24)
            exists = await self._db.fetchval(
                """
                SELECT 1 FROM recommendations
                WHERE code = $1 AND action = 'BUY' AND created_at >= $2
                LIMIT 1
                """,
                code, since,
            )
            if exists:
                # Redis 키 복구 — DB에 있으면 Redis에도 세팅
                try:
                    await self._redis.set(f"rec:cd24:{code}", "1", ex=86400)
                except Exception:
                    pass
                return True
        except Exception:
            pass
        return False

    async def _get_anchor(self, code: str) -> int | None:
        """당일 세션 진입가 앵커 조회."""
        try:
            val = await self._redis.get(f"rec:anchor:{code}")
            return int(val) if val else None
        except Exception:
            return None

    async def _set_anchor(self, code: str, price: int):
        """당일 세션 진입가 앵커 최초 설정 (NX — 이미 있으면 변경 안 함)."""
        try:
            await self._redis.set(f"rec:anchor:{code}", str(price), nx=True, ex=_ANCHOR_HOURS * 3600)
        except Exception:
            pass

    async def _generate(self, event: dict, recommender, use_anchor: bool = True) -> dict | None:
        from ml_client import get_ml_result, get_similar_cases

        # 당일 세션 진입가 앵커 적용
        anchor_price: int | None = None
        if use_anchor:
            stored = await self._get_anchor(event.get("code", ""))
            if stored:
                current = int(event.get("price", 0))
                if current and abs(current - stored) / stored <= _ANCHOR_BAND:
                    anchor_price = stored

        ml_result    = await get_ml_result(event, self._db, redis=self._redis)
        cases, stats = await get_similar_cases(event, self._db)
        rec = recommender.recommend(event, ml_result, stats, cases, anchor_price=anchor_price)

        # BUY 신호 확정 시 앵커 최초 설정
        if rec.action == "BUY" and use_anchor:
            await self._set_anchor(rec.code, rec.entry_price)

        # 종목명/시장 조회
        stock_name, stock_market = rec.code, ""
        try:
            async with self._db.acquire() as _conn:
                row = await _conn.fetchrow("SELECT name, market FROM stocks WHERE code=$1", rec.code)
                if row:
                    stock_name   = row["name"]
                    stock_market = row["market"] or ""
        except Exception:
            pass

        return {
            "code":               rec.code,
            "name":               stock_name,
            "market":             stock_market,
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
                await update_pattern_vector(self._db, event_id, code)

            return event_id
        except Exception as e:
            logger.error(f"Feature event save error {code}: {e}")
            return None

    async def _save(self, rec: dict, feature_event_id: int | None = None):
        async with self._db.acquire() as conn:
            rec_id = await conn.fetchval(
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
                RETURNING id
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
            # BUY 신호 확정 시 성과 추적 초기 row 등록 (텔레그램 발송 기준과 동일한 임계값 적용)
            if rec_id and rec.get("action") == "BUY":
                # Redis 런타임 telegram:config 의 min_prob 기준으로 필터
                perf_min_prob = float(os.environ.get("REC_MIN_PROB", "0.22"))
                try:
                    raw = await self._redis.get("telegram:config")
                    if raw:
                        cfg = orjson.loads(raw)
                        perf_min_prob = float(cfg.get("min_prob", perf_min_prob))
                except Exception:
                    pass
                if rec.get("success_prob", 0) >= perf_min_prob:
                    rationale = rec["rationale"]
                    event_type = (
                        rationale.get("event_type") if isinstance(rationale, dict)
                        else getattr(rationale, "event_type", None)
                    )
                    await conn.execute(
                        """
                        INSERT INTO recommendation_performance
                            (rec_id, code, entry_price, event_type, signal_time)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (rec_id) DO NOTHING
                        """,
                        rec_id, rec["code"], rec["entry_price"],
                        event_type, rec["created_at"],
                    )
                else:
                    logger.debug(
                        f"[PERF_TRACK] skip {rec['code']} prob={rec.get('success_prob',0):.3f} "
                        f"< threshold={perf_min_prob:.3f}"
                    )

    async def _publish_redis(self, rec: dict):
        await self._redis.publish(
            "channel:recommendations",
            orjson.dumps(rec).decode(),
        )


if __name__ == "__main__":
    asyncio.run(RecommenderService().run())
