"""
뉴스 + DART 공시 수집 워커 (DB 직접 저장 모드).

기존 흐름: news_worker → ch:news → analyzer → DB
          (analyzer가 배포되지 않으면 news 테이블에 아무것도 저장되지 않음)

수정된 흐름: news_worker → DB 직접 저장
  - embedding: NULL (sentence-transformers 미설치 환경 대응)
  - sentiment: 경량 키워드 기반 (BERT 불필요)
  - DART 공시: 기존 _write_to_db 로직 그대로 사용
"""
import asyncio
import logging
import os
import sys
from datetime import datetime

import asyncpg
import orjson

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import StockCollector, load_active_stocks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger("collector-news")

NEWS_INTERVAL = int(os.environ.get("NEWS_INTERVAL_SEC", "1800"))

# 경량 키워드 감성 분석 (BERT 없이, analyzer/news/sentiment.py의 subset)
_POS = {
    "급등": 0.35, "신고가": 0.35, "수주": 0.28, "흑자전환": 0.30,
    "상승": 0.15, "호실적": 0.22, "실적개선": 0.22, "목표주가상향": 0.20,
    "공급계약": 0.20, "수출": 0.15, "특허": 0.15, "성장": 0.12,
    "MOU": 0.08, "긍정적": 0.08, "호조": 0.10,
}
_NEG = {
    "급락": -0.35, "하한가": -0.40, "횡령": -0.45, "상장폐지": -0.50,
    "부도": -0.45, "파산": -0.45, "관리종목": -0.40, "하락": -0.15,
    "실적부진": -0.22, "목표주가하향": -0.20, "유상증자": -0.20,
    "전환사채": -0.15, "적자": -0.18, "감소": -0.10, "우려": -0.10,
}


def _keyword_sentiment(title: str, content: str = "") -> float:
    text = title + " " + title + " " + content[:500]  # 제목 2배 가중
    score = sum(w for kw, w in _POS.items() if kw in text)
    score += sum(w for kw, w in _NEG.items() if kw in text)
    return round(max(-1.0, min(1.0, score)), 3)


async def _save_news_to_db(db: asyncpg.Pool, item: dict, seen: set) -> bool:
    """뉴스 1건을 news + news_stock_links 테이블에 직접 저장."""
    url = item.get("url") or None
    if url and url in seen:
        return False
    title = item.get("title", "").strip()
    if not title:
        return False

    raw_pub = item.get("published_at", "")
    try:
        pub_dt = datetime.fromisoformat(str(raw_pub)[:19]) if raw_pub else datetime.now()
    except Exception:
        pub_dt = datetime.now()

    sentiment = _keyword_sentiment(title, item.get("content", ""))
    themes = item.get("themes") or []

    try:
        async with db.acquire() as conn:
            news_id = await conn.fetchval(
                """
                INSERT INTO news (source, published_at, title, content, url, themes, sentiment_score)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
                ON CONFLICT (url) WHERE url IS NOT NULL DO NOTHING
                RETURNING id
                """,
                item.get("source", "unknown"),
                pub_dt,
                title,
                item.get("content", ""),
                url,
                orjson.dumps(themes).decode(),
                sentiment,
            )
            if news_id and item.get("code"):
                await conn.execute(
                    "INSERT INTO news_stock_links (news_id, code, relevance) "
                    "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                    news_id, item["code"], 0.7,
                )
        if url:
            seen.add(url)
        return bool(news_id)
    except Exception as e:
        logger.warning(f"[NewsDB] 저장 실패: {e}")
        return False


async def _news_db_loop(svc: StockCollector, codes: list[str]) -> None:
    """활성 종목 뉴스를 수집해 DB에 직접 저장 (analyzer 불필요)."""
    stock_names: dict[str, str] = {}
    try:
        async with svc.db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT code, name FROM stocks WHERE code = ANY($1::text[])", codes
            )
            stock_names = {r["code"]: r["name"] for r in rows}
    except Exception as e:
        logger.warning(f"[NewsDB] 종목명 로드 실패: {e}")

    seen: set = set()
    total = 0

    while True:
        await asyncio.sleep(NEWS_INTERVAL)  # NEWS_INTERVAL_SEC=0 → 즉시 실행
        saved = 0
        for code in codes:
            name = stock_names.get(code, code)
            try:
                items = await svc.news.crawl_stock_news(code, name)
                if not items:
                    items = await svc.news_rss.crawl_stock_news(code, name)
                for it in items:
                    it["code"] = code  # 종목 코드 보강
                    if await _save_news_to_db(svc.db, it, seen):
                        saved += 1
            except Exception as e:
                logger.debug(f"[NewsDB] {code} 뉴스 수집 오류: {e}")
            await asyncio.sleep(0.5)

        if saved:
            total += saved
            logger.info(f"[NewsDB] {saved}건 저장 (누적 {total}건)")

        if NEWS_INTERVAL == 0:
            logger.info("[NewsDB] 1회 실행 완료 (NEWS_INTERVAL_SEC=0)")
            break


async def run():
    svc = StockCollector()
    await svc.setup()
    active_codes = await load_active_stocks(svc.redis)
    logger.info(f"[news] {len(active_codes)}개 활성 종목 — DB 직접 저장 모드")

    await asyncio.gather(
        _news_db_loop(svc, active_codes),
        svc.dart.run(),          # DART 공시 → disclosures 테이블 직접 저장
        return_exceptions=True,
    )


if __name__ == "__main__":
    asyncio.run(run())
