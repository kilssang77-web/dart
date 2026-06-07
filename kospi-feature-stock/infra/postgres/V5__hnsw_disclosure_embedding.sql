-- V5: disclosures 임베딩 인덱스 ivfflat → HNSW 교체
-- ivfflat은 recall이 낮음. HNSW는 메모리 사용량이 높지만 recall 우수.

BEGIN;

-- 기존 ivfflat 인덱스 제거
DROP INDEX IF EXISTS idx_disc_embedding;

-- HNSW 인덱스 생성 (feature_events와 동일한 파라미터)
CREATE INDEX IF NOT EXISTS idx_disc_embedding_hnsw ON disclosures
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- news 테이블도 동일하게 교체
DROP INDEX IF EXISTS idx_news_embedding;

CREATE INDEX IF NOT EXISTS idx_news_embedding_hnsw ON news
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

COMMIT;
