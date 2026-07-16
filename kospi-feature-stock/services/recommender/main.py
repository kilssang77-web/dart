import asyncio
import json
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

# ── 시장 국면(Market Regime) 필터 파라미터 ─────────────────────────────────────
# Bear 국면: BUY→WAIT 완전 억제(true) vs 확률만 하향 조정(false)
_REGIME_BEAR_SUPPRESS   = os.environ.get("REGIME_BEAR_SUPPRESS", "true").lower() == "true"
# Bear 국면에서 SUPPRESS=false일 때 확률 승수 (기본 0.75)
_REGIME_BEAR_PROB_MULT  = float(os.environ.get("REGIME_BEAR_PROB_MULT",    "0.75"))
# Neutral 국면 확률 승수 (기본 0.88)
_REGIME_NEUTRAL_PROB_MULT = float(os.environ.get("REGIME_NEUTRAL_PROB_MULT", "0.88"))

_KST = timezone(timedelta(hours=9))

# KRX 공식 비거래일 (주말 제외 공휴일·임시공휴일)
# 출처: KRX 연간 휴장일 공고 기준
_KRX_HOLIDAYS: frozenset[tuple[int, int, int]] = frozenset({
    # 2025년
    (2025, 1, 1),   # 신정
    (2025, 1, 28),  # 설날 전날
    (2025, 1, 29),  # 설날
    (2025, 1, 30),  # 설날 다음날
    (2025, 3, 1),   # 삼일절
    (2025, 5, 5),   # 어린이날
    (2025, 5, 6),   # 어린이날 대체
    (2025, 6, 6),   # 현충일
    (2025, 8, 15),  # 광복절
    (2025, 10, 3),  # 개천절
    (2025, 10, 6),  # 추석 전날
    (2025, 10, 7),  # 추석
    (2025, 10, 8),  # 추석 다음날
    (2025, 10, 9),  # 한글날
    (2025, 12, 25), # 크리스마스
    (2025, 12, 31), # KRX 연말 휴장
    # 2026년
    (2026, 1, 1),   # 신정
    (2026, 1, 27),  # 설날 전날 (음력 12/29)
    (2026, 1, 28),  # 설날 (음력 1/1)
    (2026, 1, 29),  # 설날 다음날 (음력 1/2)
    (2026, 1, 30),  # 설날 대체공휴일
    (2026, 3, 2),   # 삼일절 대체 (3/1 일요일)
    (2026, 5, 5),   # 어린이날
    (2026, 5, 25),  # 부처님오신날 (음력 4/8)
    (2026, 6, 6),   # 현충일 (토요일이나 KRX 별도 지정 확인 필요)
    (2026, 8, 17),  # 광복절 대체 (8/15 토요일)
    (2026, 9, 24),  # 추석 전날
    (2026, 9, 25),  # 추석
    (2026, 9, 26),  # 추석 다음날
    (2026, 10, 9),  # 한글날
    (2026, 12, 25), # 크리스마스
    (2026, 12, 31), # KRX 연말 휴장
    # 2027년 (추가 예정)
    (2027, 1, 1),   # 신정
})


# 런타임 공휴일 세트 — 기동 시 Redis에서 갱신, 없으면 _KRX_HOLIDAYS 사용
_krx_holidays_dynamic: set[tuple[int, int, int]] = set(_KRX_HOLIDAYS)


async def _refresh_holiday_cache(redis: redis_lib.Redis) -> None:
    """Redis krx:holidays:{year} 에서 공휴일 읽어 _krx_holidays_dynamic 갱신.
    하드코딩 _KRX_HOLIDAYS 와 합집합하여 KRX 자체 휴장일(연말 등)도 보완.
    """
    global _krx_holidays_dynamic
    loaded: set[tuple[int, int, int]] = set()
    now_year = datetime.now(_KST).year

    for year in [now_year - 1, now_year, now_year + 1]:
        try:
            raw = await redis.get(f"krx:holidays:{year}")
            if raw:
                date_strs: list[str] = json.loads(raw)
                for ds in date_strs:
                    loaded.add((int(ds[:4]), int(ds[5:7]), int(ds[8:10])))
        except Exception as e:
            logger.warning(f"[recommender] Redis 공휴일 로드 실패 {year}: {e}")

    if loaded:
        _krx_holidays_dynamic = loaded | set(_KRX_HOLIDAYS)
        logger.info(
            f"[recommender] 공휴일 캐시 갱신: "
            f"API {len(loaded)}건 + 하드코딩 보완 → 총 {len(_krx_holidays_dynamic)}건"
        )
    else:
        logger.warning("[recommender] Redis 공휴일 미확보 — 하드코딩 데이터 사용")


