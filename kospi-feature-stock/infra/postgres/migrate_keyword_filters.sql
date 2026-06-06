-- 기존 DB migration: 키워드 관리 기능 추가
-- 컨테이너 내부에서 실행:
--   psql $POSTGRES_DSN -f /docker-entrypoint-initdb.d/migrate_keyword_filters.sql

ALTER TABLE disclosures ADD COLUMN IF NOT EXISTS is_flagged BOOLEAN DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS disclosure_filters (
    id         BIGSERIAL PRIMARY KEY,
    type       VARCHAR(10) NOT NULL CHECK (type IN ('keyword', 'stock')),
    value      VARCHAR(200) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (type, value)
);

CREATE INDEX IF NOT EXISTS idx_disc_filter_type ON disclosure_filters(type);
CREATE INDEX IF NOT EXISTS idx_disc_flagged ON disclosures(is_flagged) WHERE is_flagged = TRUE;
