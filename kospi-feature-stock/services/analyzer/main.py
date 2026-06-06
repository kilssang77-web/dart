import asyncio
import logging
import os
import asyncpg
import orjson
from datetime import datetime
from aiokafka import AIOKafkaConsumer
from disclosure.classifier import DisclosureClassifier
from embedding.embedder import LocalEmbedder
from news.sentiment import analyze as news_sentiment

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
        self.classifier = DisclosureClassifier()
        self.embedder   = LocalEmbedder(
            model_name=os.environ.get("EMBEDDING_MODEL_NAME", "jhgan/ko-sroberta-multitask"),
            cache_dir=os.environ.get("MODEL_CACHE_DIR", "/models"),
        )

    async def run(self):
        self._db = await asyncpg.create_pool(
            dsn=os.environ["POSTGRES_DSN"].replace("+asyncpg", ""),
            min_size=3, max_size=10,
        )
        consumer = AIOKafkaConsumer(
            "disclosure", "news",
            bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            group_id="analyzer-group",
            value_deserializer=lambda v: orjson.loads(v),
            auto_offset_reset="latest",
        )
        await consumer.start()
        logger.info("Analyzer service started")

        try:
            async for msg in consumer:
                data  = msg.value
                topic = msg.topic
                try:
                    if topic == "disclosure":
                        await self._process_disclosure(data)
                    elif topic == "news":
                        await self._process_news(data)
                except Exception as e:
                    logger.error(f"Process error [{topic}]: {e}")
        finally:
            await consumer.stop()

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
                clf["sentiment_score"],
                amount or None,
                amount_text or None,
                orjson.dumps(clf["keywords"]).decode(),
                counterparty or None,
                period or None,
                vec_str,
                orjson.dumps(data).decode(),
            )
        logger.info(f"Disclosure saved: {rcept_no} [{clf['category']}]")

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


if __name__ == "__main__":
    asyncio.run(AnalyzerService().run())
