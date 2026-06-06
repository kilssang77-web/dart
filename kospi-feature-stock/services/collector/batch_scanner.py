"""
장 마감 후 전체 종목 일봉 기반 배치 특징주 탐지.

흐름:
  1. 오늘 일봉(OHLCV + 수급) 전체 조회 — 단일 쿼리
  2. 이전 N일 고가(신고가 기준) 전체 조회 — 단일 쿼리
  3. Redis 파이프라인으로 거래량/수급 평균 일괄 조회
  4. 종목별 시그널 판정 (거래량급증 / 신고가 / 캔들 / 수급이상)
  5. feature_events 저장 + Kafka 발행
  6. 상위 N개 종목을 stocks:active_codes 에 갱신 → 다음날 실시간 모니터링 자동 편입
"""

import asyncio
import logging
import os
from datetime import date, timedelta, datetime, timezone

import asyncpg
import orjson
import redis.asyncio as redis_lib

logger = logging.getLogger("batch_scanner")

# ── 탐지 임계값 (환경변수로 오버라이드 가능) ────────────────
VOL_SURGE_RATIO    = float(os.environ.get("BATCH_VOL_SURGE_RATIO",    "3.0"))
AMOUNT_SURGE_RATIO = float(os.environ.get("BATCH_AMOUNT_SURGE_RATIO", "3.0"))
SUPPLY_SURGE_RATIO = float(os.environ.get("BATCH_SUPPLY_SURGE_RATIO", "3.0"))
BREAKOUT_MIN_PCT   = float(os.environ.get("BATCH_BREAKOUT_MIN_PCT",   "0.001"))  # 0.1%
MIN_AMOUNT         = int(os.environ.get("BATCH_MIN_AMOUNT",           "500000000"))  # 5억

TOP_N_ACTIVE       = int(os.environ.get("BATCH_TOP_N_ACTIVE", "80"))  # 다음날 실시간 대상

_BASE_CODES = [
    "005930", "000660", "035420", "005380", "051910",
    "006400", "035720", "028260", "207940", "068270",
    "323410", "105560", "055550", "086790", "032830",
    "066570", "003550", "096770", "033780", "015760",
]

_BREAKOUT_CONF = [
    # (event_type, calendar_days_lookback, base_score)
    ("BREAKOUT_52W", 400, 0.80),
    ("BREAKOUT_26W", 200, 0.70),
    ("BREAKOUT_13W", 100, 0.60),
    ("BREAKOUT_20D",  30, 0.50),
]


