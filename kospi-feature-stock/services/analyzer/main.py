import asyncio
import logging
import os
import asyncpg
import orjson
import redis.asyncio as redis_lib
from datetime import datetime, timedelta, timezone
from disclosure.classifier import DisclosureClassifier, DisclosureBERTClassifier
from embedding.embedder import LocalEmbedder
from news.sentiment import analyze as news_sentiment

_NEWS_SENTIMENT_TTL = int(os.environ.get("NEWS_SENTIMENT_TTL", "604800"))  # 7일

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("analyzer")


def _calc_relevance(title: str, content: str, code: str, name: str) -> float:
    """종목명/코드 언급 빈도와 위치 기반 관련도 점수 산출 (0.0 ~ 1.0)."""
    if not name:
        return 0.5
    text = title + " " + content
    title_hit  = name in title or code in title
    content_cnt = text.count(name) + text.count(code)

    # 제목 언급: 0.7 기본, 본문 추가 언급당 +0.05 (최대 0.95)
    if title_hit:
        return min(0.95, 0.70 + content_cnt * 0.05)
    # 본문만: 언급 횟수 기반
    if content_cnt >= 3:
        return 0.60
    if content_cnt >= 1:
        return 0.45
    return 0.20


_STOCK_NAME_MAP: dict[str, str] = {}  # {종목명: code} 인메모리 캐시
_STOCK_NAME_MAP_LOADED_AT: datetime | None = None
_STOCK_NAME_MAP_TTL = 3600  # 1시간마다 갱신


async def _get_stock_name_map(db: asyncpg.Pool) -> dict[str, str]:
    """종목명 → 코드 매핑 (1시간 캐시). 1:N 뉴스-종목 링크에 사용."""
    global _STOCK_NAME_MAP, _STOCK_NAME_MAP_LOADED_AT
    now = datetime.now(timezone.utc)
    if _STOCK_NAME_MAP and _STOCK_NAME_MAP_LOADED_AT:
        age = (now - _STOCK_NAME_MAP_LOADED_AT).total_seconds()
        if age < _STOCK_NAME_MAP_TTL:
            return _STOCK_NAME_MAP
    try:
        rows = await db.fetch("SELECT code, name FROM stocks WHERE is_active = TRUE AND LENGTH(name) >= 2")
        _STOCK_NAME_MAP = {r["name"]: r["code"] for r in rows if r["name"]}
        _STOCK_NAME_MAP_LOADED_AT = now
    except Exception as e:
        logger.warning(f"[StockNameMap] load error: {e}")
    return _STOCK_NAME_MAP


def _extract_mentioned_codes(
    title: str, content: str, primary_code: str, name_map: dict[str, str]
) -> list[tuple[str, float]]:
    """뉴스 본문에서 언급된 종목 코드를 추출해 (code, relevance) 목록 반환.
    최대 5개, primary_code를 제외한 추가 종목만 포함.
    """
    text = title + " " + content[:2000]
    results: list[tuple[str, float]] = []
    seen: set[str] = {primary_code}
    for name, code in name_map.items():
        if code in seen:
            continue
        if name not in text:
            continue
        seen.add(code)
        rel = _calc_relevance(title, content, code, name)
        results.append((code, rel))
        if len(results) >= 4:  # primary 포함 최대 5개
            break
    return results


