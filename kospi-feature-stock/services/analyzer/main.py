import asyncio
import logging
import os
import asyncpg
import orjson
import redis.asyncio as redis_lib
from datetime import datetime
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from disclosure.classifier import DisclosureClassifier
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
        self.classifier = DisclosureClassifier()
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

        clf     = self.classifier.classify(title, content)
        amount, amount_text = self.classifier.extract_amount(f"{title} {content}")
        counterparty = self.classifier.extract_counterparty(content)
        period       = self.classifier.extract_contract_period(content)
        embedding    = self.embedder.encode_disclosure(title, content)
        vec_str = "[" + ",".join(f"{v:.6f}" for v in embedding.tolist()) + "]"

        # KR-FinBERT 감성 점수 (keyword 분류 fallback)
        try:
            bert = news_sentiment(title, content)
            sentiment_score = bert["sentiment_score"]
        except Exception:
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


if __name__ == "__main__":
    asyncio.run(AnalyzerService().run())