class BatchScanner:

    def __init__(
        self,
        db: asyncpg.Pool,
        redis: redis_lib.Redis,
        kafka,                     # KafkaProducerWrapper
    ):
        self.db    = db
        self.redis = redis
        self.kafka = kafka

    # ─────────────────────────────────────────────────────────────
    # 진입점
    # ─────────────────────────────────────────────────────────────

    async def run(self, all_codes: list[str]) -> list[dict]:
        today = date.today()
        logger.info(f"[BatchScan] Start — {len(all_codes)} stocks, date={today}")

        # 1. 오늘 일봉
        today_map = await self._fetch_today_bars(all_codes, today)
        if not today_map:
            logger.warning("[BatchScan] No today bars found — skipping")
            return []

        live_codes = list(today_map.keys())
        logger.info(f"[BatchScan] {len(live_codes)} stocks have today bars")

        # 2. 신고가 기준 이전 고가 (DB 단일 쿼리)
        highs_map = await self._fetch_breakout_highs(live_codes, today)

        # 3. 거래량·수급 평균 (Redis 파이프라인)
        avgs_map = await self._fetch_redis_avgs(live_codes)

        # 4. 시그널 판정
        events: list[dict] = []
        for code in live_codes:
            bar   = today_map[code]
            highs = highs_map.get(code, {})
            avgs  = avgs_map.get(code, {})
            events.extend(self._detect(code, bar, highs, avgs))

        logger.info(f"[BatchScan] Detected {len(events)} signals")

        # 5. DB 저장 + Kafka 발행
        if events:
            await self._write_events(events)
            for ev in events:
                try:
                    await self.kafka.send("feature-detected", ev, key=ev["code"])
                except Exception as e:
                    logger.debug(f"[BatchScan] Kafka send error {ev['code']}: {e}")

        # 6. active_codes 갱신
        await self._update_active_codes(events)

        return events

    # ─────────────────────────────────────────────────────────────
    # DB 조회
    # ─────────────────────────────────────────────────────────────

    async def _fetch_today_bars(
        self, codes: list[str], today: date
    ) -> dict[str, dict]:
        rows = await self.db.fetch(
            """
            SELECT code, open, high, low, close, volume, amount,
                   change_rate, foreign_net_buy, inst_net_buy
            FROM daily_bars
            WHERE code = ANY($1::varchar[])
              AND date  = $2
              AND close > 0
              AND amount >= $3
            """,
            codes, today, MIN_AMOUNT,
        )
        return {r["code"]: dict(r) for r in rows}

    async def _fetch_breakout_highs(
        self, codes: list[str], today: date
    ) -> dict[str, dict]:
        """오늘 이전 기간별 최고가 (오늘 제외 → 진짜 신고가 판별)."""
        rows = await self.db.fetch(
            """
            SELECT
                code,
                MAX(close) FILTER (WHERE date >= $2 - INTERVAL '30 days')  AS high_20d,
                MAX(close) FILTER (WHERE date >= $2 - INTERVAL '100 days') AS high_13w,
                MAX(close) FILTER (WHERE date >= $2 - INTERVAL '200 days') AS high_26w,
                MAX(close) FILTER (WHERE date >= $2 - INTERVAL '400 days') AS high_52w
            FROM daily_bars
            WHERE code = ANY($1::varchar[])
              AND date < $2
              AND close > 0
            GROUP BY code
            """,
            codes, today,
        )
        return {r["code"]: dict(r) for r in rows}

    # ─────────────────────────────────────────────────────────────
    # Redis 조회 (파이프라인)
    # ─────────────────────────────────────────────────────────────

    async def _fetch_redis_avgs(self, codes: list[str]) -> dict[str, dict]:
        """거래량·거래대금·수급 20일 평균을 Redis 파이프라인으로 일괄 조회."""
        fields = ["avg_vol_20d", "avg_amount_20d", "avg_foreign_20d", "avg_inst_20d"]

        pipe = self.redis.pipeline()
        for code in codes:
            for f in fields:
                pipe.get(f"stats:{code}:{f}")
        raw = await pipe.execute()

        result: dict[str, dict] = {}
        for i, code in enumerate(codes):
            base = i * len(fields)
            vals = {}
            for j, f in enumerate(fields):
                v = raw[base + j]
                if v is not None:
                    try:
                        vals[f] = float(v)
                    except (ValueError, TypeError):
                        pass
            result[code] = vals
        return result

    # ─────────────────────────────────────────────────────────────
    # 시그널 판정
    # ─────────────────────────────────────────────────────────────

    def _detect(
        self,
        code: str,
        bar:  dict,
        highs: dict,
        avgs:  dict,
    ) -> list[dict]:
        results: list[dict] = []

        price       = bar.get("close")  or 0
        o           = bar.get("open")   or 0
        h           = bar.get("high")   or 0
        l           = bar.get("low")    or 0
        volume      = bar.get("volume") or 0
        amount      = bar.get("amount") or 0
        change_rate = float(bar.get("change_rate") or 0)
        foreign     = bar.get("foreign_net_buy") or 0
        inst        = bar.get("inst_net_buy")    or 0

        base = dict(code=code, price=price, change_rate=change_rate)

        # ── 1. 거래량 급증 ──────────────────────────────────────
        avg_vol = avgs.get("avg_vol_20d")
        if avg_vol and avg_vol > 0 and volume > avg_vol * VOL_SURGE_RATIO:
            ratio = volume / avg_vol
            score = min(0.95, 0.50 + (ratio - VOL_SURGE_RATIO) / (VOL_SURGE_RATIO * 4))
            results.append({**base,
                "event_type":   "VOLUME_SURGE",
                "volume":       volume,
                "volume_ratio": round(ratio, 2),
                "amount":       amount,
                "signal_score": round(score, 3),
                "signal_data":  {"avg_vol_20d": int(avg_vol), "vol_ratio": round(ratio, 2)},
            })

        # ── 2. 거래대금 급증 ────────────────────────────────────
        avg_amt = avgs.get("avg_amount_20d")
        if avg_amt and avg_amt > 0 and amount > avg_amt * AMOUNT_SURGE_RATIO:
            ratio = amount / avg_amt
            score = min(0.90, 0.45 + (ratio - AMOUNT_SURGE_RATIO) / (AMOUNT_SURGE_RATIO * 4))
            results.append({**base,
                "event_type":   "AMOUNT_SURGE",
                "volume":       volume,
                "volume_ratio": round(ratio, 2),
                "amount":       amount,
                "signal_score": round(score, 3),
                "signal_data":  {"avg_amount_20d": int(avg_amt), "amount_ratio": round(ratio, 2)},
            })

        # ── 3. 신고가 돌파 ──────────────────────────────────────
        high_keys = {
            "BREAKOUT_52W": (highs.get("high_52w"), 0.80),
            "BREAKOUT_26W": (highs.get("high_26w"), 0.70),
            "BREAKOUT_13W": (highs.get("high_13w"), 0.60),
            "BREAKOUT_20D": (highs.get("high_20d"), 0.50),
        }
        for evt_type, (prev_high, base_score) in high_keys.items():
            if prev_high and prev_high > 0 and price > prev_high * (1 + BREAKOUT_MIN_PCT):
                excess_pct = (price - prev_high) / prev_high * 100
                score = min(0.95, base_score + excess_pct / 20.0)
                results.append({**base,
                    "event_type":   evt_type,
                    "signal_score": round(score, 3),
                    "signal_data":  {
                        "prev_high":  int(prev_high),
                        "excess_pct": round(excess_pct, 2),
                    },
                })

        # ── 4. 장대양봉 ─────────────────────────────────────────
        if price > 0 and o > 0 and h > l:
            body    = abs(price - o)
            rng     = h - l
            body_r  = body / rng if rng else 0
            chg_pct = (price - o) / o * 100
            if body_r >= 0.65 and chg_pct >= 3.0 and price > o:
                score = min(0.92, 0.50 + body_r * 0.4 + min(chg_pct / 20.0, 0.10))
                results.append({**base,
                    "event_type":   "LONG_WHITE_CANDLE",
                    "signal_score": round(score, 3),
                    "signal_data":  {"body_ratio": round(body_r, 3), "change_pct": round(chg_pct, 2)},
                })

            # ── 5. 망치형 캔들 ──────────────────────────────────
            lower_shadow = min(o, price) - l
            upper_shadow = h - max(o, price)
            if body > 0 and lower_shadow >= 2 * body and upper_shadow <= 0.1 * body:
                ratio_val = lower_shadow / body
                score = min(0.72, 0.45 + ratio_val * 0.05)
                results.append({**base,
                    "event_type":   "HAMMER_CANDLE",
                    "signal_score": round(score, 3),
                    "signal_data":  {"lower_shadow_ratio": round(ratio_val, 2)},
                })

        # ── 6. 외국인/기관 수급 이상 ────────────────────────────
        avg_f = avgs.get("avg_foreign_20d")
        avg_i = avgs.get("avg_inst_20d")
        surge_n, max_ratio = 0, 0.0
        if avg_f and avg_f > 0 and foreign > avg_f * SUPPLY_SURGE_RATIO:
            r = foreign / avg_f; surge_n += 1; max_ratio = max(max_ratio, r)
        if avg_i and avg_i > 0 and inst > avg_i * SUPPLY_SURGE_RATIO:
            r = inst / avg_i; surge_n += 1; max_ratio = max(max_ratio, r)
        if surge_n:
            score = min(0.95, 0.35 + max_ratio / (SUPPLY_SURGE_RATIO * 4) + surge_n * 0.10)
            results.append({**base,
                "event_type":   "SUPPLY_ANOMALY",
                "signal_score": round(score, 3),
                "signal_data":  {
                    "foreign_net": int(foreign), "inst_net": int(inst),
                    "f_ratio": round(foreign / avg_f if avg_f else 0, 2),
                    "i_ratio": round(inst    / avg_i if avg_i else 0, 2),
                },
            })

        # risk_score: 신호 강도의 역수 (간략 계산)
        for ev in results:
            ev.setdefault("risk_score", round(max(0.15, 0.80 - ev["signal_score"]), 3))

        return results

    # ─────────────────────────────────────────────────────────────
    # DB 저장
    # ─────────────────────────────────────────────────────────────

    async def _write_events(self, events: list[dict]) -> None:
        now = datetime.now(timezone.utc)
        rows = [
            (
                now,
                e["code"],
                e["event_type"],
                e.get("price"),
                e.get("change_rate"),
                e.get("volume"),
                e.get("volume_ratio"),
                e.get("amount"),
                orjson.dumps(e.get("signal_data", {})).decode(),
                e.get("signal_score"),
                e.get("risk_score", 0.3),
            )
            for e in events
        ]
        try:
            async with self.db.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO feature_events
                        (detected_at, code, event_type, price, change_rate,
                         volume, volume_ratio, amount, signal_data,
                         signal_score, risk_score)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11)
                    ON CONFLICT DO NOTHING
                    """,
                    rows,
                )
            logger.info(f"[BatchScan] Saved {len(rows)} events to feature_events")
        except Exception as e:
            logger.error(f"[BatchScan] DB write error: {e}")

    # ─────────────────────────────────────────────────────────────
    # Redis active_codes 갱신
    # ─────────────────────────────────────────────────────────────

    async def _update_active_codes(self, events: list[dict]) -> None:
        """탐지 종목 상위 N개 + 관심종목 + 기본 20개 병합 → 다음날 실시간 모니터링 대상 (최대 100개)."""
        # 종목별 최고 signal_score
        best: dict[str, float] = {}
        for ev in events:
            code  = ev["code"]
            score = ev.get("signal_score", 0)
            if score > best.get(code, 0):
                best[code] = score

        top_codes = sorted(best, key=lambda c: best[c], reverse=True)[:TOP_N_ACTIVE]

        # 사용자 관심종목 (Redis 동기화)
        fav_codes: list[str] = []
        try:
            raw = await self.redis.get("user:favorites")
            if raw:
                fav_codes = orjson.loads(raw)
        except Exception:
            pass

        merged = list(dict.fromkeys(top_codes + fav_codes + _BASE_CODES))[:100]
        await self.redis.set(
            "stocks:active_codes",
            orjson.dumps(merged),
            ex=90_000,   # 25시간 TTL
        )
        logger.info(
            f"[BatchScan] active_codes updated: {len(top_codes)} feature + "
            f"{len(fav_codes)} favorites + {len(_BASE_CODES)} base = {len(merged)} total"
        )
