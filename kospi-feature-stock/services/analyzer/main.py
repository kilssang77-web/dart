import asyncio
import logging
import os
import asyncpg
import orjson
import redis.asyncio as redis_lib
from datetime import datetime, timedelta, timezone
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
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


class AnalyzerService:

    def __init__(self):
        self._db: asyncpg.Pool | None = None
        self._redis: redis_lib.Redis | None = None
        self._producer: AIOKafkaProducer | None = None
        self.classifier      = DisclosureClassifier()
        self.bert_classifier = DisclosureBERTClassifier()
        self.embedder   = LocalEmbedder(
            model_name=os.environ.get("EMBEDDING_MODEL_NAME", "jhgan/ko-sroberta-multitask"),
            cache_dir=os.environ.get("MODEL_CACHE_DIR", "/models"),
        )

    async def run(self):
        _required = ["POSTGRES_DSN", "KAFKA_BOOTSTRAP_SERVERS"]
        missing = [k for k in _required if not os.environ.get(k)]
        if missing:
            raise RuntimeError(f"Missing required env vars: {missing}")

        self._db = await asyncpg.create_pool(
            dsn=os.environ["POSTGRES_DSN"].replace("+asyncpg", ""),
            min_size=3, max_size=10,
        )
        if os.environ.get("REDIS_URL"):
            self._redis = redis_lib.from_url(os.environ["REDIS_URL"])
        self._producer = AIOKafkaProducer(
            bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            value_serializer=lambda v: orjson.dumps(v),
            key_serializer=lambda k: k.encode() if k else b"",
            compression_type="lz4",
        )
        await self._producer.start()
        logger.info("Analyzer service started")

        try:
            await asyncio.gather(
                self._consume_topic("disclosure", self._process_disclosure),
                self._consume_topic("news",       self._process_news),
                self._theme_cluster_loop(),
                self._theme_snapshot_loop(),
                self._post_change_updater_loop(),
            )
        finally:
            if self._producer:
                await self._producer.stop()

    async def _consume_topic(self, topic: str, handler):
        """단일 토픽 독립 컨슈머 — 오류 시 5초 후 재연결."""
        while True:
            consumer = AIOKafkaConsumer(
                topic,
                bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
                group_id=f"analyzer-{topic}-group",
                value_deserializer=lambda v: orjson.loads(v),
                auto_offset_reset="latest",
            )
            try:
                await consumer.start()
                logger.info(f"[Analyzer] '{topic}' consumer started")
                async for msg in consumer:
                    try:
                        await handler(msg.value)
                    except Exception as e:
                        logger.error(f"[Analyzer] Process error [{topic}]: {e}")
            except Exception as e:
                logger.error(f"[Analyzer] '{topic}' consumer failed: {e} — reconnecting in 5s")
                await asyncio.sleep(5)
            finally:
                try:
                    await consumer.stop()
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
        content = data.get("content", "")

        # disclosed_at: DART는 'YYYYMMDD', KIND는 isoformat — datetime으로 정규화
        raw_dt = data.get("disclosed_at", "")
        try:
            if raw_dt and len(raw_dt) == 8 and raw_dt.isdigit():
                disclosed_dt = datetime.strptime(raw_dt, "%Y%m%d")
            elif raw_dt:
                disclosed_dt = datetime.fromisoformat(raw_dt[:19])
            else:
                disclosed_dt = datetime.now()
        except Exception:
            disclosed_dt = datetime.now()

        clf     = self.bert_classifier.classify(title, content, data.get("disclosure_type", ""))
        amount, amount_text = self.classifier.extract_amount(f"{title} {content}")
        counterparty = self.classifier.extract_counterparty(content)
        period       = self.classifier.extract_contract_period(content)
        embedding    = self.embedder.encode_disclosure(title, content)
        vec_str = "[" + ",".join(f"{v:.6f}" for v in embedding.tolist()) + "]"

        sentiment_score = clf["sentiment_score"]

        async with self._db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO disclosures (
                    rcept_no, code, corp_name, disclosed_at,
                    report_type, disclosure_type, title,
                    category, sentiment_score, amount, amount_text,
                    keywords, counterparty, contract_period,
                    embedding, raw_json
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::vector,$16)
                ON CONFLICT (rcept_no) DO UPDATE SET
                    category       = EXCLUDED.category,
                    sentiment_score= EXCLUDED.sentiment_score,
                    keywords       = EXCLUDED.keywords,
                    embedding      = EXCLUDED.embedding
                """,
                rcept_no,
                data.get("code"),
                data.get("corp_name"),
                disclosed_dt,
                data.get("report_type"),
                data.get("disclosure_type") or clf["category"],
                title,
                clf["category"],
                sentiment_score,
                amount or None,
                amount_text or None,
                orjson.dumps(clf["keywords"]).decode(),
                counterparty or None,
                period or None,
                vec_str,
                orjson.dumps(data).decode(),
            )
        logger.info(f"Disclosure saved: {rcept_no} [{clf['category']}]")

        # disclosure-analyzed 토픽에 발행: notifier가 소비
        if self._producer:
            analyzed = {
                "rcept_no":        rcept_no,
                "code":            data.get("code"),
                "corp_name":       data.get("corp_name"),
                "title":           title,
                "report_type":     data.get("report_type"),
                "category":        clf["category"],
                "sentiment_score": sentiment_score,
                "keywords":        clf["keywords"],
                "disclosed_at":    disclosed_dt.isoformat(),
            }
            await self._producer.send(
                "disclosure-analyzed",
                analyzed,
                key=data.get("code") or "UNKNOWN",
            )

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
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                data.get("source"),
                pub_dt,
                title,
                content,
                data.get("url"),
                orjson.dumps(data.get("themes", [])).decode(),
                sentiment["sentiment_score"],
                vec_str,
            )
            if news_id and data.get("code"):
                relevance = _calc_relevance(title, content, data.get("code", ""), data.get("name", ""))
                await conn.execute(
                    """
                    INSERT INTO news_stock_links (news_id, code, relevance)
                    VALUES ($1, $2, $3) ON CONFLICT DO NOTHING
                    """,
                    news_id, data["code"], relevance,
                )
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
        """매 시간 공시 사후 수익률(post_1d/3d_change)을 daily_bars에서 자동 채운다.

        disclosed_at 기준:
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
                   d.disclosed_at::date AS disc_date
            FROM disclosures d
            WHERE d.code IS NOT NULL
              AND d.disclosed_at >= NOW() - INTERVAL '90 days'
              AND (d.post_1d_change IS NULL OR d.post_3d_change IS NULL)
            ORDER BY d.disclosed_at DESC
            LIMIT 200
            """,
        )
        if not rows:
            return

        updated = 0
        for row in rows:
            code      = row["code"]
            disc_date = row["disc_date"]
            rcept_no  = row["rcept_no"]

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
            if len(bars) < 2:
                continue

            base_close = float(bars[0]["close"])
            if base_close <= 0:
                continue

            post_1d = float(bars[1]["close"]) if len(bars) > 1 else None
            post_3d = float(bars[3]["close"]) if len(bars) > 3 else None

            chg_1d = round((post_1d - base_close) / base_close * 100, 2) if post_1d else None
            chg_3d = round((post_3d - base_close) / base_close * 100, 2) if post_3d else None

            if chg_1d is None and chg_3d is None:
                continue

            await self._db.execute(
                """
                UPDATE disclosures
                   SET post_1d_change = COALESCE($2, post_1d_change),
                       post_3d_change = COALESCE($3, post_3d_change)
                 WHERE rcept_no = $1
                """,
                rcept_no, chg_1d, chg_3d,
            )
            updated += 1

        if updated:
            logger.info(f"[PostChange] {updated}건 post_1d/3d_change 업데이트 완료")


if __name__ == "__main__":
    asyncio.run(AnalyzerService().run())