import asyncio
import logging
import os
from datetime import datetime, timedelta
import redis.asyncio as redis_lib
from rules.volume_surge import VolumeSurgeDetector
from rules.amount_surge import AmountSurgeDetector
from rules.breakout import BreakoutDetector
from rules.candlestick import CandlestickDetector
from rules.supply_anomaly import SupplyAnomalyDetector
from rules.vi_detector import VIDetector
from rules.post_disclosure import PostDisclosureDetector
from kafka.consumer import KafkaConsumerWrapper
from kafka.producer import KafkaProducerWrapper

_COOLDOWN_MINUTES = int(os.environ.get("SIGNAL_COOLDOWN_MINUTES", "10"))

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
        self._cooldown: dict[tuple, datetime] = {}
        self._bar_buffer: dict[str, list[dict]] = {}  # 모닝스타용 종목별 최근 3봉

    async def run(self):
        await asyncio.gather(
            self._process_ticks(),
            self._process_minute_bars(),
            self._process_supply_demand(),
            self._process_disclosures(),
        )

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

                # 장대양봉
                if self.cnd_det.detect_long_white_candle(bar):
                    await self._emit({
                        "code":        code,
                        "event_type":  "LONG_WHITE_CANDLE",
                        "price":       int(bar.get("close", 0)),
                        "change_rate": float(bar.get("change_rate", 0)),
                        "signal_score": self.cnd_det.long_white_score(bar),
                        "signal_data": bar,
                    })

                # 망치형
                if self.cnd_det.detect_hammer(bar):
                    await self._emit({
                        "code":        code,
                        "event_type":  "HAMMER_CANDLE",
                        "price":       int(bar.get("close", 0)),
                        "change_rate": float(bar.get("change_rate", 0)),
                        "signal_score": self.cnd_det.hammer_score(bar),
                        "signal_data": bar,
                    })

                # 모닝스타 (3봉 슬라이딩 버퍼)
                buf = self._bar_buffer.setdefault(code, [])
                buf.append(bar)
                if len(buf) > 3:
                    buf.pop(0)
                if self.cnd_det.detect_morning_star(buf):
                    await self._emit({
                        "code":        code,
                        "event_type":  "MORNING_STAR",
                        "price":       int(bar.get("close", 0)),
                        "change_rate": float(bar.get("change_rate", 0)),
                        "signal_score": 0.68,
                        "signal_data": {"bars": buf[-3:]},
                    })

    async def _process_supply_demand(self):
        async for batch in self.consumer.consume(["supply-demand"], batch_size=50):
            for data in batch:
                anomaly = await self.sup_det.detect(data)
                if anomaly:
                    await self._emit(anomaly)

    async def _process_disclosures(self):
        async for batch in self.consumer.consume(["disclosure"], batch_size=20):
            for disc in batch:
                code     = disc.get("code") or ""
                category = disc.get("category", "neutral")
                if code:
                    await self.disc_det.mark_disclosure(code, category)

    async def _emit(self, signal: dict):
        ck = (signal.get("code"), signal.get("event_type"))
        now = datetime.now()
        last = self._cooldown.get(ck)
        if last and now - last < timedelta(minutes=_COOLDOWN_MINUTES):
            return
        self._cooldown[ck] = now

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


if __name__ == "__main__":
    asyncio.run(FeatureStockDetector().run())