def _is_trading_day() -> bool:
    """한국 거래일 여부: 월~금 + KRX 비거래일 제외 + 09:00~15:35 KST."""
    now_kst = datetime.now(_KST)
    if now_kst.weekday() >= 5:          # 토·일
        return False
    if (now_kst.year, now_kst.month, now_kst.day) in _krx_holidays_dynamic:
        return False
    hour, minute = now_kst.hour, now_kst.minute
    return (hour > 9 or (hour == 9 and minute >= 0)) and (hour < 15 or (hour == 15 and minute <= 35))
# 당일 세션 진입가 앵커 유효 시간 (시간)
_ANCHOR_HOURS     = int(os.environ.get("REC_ANCHOR_HOURS",     "8"))
# 앵커 가격과 현재가 허용 괴리율 (초과 시 앵커 무시)
_ANCHOR_BAND      = float(os.environ.get("REC_ANCHOR_BAND",    "0.03"))


class RecommenderService:

    def __init__(self):
        self._db: asyncpg.Pool | None = None
        self._redis: redis_lib.Redis | None = None

    async def setup(self):
        dsn = os.environ["POSTGRES_DSN"].replace("+asyncpg", "")
        self._db = await asyncpg.create_pool(
            dsn=dsn, min_size=3, max_size=10,
            ssl="require" if "supabase" in dsn else False,
            statement_cache_size=0,
        )
        self._redis = redis_lib.from_url(os.environ["REDIS_URL"])

    async def run(self):
        await self.setup()

        # 기동 시 Redis에서 공휴일 캐시 갱신
        await _refresh_holiday_cache(self._redis)

        from entry_recommender import EntryRecommender, update_threshold
        recommender = EntryRecommender()

        # 기동 시 Redis에서 optimal_threshold 로드
        await self._sync_threshold(update_threshold)

        # 기동 시 미처리 이벤트 복구
        await self._recover_missed_events(recommender)

        # 주기적 미처리 이벤트 재스캔 (메시지 유실 방지)
        _recovery_interval = int(os.environ.get("REC_PERIODIC_RECOVERY_MINUTES", "30")) * 60
        recovery_task = asyncio.create_task(
            self._periodic_recovery_loop(recommender, _recovery_interval)
        )
        # 주기적 threshold 동기화 (ML 재학습 후 자동 갱신, 10분 간격)
        threshold_task = asyncio.create_task(
            self._threshold_sync_loop(update_threshold)
        )

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
                if not _is_trading_day():
                    logger.debug(f"Non-trading skip: {event.get('code')} {event.get('event_type')}")
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
            recovery_task.cancel()
            threshold_task.cancel()
            try:
                await pubsub.unsubscribe()
                await pubsub.aclose()
            except Exception:
                pass

    async def _periodic_recovery_loop(self, recommender, interval: int) -> None:
        """주기적으로 미처리 feature_events를 재스캔해 pub/sub 유실 방지."""
        while True:
            await asyncio.sleep(interval)
            try:
                logger.info("[periodic-recovery] scanning missed events...")
                await self._recover_missed_events(recommender)
            except Exception as e:
                logger.error(f"[periodic-recovery] error: {e}")

    async def _sync_threshold(self, update_fn) -> None:
        """Redis ml:optimal_threshold 값으로 entry_recommender 임계값 갱신."""
        try:
            val = await self._redis.get("ml:optimal_threshold")
            if val:
                update_fn(float(val))
        except Exception as e:
            logger.warning(f"[threshold-sync] Redis 조회 실패: {e}")

    async def _threshold_sync_loop(self, update_fn, interval: int = 600) -> None:
        """10분마다 Redis ml:optimal_threshold를 폴링해 임계값 핫업데이트."""
        while True:
            await asyncio.sleep(interval)
            await self._sync_threshold(update_fn)

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
        1) Redis 단기 쿨다운 (_COOLDOWN_MINUTES) — 세션 내 폭발적 중복 방지
        2) DB 당일(KST) 쿨다운 — 날짜가 같으면 재추천 방지
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
        # ② Redis 기반 당일 쿨다운 — 장 시작 시 초기화됨
        try:
            if await self._redis.get(f"rec:cd24:{code}"):
                return True
        except Exception:
            pass
        # ③ DB 당일(KST) 쿨다운 — Redis 미스 시 폴백
        try:
            exists = await self._db.fetchval(
                """
                SELECT 1 FROM recommendations
                WHERE code = $1 AND action = 'BUY'
                  AND (created_at AT TIME ZONE 'Asia/Seoul')::DATE
                      = (NOW() AT TIME ZONE 'Asia/Seoul')::DATE
                LIMIT 1
                """,
                code,
            )
            if exists:
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

    async def _get_market_regime(self) -> dict | None:
        """KOSPI MA20 기준 시장 국면 판단. Redis 캐시 우선(30분 TTL)."""
        CACHE_KEY = "market:regime"
        try:
            cached = await self._redis.get(CACHE_KEY)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

        try:
            async with self._db.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT close FROM daily_bars WHERE code='0001' ORDER BY date DESC LIMIT 25"
                )
            if not rows or len(rows) < 5:
                return None

            closes = [float(r["close"]) for r in rows]
            kospi_price = closes[0]
            ma20 = sum(closes[:20]) / min(20, len(closes))
            pct  = (kospi_price - ma20) / ma20 * 100

            bear_thr = float(os.environ.get("REGIME_BEAR_THRESHOLD", "-3.0"))
            bull_thr = float(os.environ.get("REGIME_BULL_THRESHOLD", "-0.5"))
            if pct < bear_thr:
                phase = "bear"
            elif pct < bull_thr:
                phase = "neutral"
            else:
                phase = "bull"

            result = {
                "phase":         phase,
                "kospi_price":   round(kospi_price, 2),
                "ma20":          round(ma20, 2),
                "pct_from_ma20": round(pct, 2),
            }
            try:
                await self._redis.set(CACHE_KEY, json.dumps(result), ex=1800)
            except Exception:
                pass
            return result
        except Exception as e:
            logger.warning(f"[REGIME] 시장 국면 조회 실패: {e}")
            return None

    async def _get_theme_boost(self, code: str, sector: str | None) -> dict:
        """활성 테마 여부 확인 + 테마 역전 감지.
        Returns: {boost, themes, reversal, reversal_note}
        """
        CACHE_KEY = f"theme:boost:{code}"
        try:
            cached = await self._redis.get(CACHE_KEY)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

        result: dict = {"boost": 0.0, "themes": [], "reversal": False, "reversal_note": None}
        try:
            since = datetime.now(timezone.utc) - timedelta(hours=72)
            async with self._db.acquire() as conn:
                # 해당 종목의 최근 테마 뉴스 — 개별 테마 원소 단위로 집계
                theme_rows = await conn.fetch(
                    """
                    SELECT elem AS theme, COUNT(*) AS cnt
                    FROM news n
                    JOIN news_stock_links nsl ON nsl.news_id = n.id
                    , jsonb_array_elements_text(n.themes) AS elem
                    WHERE nsl.code = $1
                      AND nsl.relevance >= 0.5
                      AND n.published_at >= $2
                      AND n.themes IS NOT NULL AND n.themes != '[]'::jsonb
                      AND LENGTH(elem) >= 2
                      AND elem NOT IN (
                          'href','target','blank','v.daum.net','_blank','javascript',
                          'daum','naver','kakao','Blog','Naver','USA',
                          '머니투데이','연합뉴스','이데일리','헤럴드경제','한국경제',
                          '뉴스1','조선비즈','서울경제','매일경제','파이낸셜뉴스',
                          '상한','하한','증시','주가','종목','거래량','주식','매매'
                      )
                    GROUP BY elem
                    ORDER BY cnt DESC
                    LIMIT 10
                    """,
                    code, since,
                )
                theme_counts: dict[str, int] = {row["theme"]: int(row["cnt"]) for row in theme_rows}

                if not theme_counts and sector:
                    # 섹터 활성도 폴백: 동일 섹터 탐지 건수
                    sector_cnt = await conn.fetchval(
                        """
                        SELECT COUNT(*) FROM feature_events fe
                        JOIN stocks s ON s.code = fe.code
                        WHERE s.sector = $1 AND fe.detected_at >= $2
                        """,
                        sector, since,
                    )
                    if sector_cnt and sector_cnt >= 5:
                        result["boost"] = 0.02
                        result["themes"] = [sector]
                else:
                    top_themes = sorted(theme_counts.items(), key=lambda x: -x[1])[:3]
                    active_themes = [t for t, c in top_themes if c >= 1]
                    if active_themes:
                        # 기사 2건 이상 언급 테마: +2% / 1건: +1%, 최대 3%
                        boost = sum(0.02 if c >= 2 else 0.01 for _, c in top_themes if c >= 1)
                        boost = round(min(0.03, boost), 3)
                        result["boost"] = boost
                        result["themes"] = active_themes

                        # 테마 역전 감지: theme_snapshots velocity < -0.1
                        snap_rows = await conn.fetch(
                            """
                            SELECT DISTINCT ON (theme_name)
                                theme_name, velocity, momentum_score
                            FROM theme_snapshots
                            WHERE theme_name = ANY($1::text[])
                              AND snap_date >= CURRENT_DATE - INTERVAL '7 days'
                            ORDER BY theme_name, snap_date DESC
                            """,
                            active_themes,
                        )
                        reversal_themes = [
                            r["theme_name"] for r in snap_rows
                            if r["velocity"] is not None and float(r["velocity"]) < -0.1
                        ]
                        if reversal_themes:
                            result["reversal"] = True
                            result["reversal_note"] = f"테마 역전 주의: {', '.join(reversal_themes)} (모멘텀 하락)"
                            result["boost"] = 0.0
        except Exception as e:
            logger.warning(f"[THEME] 테마 부스트 조회 실패 {code}: {e}")

        try:
            await self._redis.set(CACHE_KEY, json.dumps(result), ex=900)
        except Exception:
            pass
        return result

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

        regime       = await self._get_market_regime()
        ml_result    = await get_ml_result(event, self._db, redis=self._redis)
        cases, stats = await get_similar_cases(event, self._db)
        rec = recommender.recommend(event, ml_result, stats, cases, anchor_price=anchor_price)

        # BUY 신호 확정 시 앵커 최초 설정
        if rec.action == "BUY" and use_anchor:
            await self._set_anchor(rec.code, rec.entry_price)

        # ── 시장 국면(Market Regime) 필터 ─────────────────────────────
        action       = rec.action
        success_prob = rec.success_prob
        regime_note: str | None = None
        if regime:
            pct   = regime.get("pct_from_ma20", 0.0)
            phase = regime.get("phase", "neutral")
            if phase == "bear" and action == "BUY":
                if _REGIME_BEAR_SUPPRESS:
                    action      = "WAIT"
                    regime_note = f"하락장 진입 억제 (KOSPI MA20 대비 {pct:.1f}%)"
                    logger.info(f"[REGIME] Bear filter: {rec.code} BUY→WAIT (KOSPI {pct:.1f}% vs MA20)")
                else:
                    success_prob = round(success_prob * _REGIME_BEAR_PROB_MULT, 4)
                    regime_note  = f"하락장 확률 하향 (KOSPI MA20 대비 {pct:.1f}%, ×{_REGIME_BEAR_PROB_MULT})"
                    logger.info(f"[REGIME] Bear adjust: {rec.code} prob×{_REGIME_BEAR_PROB_MULT} (KOSPI {pct:.1f}% vs MA20)")
            elif phase == "neutral" and action == "BUY":
                success_prob = round(success_prob * _REGIME_NEUTRAL_PROB_MULT, 4)
                regime_note  = f"중립장 확률 조정 (KOSPI MA20 대비 {pct:.1f}%, ×{_REGIME_NEUTRAL_PROB_MULT})"

        # 종목명/시장/섹터 조회
        stock_name, stock_market, stock_sector = rec.code, "", None
        try:
            async with self._db.acquire() as _conn:
                row = await _conn.fetchrow("SELECT name, market, sector FROM stocks WHERE code=$1", rec.code)
                if row:
                    stock_name   = row["name"]
                    stock_market = row["market"] or ""
                    stock_sector = row["sector"]
        except Exception:
            pass

        # ── 테마 활성도 보너스 + 역전 감지 ─────────────────────────────
        theme_info = await self._get_theme_boost(rec.code, stock_sector)
        theme_boost   = theme_info.get("boost", 0.0)
        theme_reversal = theme_info.get("reversal", False)
        theme_reversal_note = theme_info.get("reversal_note")
        active_themes = theme_info.get("themes", [])

        if theme_boost > 0 and action == "BUY":
            success_prob = round(min(0.95, success_prob + theme_boost), 4)
            logger.info(f"[THEME] {rec.code} 테마 활성 보너스: +{theme_boost:.3f} (테마: {active_themes})")

        rationale = {
            **rec.rationale,
            "market_regime":      regime,
            "regime_note":        regime_note,
            "theme_boost":        theme_boost,
            "active_themes":      active_themes,
            "theme_reversal":     theme_reversal,
            "theme_reversal_note": theme_reversal_note,
        }

        return {
            "code":               rec.code,
            "name":               stock_name,
            "market":             stock_market,
            "created_at":         datetime.now(timezone.utc),
            "action":             action,
            "entry_price":        rec.entry_price,
            "entry_price_low":    rec.entry_price_low,
            "entry_price_high":   rec.entry_price_high,
            "target_price":       rec.target_price,
            "stop_loss_price":    rec.stop_loss_price,
            "expected_hold_days": rec.expected_hold_days,
            "success_prob":       success_prob,
            "expected_return":    rec.expected_return,
            "risk_score":         rec.risk_score,
            "risk_reward_ratio":  rec.risk_reward_ratio,
            "rationale":          rationale,
            "similar_cases":      rec.similar_cases,
        }

    async def _save_feature_event(self, event: dict) -> int | None:
        code = event.get("code", "")
        if not code:
            return None
        signal_data = event.get("signal_data") or {}
        try:
            detected_at = datetime.fromisoformat(event.get("detected_at", datetime.now().isoformat()))
            event_type  = event.get("event_type", "UNKNOWN")
            async with self._db.acquire() as conn:
                # 중복 체크 후 INSERT (text vs varchar 타입 추론 충돌 방지를 위해 분리)
                exists = await conn.fetchval(
                    """
                    SELECT id FROM feature_events
                    WHERE code       = $1
                      AND event_type = $2
                      AND detected_at >= DATE_TRUNC('day', $3::timestamptz)
                      AND detected_at <  DATE_TRUNC('day', $3::timestamptz) + INTERVAL '1 day'
                    ORDER BY id DESC LIMIT 1
                    """,
                    code, event_type, detected_at,
                )
                if exists is not None:
                    event_id = exists
                else:
                    event_id = await conn.fetchval(
                        """
                        INSERT INTO feature_events (
                            code, detected_at, event_type, price, change_rate,
                            volume, volume_ratio, amount, signal_score, risk_score,
                            signal_data
                        )
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                        RETURNING id
                        """,
                        code,
                        detected_at,
                        event_type,
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
            # BUY 신호 확정 시 성과 추적 초기 row 등록
            # telegram:config Redis 키의 실효 임계값과 동기화
            if rec_id and rec.get("action") == "BUY":
                perf_max_risk = float(os.environ.get("REC_MAX_RISK", "0.60"))
                perf_min_rr   = float(os.environ.get("REC_MIN_RISK_REWARD", "2.0"))
                # telegram:config 에 설정된 min_prob 를 우선 사용 (없으면 env 기본값)
                _tg_cfg_raw = await self._redis.get("telegram:config")
                if _tg_cfg_raw:
                    try:
                        import orjson as _oj
                        _tg_cfg = _oj.loads(_tg_cfg_raw)
                        perf_min_prob = float(_tg_cfg.get("min_prob", os.environ.get("REC_PERF_MIN_PROB", "0.55")))
                        perf_max_risk = float(_tg_cfg.get("max_risk", perf_max_risk))
                        perf_min_rr   = float(_tg_cfg.get("min_risk_reward", perf_min_rr))
                    except Exception:
                        perf_min_prob = float(os.environ.get("REC_PERF_MIN_PROB", "0.55"))
                else:
                    perf_min_prob = float(os.environ.get("REC_PERF_MIN_PROB", "0.55"))
                if (
                    rec.get("success_prob", 0)      >= perf_min_prob
                    and rec.get("risk_score", 1)    <= perf_max_risk
                    and rec.get("risk_reward_ratio", 0) >= perf_min_rr
                ):
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
                        f"risk={rec.get('risk_score',0):.3f} rr={rec.get('risk_reward_ratio',0):.2f} "
                        f"(thresholds: prob>={perf_min_prob} risk<={perf_max_risk} rr>={perf_min_rr})"
                    )

    async def _publish_redis(self, rec: dict):
        await self._redis.publish(
            "channel:recommendations",
            orjson.dumps(rec).decode(),
        )


if __name__ == "__main__":
    asyncio.run(RecommenderService().run())
