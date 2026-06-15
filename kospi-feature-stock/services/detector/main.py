import asyncio
import logging
import os
import orjson
import asyncpg
from collections import deque
from datetime import datetime, timedelta, timezone
import redis.asyncio as redis_lib
from rules.volume_surge import VolumeSurgeDetector
from rules.amount_surge import AmountSurgeDetector
from rules.breakout import BreakoutDetector
from rules.candlestick import CandlestickDetector
from rules.supply_anomaly import SupplyAnomalyDetector
from rules.vi_detector import VIDetector
from rules.post_disclosure import PostDisclosureDetector
from rules.correlation import CorrelationDetector
from kafka.consumer import KafkaConsumerWrapper
from kafka.producer import KafkaProducerWrapper

_COOLDOWN_MINUTES   = int(os.environ.get("SIGNAL_COOLDOWN_MINUTES",  "10"))
_NOISE_SCORE_FLOOR  = float(os.environ.get("NOISE_SCORE_FLOOR",      "0.45"))
# 분봉 개별 캔들스틱 탐지는 기본 비활성화.
# 동일 패턴을 일봉 마감 후 batch_scanner에서 더 정확하게 탐지하므로
# 중복 신호 및 데이터 불일치 방지를 위해 0으로 유지한다.
_DETECTOR_CANDLE_ENABLED = os.environ.get("DETECTOR_CANDLE_ENABLED", "0") == "1"
# 세션 OHLC 기반 장중 캔들 탐지 (기본 활성화 — 세션 전체 등락 기준으로 더 안정적)
_DETECTOR_SESSION_CANDLE_ENABLED = os.environ.get("DETECTOR_SESSION_CANDLE_ENABLED", "1") == "1"
# 실시간 캔들 탐지 (장중 세션 OHLC 기반 — batch_scanner dedup Redis 키 병행)
_DETECTOR_CANDLE_REALTIME    = os.environ.get("DETECTOR_CANDLE_REALTIME", "1") == "1"
_SESSION_CANDLE_MIN_RETURN   = float(os.environ.get("SESSION_CANDLE_MIN_RETURN", "0.03"))   # 3%+
_SESSION_CANDLE_HOUR_AFTER   = int(os.environ.get("SESSION_CANDLE_HOUR_AFTER",   "13"))     # 13시 이후
_SESSION_OHLC_TTL            = 28800  # 8시간 (당일 세션 유효)
_CANDLE_RT_MIN_BARS          = int(os.environ.get("CANDLE_RT_MIN_BARS", "5"))   # 최소 분봉 수
_CANDLE_DEDUP_TTL            = 90_000  # 25시간 (당일 + 다음날 장 전까지)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("detector")


