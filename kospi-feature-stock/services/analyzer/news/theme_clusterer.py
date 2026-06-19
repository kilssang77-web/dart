"""
동적 테마 클러스터링 엔진.

하드코딩 키워드 없이 뉴스 임베딩 벡터를 K-Means 클러스터링하여
테마를 자동 발견하고 테마 확산을 추적한다.

사용 흐름:
  1. 최근 7일 뉴스 임베딩을 DB에서 로드
  2. K-Means (또는 HDBSCAN) 클러스터링
  3. 클러스터별 대표 키워드 추출 (TF-IDF)
  4. 클러스터 크기 시계열로 테마 확산 추적
  5. 결과를 Redis에 캐시 (TTL: 6시간)
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
import numpy as np
import redis.asyncio as redis_lib
import orjson

logger = logging.getLogger(__name__)

_kiwi_instance = None

def _get_kiwi():
    global _kiwi_instance
    if _kiwi_instance is None:
        from kiwipiepy import Kiwi  # type: ignore
        _kiwi_instance = Kiwi()
    return _kiwi_instance

_N_CLUSTERS   = int(os.environ.get("THEME_N_CLUSTERS",    "30"))
_MIN_NEWS_PER_CLUSTER = int(os.environ.get("THEME_MIN_NEWS", "5"))
_LOOKBACK_DAYS = int(os.environ.get("THEME_LOOKBACK_DAYS", "7"))
_CACHE_TTL     = int(os.environ.get("THEME_CACHE_TTL_SEC", "21600"))  # 6시간


@dataclass
class Theme:
    cluster_id: int
    keywords: list[str]
    news_count: int
    stock_codes: list[str]
    centroid: Optional[np.ndarray] = None
    trend: str = "stable"          # rising / falling / stable
    count_3d: int = 0
    count_7d: int = 0


class ThemeClusterer:

    def __init__(self, db_pool: asyncpg.Pool, redis_client: redis_lib.Redis):
        self.db    = db_pool
        self.redis = redis_client

    async def run(self) -> list[Theme]:
        """테마 클러스터링 실행 후 결과 반환 및 Redis 캐시."""
        since = datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)

        rows = await self._load_news_embeddings(since)
        if len(rows) < _N_CLUSTERS * 2:
            logger.warning(f"[ThemeCluster] 뉴스 부족 ({len(rows)}건) — 클러스터링 스킵")
            return []

        ids       = [r["id"] for r in rows]
        titles    = [r["title"] for r in rows]
        contents  = [r["content"] or "" for r in rows]
        published = [r["published_at"] for r in rows]
        vecs_raw  = [r["embedding"] for r in rows]

        # pgvector 반환 타입을 numpy로 변환
        vecs = np.array([self._parse_vec(v) for v in vecs_raw], dtype=np.float32)

        # 유효하지 않은 행 제거
        valid = ~np.isnan(vecs).any(axis=1)
        vecs, ids, titles, contents, published = (
            vecs[valid], [x for x, v in zip(ids, valid) if v],
            [x for x, v in zip(titles, valid) if v],
            [x for x, v in zip(contents, valid) if v],
            [x for x, v in zip(published, valid) if v],
        )

        if len(vecs) < _N_CLUSTERS:
            logger.warning("[ThemeCluster] 유효 임베딩 부족")
            return []

        # K-Means 클러스터링
        labels, centroids = self._kmeans(vecs, n_clusters=_N_CLUSTERS)

        # 클러스터별 분석
        themes = []
        for cid in range(_N_CLUSTERS):
            mask = labels == cid
            if mask.sum() < _MIN_NEWS_PER_CLUSTER:
                continue

            cluster_titles   = [t for t, m in zip(titles, mask) if m]
            cluster_contents = [c for c, m in zip(contents, mask) if m]
            cluster_dates    = [d for d, m in zip(published, mask) if m]

            keywords = self._extract_keywords(cluster_titles, cluster_contents, top_k=8)

            # 연결 종목 조회 (news_stock_links)
            cluster_ids = [i for i, m in zip(ids, mask) if m]
            stock_codes = await self._get_linked_stocks(cluster_ids)

            # 확산 추이: 최근 3일 vs 7일 뉴스 수
            now = datetime.now(timezone.utc)
            count_3d = sum(1 for d in cluster_dates if d and (now - d).days <= 3)
            count_7d = mask.sum()
            trend = "rising" if count_3d > count_7d * 0.6 else (
                "falling" if count_3d < count_7d * 0.25 else "stable"
            )

            themes.append(Theme(
                cluster_id=cid,
                keywords=keywords,
                news_count=int(mask.sum()),
                stock_codes=stock_codes[:10],
                centroid=centroids[cid],
                trend=trend,
                count_3d=count_3d,
                count_7d=count_7d,
            ))

        # 뉴스 많은 순으로 정렬
        themes.sort(key=lambda t: t.news_count, reverse=True)

        # Redis 캐시
        await self._cache_themes(themes)

        # DB 스냅쌏 저장 (momentum 포함)
        try:
            await self._save_snapshots_with_momentum(themes)
        except Exception as e:
            logger.warning(f"[ThemeCluster] 스냅쌏 저장 실패: {e}")

        logger.info(f"[ThemeCluster] {len(themes)}개 테마 발견 (총 {len(vecs)}건 뉴스)")
        return themes

    async def _load_news_embeddings(self, since: datetime) -> list:
        return await self.db.fetch(
            """
            SELECT id, title, content, published_at, embedding
            FROM news
            WHERE published_at >= $1
              AND embedding IS NOT NULL
            ORDER BY published_at DESC
            LIMIT 5000
            """,
            since,
        )

    def _parse_vec(self, raw) -> np.ndarray:
        """asyncpg가 반환하는 vector 타입 → numpy 변환."""
        try:
            if isinstance(raw, str):
                vals = raw.strip("[]").split(",")
                return np.array([float(v) for v in vals], dtype=np.float32)
            if hasattr(raw, "__iter__"):
                return np.array(list(raw), dtype=np.float32)
        except Exception:
            pass
        return np.full(768, np.nan, dtype=np.float32)

    def _kmeans(self, X: np.ndarray, n_clusters: int) -> tuple[np.ndarray, np.ndarray]:
        try:
            from sklearn.cluster import MiniBatchKMeans
            from sklearn.preprocessing import normalize
            X_norm = normalize(X)
            km = MiniBatchKMeans(
                n_clusters=n_clusters,
                random_state=42,
                n_init=3,
                batch_size=min(1024, len(X)),
            )
            labels = km.fit_predict(X_norm)
            return labels, km.cluster_centers_
        except Exception as e:
            logger.error(f"[ThemeCluster] K-Means 실패: {e}")
            return np.zeros(len(X), dtype=int), np.zeros((n_clusters, X.shape[1]))

    def _extract_keywords(
        self, titles: list[str], contents: list[str], top_k: int = 8
    ) -> list[str]:
        """형태소 분석 기반 명사 추출 (kiwipiepy 우선, regex fallback)."""
        import re
        from collections import Counter

        stopwords = {
            "및", "이", "가", "을", "를", "에", "의", "는", "은", "로", "으로",
            "에서", "와", "과", "도", "만", "보다", "부터", "까지", "이다",
            "있다", "하다", "되다", "않다", "없다", "같다",
            "주식", "주가", "종목", "투자", "증시", "코스피", "코스닥",
            "상승", "하락", "전망", "분석", "관련", "통해", "위해", "대한",
        }

        title_text = " ".join(titles)
        body_texts  = [t + " " + c[:200] for t, c in zip(titles, contents)]
        full_text   = " ".join(body_texts)

        def _kiwi_nouns(text: str) -> list[str]:
            try:
                from kiwipiepy import Kiwi  # type: ignore
                kiwi = _get_kiwi()
                tokens = kiwi.tokenize(text)
                return [
                    t.form for t in tokens
                    if t.tag in ("NNG", "NNP", "SL") and len(t.form) >= 2
                ]
            except Exception:
                return re.findall(r"[가-힣]{2,6}", text)

        body_words  = [w for w in _kiwi_nouns(full_text)  if w not in stopwords]
        title_words = [w for w in _kiwi_nouns(title_text) if w not in stopwords]
        all_words   = body_words + title_words * 2  # 제목 2배 가중

        counter = Counter(all_words)
        return [w for w, _ in counter.most_common(top_k)]

    async def _get_linked_stocks(self, news_ids: list[int]) -> list[str]:
        if not news_ids:
            return []
        rows = await self.db.fetch(
            """
            SELECT code, COUNT(*) AS cnt
            FROM news_stock_links
            WHERE news_id = ANY($1::bigint[])
            GROUP BY code
            ORDER BY cnt DESC
            LIMIT 10
            """,
            news_ids,
        )
        return [r["code"] for r in rows]

    async def _save_snapshots_with_momentum(self, themes: list[Theme]) -> None:
        """테마별 일별 스냅쌏 저장 — momentum_score·velocity·lead_codes 포함."""
        today = datetime.now(timezone.utc).date()

        # 전날 stock_count 조회 (velocity 계산용)
        prev_rows = await self.db.fetch(
            """
            SELECT theme_name, stock_count
            FROM theme_snapshots
            WHERE snap_date = $1
            """,
            today - timedelta(days=1),
        )
        prev_map: dict[str, int] = {r["theme_name"]: r["stock_count"] for r in prev_rows}

        for t in themes:
            name        = ",".join(t.keywords[:3])  # 키워드 조합을 테마 이름으로 사용
            stock_count = len(t.stock_codes)
            prev        = prev_map.get(name, stock_count)
            vel         = stock_count - prev        # 당일 변화량

            # momentum_score: 뉴스 수 + trend + velocity 종합
            trend_boost = 0.2 if t.trend == "rising" else (-0.1 if t.trend == "falling" else 0.0)
            mom  = round(min(1.0, t.news_count / 100.0 + trend_boost + max(0, vel) / 20.0), 3)

            lead = ",".join(t.stock_codes[:5]) if t.stock_codes else None

            try:
                await self.db.execute(
                    """
                    INSERT INTO theme_snapshots
                        (theme_name, snap_date, stock_count, avg_return, top_codes,
                         momentum_score, velocity, lead_codes)
                    VALUES ($1, $2, $3, NULL, $4, $5, $6, $7)
                    ON CONFLICT (theme_name, snap_date) DO UPDATE
                      SET stock_count    = EXCLUDED.stock_count,
                          top_codes      = EXCLUDED.top_codes,
                          momentum_score = EXCLUDED.momentum_score,
                          velocity       = EXCLUDED.velocity,
                          lead_codes     = EXCLUDED.lead_codes
                    """,
                    name, today, stock_count,
                    ",".join(t.stock_codes),
                    mom, vel, lead,
                )
            except Exception as e:
                logger.debug(f"[ThemeCluster] snapshot insert error [{name}]: {e}")

    async def _cache_themes(self, themes: list[Theme]) -> None:
        payload = [
            {
                "cluster_id":  t.cluster_id,
                "keywords":    t.keywords,
                "news_count":  t.news_count,
                "stock_codes": t.stock_codes,
                "trend":       t.trend,
                "count_3d":    t.count_3d,
                "count_7d":    t.count_7d,
            }
            for t in themes
        ]
        await self.redis.set(
            "themes:clusters",
            orjson.dumps(payload),
            ex=_CACHE_TTL,
        )
        await self.redis.set(
            "themes:updated_at",
            datetime.now(timezone.utc).isoformat(),
            ex=_CACHE_TTL,
        )