class AnalyzerService:

    def __init__(self):
        self._db: asyncpg.Pool | None = None
        self._redis: redis_lib.Redis | None = None
        self.classifier      = DisclosureClassifier()
        self.bert_classifier = DisclosureBERTClassifier()
        self.embedder   = LocalEmbedder(
            model_name=os.environ.get("EMBEDDING_MODEL_NAME", "jhgan/ko-sroberta-multitask"),
            cache_dir=os.environ.get("MODEL_CACHE_DIR", "/models"),
        )

    async def run(self):
        if not os.environ.get("POSTGRES_DSN"):
            raise RuntimeError("Missing required env var: POSTGRES_DSN")
        if not os.environ.get("REDIS_URL"):
            raise RuntimeError("Missing required env var: REDIS_URL")

        self._db = await asyncpg.create_pool(
            dsn=os.environ["POSTGRES_DSN"].replace("+asyncpg", ""),
            min_size=3, max_size=10,
        )
        self._redis = redis_lib.from_url(os.environ["REDIS_URL"])
        logger.info("Analyzer service started")

        await asyncio.gather(
            self._consume_topic("disclosure", self._process_disclosure),
            self._consume_topic("news",       self._process_news),
            self._theme_cluster_loop(),
            self._theme_snapshot_loop(),
            self._post_change_updater_loop(),
        )

    async def _consume_topic(self, topic: str, handler):
        """단일 토픽 Redis 구독 — 오류 시 5초 후 재연결."""
        while True:
            pubsub = self._redis.pubsub()
            try:
                await pubsub.subscribe(f"ch:{topic}")
                logger.info(f"[Analyzer] '{topic}' Redis subscriber started")
                async for msg in pubsub.listen():
                    if msg["type"] != "message":
                        continue
                    try:
                        await handler(orjson.loads(msg["data"]))
                    except Exception as e:
                        logger.error(f"[Analyzer] Process error [{topic}]: {e}")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"[Analyzer] '{topic}' subscriber failed: {e} — reconnecting in 5s")
                await asyncio.sleep(5)
            finally:
                try:
                    await pubsub.unsubscribe()
                    await pubsub.aclose()
                except Exception:
                    pass

    async def _theme_snapshot_loop(self):
        """매일 18:00 KST 테마 스냅샷 자동 저장."""
        KST = timezone(timedelta(hours=9))
        while True:
            now = datetime.now(KST)
            target = now.replace(hour=18, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait = (target - now).total_seconds()
            logger.info(f"[ThemeSnapshot] 다음 실행까지 {wait:.0f}초 대기 (18:00 KST)")
            await asyncio.sleep(wait)

            try:
                today = datetime.now(KST).date()
                rows = await self._db.fetch(
                    """
                    SELECT
                        theme_name,
                        COUNT(DISTINCT fe.code) AS stock_count,
                        ROUND(AVG(fe.result_1d)::NUMERIC, 4) AS avg_return,
                        STRING_AGG(DISTINCT fe.code, ',' ORDER BY fe.code) AS top_codes
                    FROM (
                        SELECT fe.code, fe.result_1d,
                               jsonb_array_elements_text(n.themes::jsonb) AS theme_name
                        FROM feature_events fe
                        JOIN news_stock_links nsl ON nsl.code = fe.code
                        JOIN news n ON n.id = nsl.news_id
                        WHERE fe.detected_at::date = $1
                          AND n.themes IS NOT NULL AND n.themes != '[]'
                    ) sub
                    GROUP BY theme_name
                    HAVING COUNT(DISTINCT code) >= 2
                    """,
                    today,
                )
                saved = 0
                for row in rows:
                    try:
                        await self._db.execute(
                            """
                            INSERT INTO theme_snapshots (theme_name, snap_date, stock_count, avg_return, top_codes)
                            VALUES ($1, $2, $3, $4, $5)
                            ON CONFLICT (theme_name, snap_date) DO UPDATE
                              SET stock_count = EXCLUDED.stock_count,
                                  avg_return  = EXCLUDED.avg_return,
                                  top_codes   = EXCLUDED.top_codes
                            """,
                            row["theme_name"], today,
                            int(row["stock_count"]), row["avg_return"], row["top_codes"],
                        )
                        saved += 1
                    except Exception as e:
                        logger.warning(f"[ThemeSnapshot] save error {row['theme_name']}: {e}")
                logger.info(f"[ThemeSnapshot] {today} 저장 완료: {saved}건")
            except Exception as e:
                logger.error(f"[ThemeSnapshot] 실행 오류: {e}")

    async def _theme_cluster_loop(self):
        """1시간마다 뉴스 테마 클러스터링 실행."""
        await asyncio.sleep(300)  # 서비스 기동 5분 후 첫 실행
        while True:
            try:
                if self._redis:
                    from news.theme_clusterer import ThemeClusterer
                    tc = ThemeClusterer(db_pool=self._db, redis_client=self._redis)
                    themes = await tc.run()
                    logger.info(f"Theme clustering completed: {len(themes)} themes")
                else:
                    logger.warning("Theme clustering skipped: Redis not connected")
            except Exception as e:
                logger.error(f"Theme clustering error: {e}")
            await asyncio.sleep(3600)  # 1시간

    async def _process_disclosure(self, data: dict):
        rcept_no = data.get("rcept_no")
        if not rcept_no:
            return

        title   = data.get("title", "")
        # DART 폴러는 'content' 대신 'body_preview'로 본문 일부를 전달함
        content = data.get("content", "") or data.get("body_preview", "")

        # disclosed_at: DART는 'YYYYMMDD' 혹은 KST isoformat, KIND는 KST isoformat
        # naive datetime은 모두 KST로 해석 (UTC로 해석하면 +9h 오차 발생)
        _KST_LOC = timezone(timedelta(hours=9))
        raw_dt = data.get("disclosed_at", "")
        try:
            if raw_dt and len(raw_dt) == 8 and raw_dt.isdigit():
                # DART 날짜만 제공 — 정확한 시각 미상이므로 처리 시각 사용
                disclosed_dt = datetime.now(_KST_LOC)
            elif raw_dt:
                dt = datetime.fromisoformat(raw_dt)
                disclosed_dt = dt if dt.tzinfo else dt.replace(tzinfo=_KST_LOC)
                # 자정(00:00) 수집 시각: DART 시스템 공시 자정 게시 아티팩트 → 처리 시각 사용
                if disclosed_dt.hour == 0 and disclosed_dt.minute == 0:
                    disclosed_dt = datetime.now(_KST_LOC)
            else:
                disclosed_dt = datetime.now(_KST_LOC)
        except Exception:
            disclosed_dt = datetime.now(_KST_LOC)

        clf     = self.bert_classifier.classify(title, content, data.get("disclosure_type", ""))
        amount, amount_text = self.classifier.extract_amount(f"{title} {content}")
        counterparty = self.classifier.extract_counterparty(content)
        period       = self.classifier.extract_contract_period(content)
        embedding    = self.embedder.encode_disclosure(title, content)
        vec_str = "[" + ",".join(f"{v:.6f}" for v in embedding.tolist()) + "]"

        sentiment_score = clf["sentiment_score"]

        async with self._db.acquire() as conn:
            # KIND 공시: corp_name으로 종목코드 조회 (code=None)
            resolved_code = data.get("code")
            if not resolved_code and data.get("corp_name"):
                row_code = await conn.fetchrow(
                    "SELECT code FROM stocks WHERE name = $1 LIMIT 1",
                    data["corp_name"],
                )
                if row_code:
                    resolved_code = row_code["code"]

            await conn.execute(
                """
                INSERT INTO disclosures (
                    rcept_no, code, corp_name, disclosed_at,
                    report_type, disclosure_type, title,
                    category, sentiment_score, amount, amount_text,
                    contract_amount,
                    keywords, counterparty, contract_period,
                    embedding, raw_json
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16::vector,$17)
                ON CONFLICT (rcept_no) DO UPDATE SET
                    code            = COALESCE(EXCLUDED.code, disclosures.code),
                    category        = EXCLUDED.category,
                    sentiment_score = EXCLUDED.sentiment_score,
                    keywords        = EXCLUDED.keywords,
                    embedding       = EXCLUDED.embedding,
                    amount          = COALESCE(EXCLUDED.amount,           disclosures.amount),
                    amount_text     = COALESCE(EXCLUDED.amount_text,      disclosures.amount_text),
                    contract_amount = COALESCE(EXCLUDED.contract_amount,  disclosures.contract_amount),
                    counterparty    = COALESCE(EXCLUDED.counterparty,     disclosures.counterparty),
                    contract_period = COALESCE(EXCLUDED.contract_period,  disclosures.contract_period)
                """,
                rcept_no,
                resolved_code,
                data.get("corp_name"),
                disclosed_dt,
                data.get("report_type"),
                data.get("disclosure_type") or clf["category"],
                title,
                clf["category"],
                sentiment_score,
                amount or None,
                amount_text or None,
                amount or None,          # contract_amount = amount (동일 추출값)
                orjson.dumps(clf["keywords"]).decode(),
                counterparty or None,
                period or None,
                vec_str,
                orjson.dumps(data).decode(),
            )
            # is_flagged: 등록된 keyword 필터와 제목 매칭
            await conn.execute(
                """
                UPDATE disclosures SET is_flagged = (
                    EXISTS (
                        SELECT 1 FROM disclosure_filters
                        WHERE type = 'keyword'
                          AND $1 ILIKE '%' || value || '%'
                    )
                ) WHERE rcept_no = $2 AND is_flagged = FALSE
                """,
                title, rcept_no,
            )
        logger.info(f"Disclosure saved: {rcept_no} [{clf['category']}]")

        # disclosure-analyzed 채널에 발행: notifier가 소비
        analyzed = {
            "rcept_no":        rcept_no,
            "code":            resolved_code,
            "corp_name":       data.get("corp_name"),
            "title":           title,
            "report_type":     data.get("report_type"),
            "category":        clf["category"],
            "sentiment_score": sentiment_score,
            "keywords":        clf["keywords"],
            "disclosed_at":    disclosed_dt.isoformat(),
        }
        await self._redis.publish("ch:disclosure-analyzed", orjson.dumps(analyzed).decode())

    async def _process_news(self, data: dict):
        title   = data.get("title", "")
        content = data.get("content", "")
        if not title:
            return

        # published_at: 문자열 → datetime 변환
        raw_pub = data.get("published_at", "")
        try:
            if raw_pub and isinstance(raw_pub, str):
                pub_dt = datetime.fromisoformat(raw_pub[:19])
            elif isinstance(raw_pub, datetime):
                pub_dt = raw_pub
            else:
                pub_dt = datetime.now()
        except Exception:
            pub_dt = datetime.now()

        # 감성 분석
        sentiment = news_sentiment(title, content)

        embedding = self.embedder.encode_disclosure(title, content)
        vec_str   = "[" + ",".join(f"{v:.6f}" for v in embedding.tolist()) + "]"

        async with self._db.acquire() as conn:
            news_id = await conn.fetchval(
                """
                INSERT INTO news (source, published_at, title, content, url,
                    themes, sentiment_score, embedding)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8::vector)
                ON CONFLICT (url) WHERE url IS NOT NULL DO NOTHING
                RETURNING id
                """,
                data.get("source"),
                pub_dt,
                title,
                content,
                data.get("url"),
                orjson.dumps(data.get("themes") or []).decode(),
                sentiment["sentiment_score"],
                vec_str,
            )
            if news_id and data.get("code"):
                primary_code = data["code"]
                relevance = _calc_relevance(title, content, primary_code, data.get("name", ""))
                await conn.execute(
                    """
                    INSERT INTO news_stock_links (news_id, code, relevance)
                    VALUES ($1, $2, $3) ON CONFLICT DO NOTHING
                    """,
                    news_id, primary_code, relevance,
                )
                # 1:N — 본문 내 추가 종목 자동 링크
                try:
                    name_map = await _get_stock_name_map(self._db)
                    extra = _extract_mentioned_codes(title, content, primary_code, name_map)
                    for ex_code, ex_rel in extra:
                        await conn.execute(
                            "INSERT INTO news_stock_links (news_id, code, relevance) "
                            "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                            news_id, ex_code, ex_rel,
                        )
                except Exception as e:
                    logger.debug(f"[NewsLink 1:N] {e}")
        logger.debug(f"News saved: {title[:40]} sentiment={sentiment['sentiment_score']}")

        # 종목별 뉴스 감성 집계를 Redis에 저장 (ML 피처용)
        code = data.get("code")
        if code and self._redis:
            await self._update_news_sentiment_redis(code, sentiment["sentiment_score"])

    async def _update_news_sentiment_redis(self, code: str, score: float):
        key = f"news:sentiment:{code}"
        try:
            raw = await self._redis.get(key)
            if raw:
                prev = orjson.loads(raw)
                n = prev.get("count", 0) + 1
                avg = (prev.get("avg_sentiment", 0.0) * (n - 1) + score) / n
            else:
                n, avg = 1, score
            await self._redis.set(
                key,
                orjson.dumps({"avg_sentiment": round(avg, 4), "count": n}),
                ex=_NEWS_SENTIMENT_TTL,
            )
        except Exception as e:
            logger.debug(f"news sentiment redis update failed {code}: {e}")


    async def _post_change_updater_loop(self):
        """매 시간 공시 사후 수익률(post_1h/1d/3d_change)을 자동 채운다.

        disclosed_at 기준:
          - post_1h_change: 공시 후 1시간 시점 tick_data 가격 vs 공시 당시 종가
          - post_1d_change: 공시 다음 거래일 종가 vs 당일 종가
          - post_3d_change: 공시 후 3거래일 종가 vs 당일 종가
        """
        await asyncio.sleep(120)  # 기동 2분 후 첫 실행
        while True:
            try:
                await self._fill_post_changes()
            except Exception as e:
                logger.error(f"[PostChange] 업데이트 오류: {e}")
            await asyncio.sleep(3600)

    async def _fill_post_changes(self):
        rows = await self._db.fetch(
            """
            SELECT d.rcept_no, d.code,
                   d.disclosed_at::date AS disc_date,
                   d.disclosed_at       AS disc_ts,
                   d.post_1h_change,
                   d.post_1d_change,
                   d.post_3d_change
            FROM disclosures d
            WHERE d.code IS NOT NULL
              AND d.disclosed_at >= NOW() - INTERVAL '90 days'
              AND d.disclosed_at < NOW() - INTERVAL '2 hours'
              AND (d.post_1h_change IS NULL OR d.post_1d_change IS NULL OR d.post_3d_change IS NULL)
            ORDER BY d.disclosed_at ASC
            LIMIT 500
            """,
        )
        if not rows:
            return

        updated = 0
        for row in rows:
            code      = row["code"]
            disc_date = row["disc_date"]
            disc_ts   = row["disc_ts"]
            rcept_no  = row["rcept_no"]

            # ── post_1h_change: tick_data 기반 (공시 후 1시간) ─────────
            chg_1h = None
            if row["post_1h_change"] is None:
                try:
                    target_ts = disc_ts + timedelta(hours=1)
                    base_row = await self._db.fetchrow(
                        """SELECT price FROM tick_data
                           WHERE code=$1 AND time <= $2
                           ORDER BY time DESC LIMIT 1""",
                        code, disc_ts,
                    )
                    after_row = await self._db.fetchrow(
                        """SELECT price FROM tick_data
                           WHERE code=$1 AND time >= $2 AND time <= $3
                           ORDER BY time ASC LIMIT 1""",
                        code, disc_ts, target_ts,
                    )
                    if base_row and after_row:
                        bp = float(base_row["price"])
                        ap = float(after_row["price"])
                        if bp > 0:
                            chg_1h = round((ap - bp) / bp * 100, 2)
                except Exception as e:
                    logger.debug(f"[PostChange] 1h tick 조회 실패 {code}: {e}")

            # ── post_1d/3d_change: daily_bars 기반 ─────────────────────
            chg_1d = None
            chg_3d = None
            if row["post_1d_change"] is None or row["post_3d_change"] is None:
                bars = await self._db.fetch(
                    """
                    SELECT date::TEXT, close
                    FROM daily_bars
                    WHERE code = $1
                      AND date BETWEEN $2 AND ($2 + INTERVAL '10 days')::date
                    ORDER BY date ASC
                    LIMIT 6
                    """,
                    code, disc_date,
                )
                if len(bars) >= 2:
                    base_close = float(bars[0]["close"])
                    if base_close > 0:
                        post_1d = float(bars[1]["close"]) if len(bars) > 1 else None
                        post_3d = float(bars[3]["close"]) if len(bars) > 3 else None
                        chg_1d = round((post_1d - base_close) / base_close * 100, 2) if post_1d else None
                        chg_3d = round((post_3d - base_close) / base_close * 100, 2) if post_3d else None

            if chg_1h is None and chg_1d is None and chg_3d is None:
                continue

            await self._db.execute(
                """
                UPDATE disclosures
                   SET post_1h_change = COALESCE($2, post_1h_change),
                       post_1d_change = COALESCE($3, post_1d_change),
                       post_3d_change = COALESCE($4, post_3d_change)
                 WHERE rcept_no = $1
                """,
                rcept_no, chg_1h, chg_1d, chg_3d,
            )
            updated += 1

        if updated:
            logger.info(f"[PostChange] {updated}건 post_1h/1d/3d_change 업데이트 완료")


if __name__ == "__main__":
    asyncio.run(AnalyzerService().run())