class FeatureStockDetector:

    def __init__(self):
        self.redis   = redis_lib.from_url(os.environ["REDIS_URL"])
        self.consumer = KafkaConsumerWrapper(
            os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            group_id="detector-group",
        )
        self.producer = KafkaProducerWrapper(os.environ["KAFKA_BOOTSTRAP_SERVERS"])

        self.vol_det   = VolumeSurgeDetector(self.redis)
        self.amt_det   = AmountSurgeDetector(self.redis)
        self.brk_det   = BreakoutDetector(self.redis)
        self.cnd_det   = CandlestickDetector()
        self.sup_det   = SupplyAnomalyDetector(self.redis)
        self.vi_det    = VIDetector(self.redis)
        self.disc_det  = PostDisclosureDetector(self.redis)
        self.corr_det  = CorrelationDetector(self.redis)
        self._cooldown: dict[tuple, datetime] = {}
        self._emit_count: int = 0
        self._bar_buffer: dict[str, deque] = {}  # 모닝스타용 종목별 최근 3봉
        self._bar_count:  dict[str, int]   = {}  # 실시간 캔들 탐지용 분봉 누적 카운터

    async def run(self):
        # DB 연결 (startup_check용)
        db_pool = await asyncpg.create_pool(
            dsn=os.environ["POSTGRES_DSN"].replace("+asyncpg", ""),
            min_size=2, max_size=5,
        )
        try:
            # Redis 통계 유효성 확인 및 복구
            try:
                import sys, os as _os
                sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '../../collector'))
                from startup_check import ensure_redis_stats
                ok = await ensure_redis_stats(db_pool, self.redis)
                if not ok:
                    logger.warning("Redis 통계 복구 실패 — 탐지 정확도 저하 가능")
            except ImportError:
                logger.warning("startup_check 모듈 없음 — Redis 통계 미검증")

            await asyncio.gather(
                self._process_ticks(),
                self._process_minute_bars(),
                self._process_supply_demand(),
                self._process_disclosures(),
                self._kafka_lag_monitor(db_pool),
            )
        finally:
            await db_pool.close()

    async def _kafka_lag_monitor(self, db=None):
        """30초마다 Kafka 컨슈머 오프셋 lag를 Redis에 기록, 10분마다 DB에도 기록."""
        import orjson
        from aiokafka import AIOKafkaConsumer
        topics = ["tick-data", "minute-bar", "feature-detected", "disclosure", "news"]
        _db_log_interval = 20  # 20 × 30s = 10분마다 DB 기록
        _tick = 0
        while True:
            await asyncio.sleep(30)
            _tick += 1
            try:
                admin_consumer = AIOKafkaConsumer(
                    bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
                    group_id="detector-lag-probe",
                )
                await admin_consumer.start()
                total_lag = 0
                lags: dict[str, int] = {}
                for topic in topics:
                    try:
                        partitions = admin_consumer.partitions_for_topic(topic)
                        if partitions:
                            for p in partitions:
                                from aiokafka import TopicPartition
                                tp = TopicPartition(topic, p)
                                await admin_consumer.seek_to_end(tp)
                                hw = admin_consumer.highwater(tp)
                                pos = await admin_consumer.position(tp)
                                lag = max(0, (hw or 0) - (pos or 0))
                                total_lag += lag
                            lags[topic] = lag
                    except Exception:
                        pass
                await admin_consumer.stop()
                if self.redis:
                    await self.redis.set("kafka:lag:total", total_lag)
                    for topic, lag in lags.items():
                        await self.redis.set(f"kafka:lag:{topic}", lag)
                logger.debug(f"[Kafka Lag] total={total_lag} {lags}")
                # 10분마다 DB 기록 (장기 추세 분석용)
                if db and _tick % _db_log_interval == 0:
                    try:
                        await db.execute(
                            "INSERT INTO system_logs (service, level, message, extra) VALUES ($1,$2,$3,$4::jsonb)",
                            "detector", "INFO", "kafka_lag",
                            orjson.dumps({"total": total_lag, **lags}).decode(),
                        )
                    except Exception as db_err:
                        logger.debug(f"[Kafka Lag] DB 기록 실패: {db_err}")
            except Exception as e:
                logger.debug(f"[Kafka Lag] monitor error: {e}")

    async def _process_ticks(self):
        async for batch in self.consumer.consume(["tick-data"], batch_size=200):
            for tick in batch:
                if not tick:
                    continue
                results = await asyncio.gather(
                    self._from_tick(tick),
                    return_exceptions=True,
                )
                for r in results:
                    if isinstance(r, Exception):
                        logger.error(f"_from_tick error [{tick.get('code')}]: {r!r}")

    async def _from_tick(self, tick: dict):
        code = tick.get("code", "")
        if code and tick.get("price"):
            await self.redis.set(f"stats:{code}:last_price", int(tick["price"]))
            await self.redis.set(f"stats:{code}:last_change_rate", float(tick.get("change_rate", 0)))

        # VI 탐지
        vi = await self.vi_det.detect(tick)
        if vi:
            await self._emit(vi)

        # 신고가 돌파
        for sig in await self.brk_det.detect(tick):
            await self._emit({
                "code":        sig.code,
                "event_type":  sig.event_type,
                "price":       sig.price,
                "change_rate": sig.change_rate,
                "signal_score":sig.signal_score,
                "signal_data": {"prev_high": sig.prev_high, "period_days": sig.period_days},
            })

        # 공시 후 급등
        disc = await self.disc_det.detect(tick)
        if disc:
            await self._emit(disc)

    async def _process_minute_bars(self):
        async for batch in self.consumer.consume(["minute-bar"], batch_size=100):
            for data in batch:
                bars = data.get("bars", [])
                if not bars:
                    continue
                bar = bars[-1]
                code = data.get("code", bar.get("code", ""))
                bar["code"] = code

                # 거래량 급증
                surge = await self.vol_det.detect(bar)
                if surge:
                    await self._emit({
                        "code":         surge.code,
                        "event_type":   surge.event_type,
                        "price":        surge.price,
                        "change_rate":  surge.change_rate,
                        "volume":       surge.volume,
                        "volume_ratio": surge.volume_ratio,
                        "amount":       surge.amount,
                        "signal_score": surge.signal_score,
                        "signal_data":  surge.signal_data,
                    })

                # 거래대금 급증
                amt_surge = await self.amt_det.detect(bar)
                if amt_surge:
                    await self._emit({
                        "code":         amt_surge.code,
                        "event_type":   amt_surge.event_type,
                        "price":        amt_surge.price,
                        "change_rate":  amt_surge.change_rate,
                        "volume":       amt_surge.volume,
                        "amount":       amt_surge.amount,
                        "volume_ratio": amt_surge.amount_ratio,
                        "signal_score": amt_surge.signal_score,
                        "signal_data":  amt_surge.signal_data,
                    })

                # 세션 OHLC 누적 (세션 캔들 탐지에 사용)
                if _DETECTOR_SESSION_CANDLE_ENABLED:
                    await self._update_session_ohlc(code, bar)
                    sig = await self._detect_session_candle(code, bar)
                    if sig:
                        await self._emit(sig)

                # 분봉 개별 캔들스틱 탐지 (DETECTOR_CANDLE_ENABLED=1 일 때만 활성화)
                # 기본값 0: 일봉 마감 후 batch_scanner에서 동일 패턴을 더 정확하게 탐지
                if _DETECTOR_CANDLE_ENABLED:
                    if self.cnd_det.detect_long_white_candle(bar):
                        await self._emit({
                            "code":        code,
                            "event_type":  "LONG_WHITE_CANDLE",
                            "price":       int(bar.get("close", 0)),
                            "change_rate": float(bar.get("change_rate", 0)),
                            "signal_score": self.cnd_det.long_white_score(bar),
                            "signal_data": bar,
                        })

                    if self.cnd_det.detect_hammer(bar):
                        await self._emit({
                            "code":        code,
                            "event_type":  "HAMMER_CANDLE",
                            "price":       int(bar.get("close", 0)),
                            "change_rate": float(bar.get("change_rate", 0)),
                            "signal_score": self.cnd_det.hammer_score(bar),
                            "signal_data": bar,
                        })

                    buf = self._bar_buffer.setdefault(code, deque(maxlen=3))
                    buf.append(bar)
                    if self.cnd_det.detect_morning_star(buf):
                        await self._emit({
                            "code":        code,
                            "event_type":  "MORNING_STAR",
                            "price":       int(bar.get("close", 0)),
                            "change_rate": float(bar.get("change_rate", 0)),
                            "signal_score": 0.68,
                            "signal_data": {"bars": buf[-3:]},
                        })

                # 실시간 세션 캔들 탐지 (DETECTOR_CANDLE_REALTIME=1, 기본값 활성화)
                # 세션 누적 OHLC 기준으로 장중 탐지 → Redis dedup 키로 batch_scanner와 중복 방지
                if _DETECTOR_CANDLE_REALTIME:
                    self._bar_count[code] = self._bar_count.get(code, 0) + 1
                    if self._bar_count[code] >= _CANDLE_RT_MIN_BARS:
                        await self._detect_realtime_candles(code, bar)

    async def _update_session_ohlc(self, code: str, bar: dict):
        """분봉 데이터로 당일 세션 OHLC를 Redis에 누적."""
        today = datetime.now(timezone.utc).astimezone(
            __import__("zoneinfo").ZoneInfo("Asia/Seoul")
        ).strftime("%Y-%m-%d")
        key = f"session:ohlc:{code}"
        try:
            raw = await self.redis.get(key)
            if raw:
                prev = orjson.loads(raw)
                if prev.get("d") != today:
                    prev = None
            else:
                prev = None

            o = float(bar.get("open",  bar.get("close", 0)) or 0)
            h = float(bar.get("high",  bar.get("close", 0)) or 0)
            l = float(bar.get("low",   bar.get("close", 0)) or 0)
            c = float(bar.get("close", 0) or 0)
            v = int(bar.get("volume", 0) or 0)

            if prev:
                new_ohlc = {
                    "d": today,
                    "o": prev["o"],             # 세션 시작가 유지
                    "h": max(prev["h"], h),
                    "l": min(prev["l"], l),
                    "c": c,
                    "v": prev["v"] + v,
                }
            else:
                new_ohlc = {"d": today, "o": o, "h": h, "l": l, "c": c, "v": v}

            await self.redis.set(key, orjson.dumps(new_ohlc), ex=_SESSION_OHLC_TTL)
        except Exception as e:
            logger.debug(f"session ohlc update error {code}: {e}")

    async def _detect_session_candle(self, code: str, bar: dict) -> dict | None:
        """세션 OHLC 기준 장중 Long White Candle 탐지 (13시 이후, 세션 대비 3%+ 상승)."""
        now_kst = datetime.now(timezone.utc).astimezone(
            __import__("zoneinfo").ZoneInfo("Asia/Seoul")
        )
        if now_kst.hour < _SESSION_CANDLE_HOUR_AFTER:
            return None

        key = f"session:ohlc:{code}"
        try:
            raw = await self.redis.get(key)
            if not raw:
                return None
            ohlc = orjson.loads(raw)
            o, c = ohlc.get("o", 0), ohlc.get("c", 0)
            if not o or not c:
                return None
            session_return = (c - o) / o
            if session_return >= _SESSION_CANDLE_MIN_RETURN:
                score = min(0.9, 0.5 + session_return * 5)
                return {
                    "code":        code,
                    "event_type":  "LONG_WHITE_CANDLE",
                    "price":       int(c),
                    "change_rate": float(bar.get("change_rate", 0)),
                    "signal_score": round(score, 3),
                    "signal_data":  {"session_open": o, "session_return": round(session_return, 4)},
                }
        except Exception as e:
            logger.debug(f"session candle detect error {code}: {e}")
        return None

    async def _detect_realtime_candles(self, code: str, bar: dict) -> None:
        """세션 OHLC 기반 실시간 캔들 탐지 — batch_scanner Redis dedup 키 병행."""
        now_kst = datetime.now(timezone.utc).astimezone(
            __import__("zoneinfo").ZoneInfo("Asia/Seoul")
        )
        if now_kst.hour < _SESSION_CANDLE_HOUR_AFTER:
            return

        key_ohlc = f"session:ohlc:{code}"
        try:
            raw = await self.redis.get(key_ohlc)
            if not raw:
                return
            ohlc = orjson.loads(raw)
        except Exception:
            return

        o = float(ohlc.get("o") or 0)
        h = float(ohlc.get("h") or 0)
        l = float(ohlc.get("l") or 0)
        c = float(ohlc.get("c") or 0)
        if not o or not c:
            return

        today    = now_kst.strftime("%Y-%m-%d")
        chg_rate = float(bar.get("change_rate", 0))
        price    = int(c)

        # ── 장대양봉 ───────────────────────────────────────────
        body   = abs(c - o)
        rng    = h - l
        body_r = body / rng if rng else 0
        chg_pct = (c - o) / o * 100 if o else 0
        if body_r >= 0.65 and chg_pct >= 3.0 and c > o:
            dedup = f"candle:rt:{code}:{today}:LONG_WHITE_CANDLE"
            if not await self.redis.exists(dedup):
                score = round(min(0.88, 0.50 + body_r * 0.4 + min(chg_pct / 20.0, 0.10)), 3)
                await self.redis.set(dedup, "1", ex=_CANDLE_DEDUP_TTL)
                await self._emit({
                    "code":        code,
                    "event_type":  "LONG_WHITE_CANDLE",
                    "price":       price,
                    "change_rate": chg_rate,
                    "signal_score": score,
                    "signal_data":  {"body_ratio": round(body_r, 3), "change_pct": round(chg_pct, 2), "realtime": True},
                })

        # ── 망치형 ────────────────────────────────────────────
        lower  = min(o, c) - l
        upper  = h - max(o, c)
        if body > 0 and lower >= 2 * body and upper <= 0.1 * body:
            dedup = f"candle:rt:{code}:{today}:HAMMER_CANDLE"
            if not await self.redis.exists(dedup):
                ratio_val = lower / body
                score = round(min(0.72, 0.45 + ratio_val * 0.05), 3)
                await self.redis.set(dedup, "1", ex=_CANDLE_DEDUP_TTL)
                await self._emit({
                    "code":        code,
                    "event_type":  "HAMMER_CANDLE",
                    "price":       price,
                    "change_rate": chg_rate,
                    "signal_score": score,
                    "signal_data":  {"lower_shadow_ratio": round(ratio_val, 2), "realtime": True},
                })

    async def _process_supply_demand(self):
        async for batch in self.consumer.consume(["supply-demand"], batch_size=50):
            for data in batch:
                for sig in await self._detect_supply(data):
                    await self._emit(sig)

    async def _detect_supply(self, data: dict) -> list[dict]:
        sigs: list[dict] = []
        anomaly = await self.sup_det.detect(data)
        if anomaly:
            sigs.append(anomaly)
        short = await self.sup_det.detect_short_surge(data)
        if short:
            sigs.append(short)
        streak = await self.sup_det.detect_dual_buy_streak(data)
        if streak:
            sigs.append(streak)
        return sigs

    async def _process_disclosures(self):
        async for batch in self.consumer.consume(["disclosure"], batch_size=20):
            for disc in batch:
                code     = disc.get("code") or ""
                category = disc.get("category", "neutral")
                if code:
                    await self.disc_det.mark_disclosure(code, category)

    async def _emit(self, signal: dict):
        # 노이즈 필터: signal_score 임계치 미달 신호 조기 차단
        score = float(signal.get("signal_score", 0.5))
        if score < _NOISE_SCORE_FLOOR:
            logger.debug(
                f"[NOISE] {signal.get('code')} {signal.get('event_type')} "
                f"score={score:.2f} < {_NOISE_SCORE_FLOOR:.2f} — skipped"
            )
            return

        ck = (signal.get("code"), signal.get("event_type"))
        now = datetime.now()
        last = self._cooldown.get(ck)
        if last and now - last < timedelta(minutes=_COOLDOWN_MINUTES):
            return
        self._cooldown[ck] = now
        self._emit_count += 1
        if self._emit_count % 500 == 0:
            cutoff = now - timedelta(minutes=_COOLDOWN_MINUTES * 2)
            for k in [k for k, v in self._cooldown.items() if v < cutoff]:
                del self._cooldown[k]

        signal.setdefault("detected_at", now.isoformat())
        signal.setdefault("signal_score", 0.5)
        await self.producer.send(
            "feature-detected",
            signal,
            key=signal.get("code", ""),
        )
        logger.info(
            f"[SIGNAL] {signal.get('code')} {signal.get('event_type')} "
            f"score={signal.get('signal_score', 0):.2f}"
        )

        # 섹터 상관 탐지: 동일 섹터 집중 신호 확인
        corr = await self.corr_det.record_and_check(signal)
        if corr:
            # SECTOR_CORRELATION은 별도 cooldown (코드+타입 키로 관리됨)
            corr_ck = (corr.get("code"), "SECTOR_CORRELATION")
            corr_last = self._cooldown.get(corr_ck)
            if not corr_last or now - corr_last >= timedelta(minutes=_COOLDOWN_MINUTES):
                self._cooldown[corr_ck] = now
                corr.setdefault("detected_at", now.isoformat())
                await self.producer.send("feature-detected", corr, key=corr.get("code", ""))
                logger.info(
                    f"[CORR] {corr.get('code')} sector={corr.get('signal_data', {}).get('sector')} "
                    f"stocks={corr.get('signal_data', {}).get('stock_count')} score={corr.get('signal_score', 0):.2f}"
                )


if __name__ == "__main__":
    asyncio.run(FeatureStockDetector().run())
