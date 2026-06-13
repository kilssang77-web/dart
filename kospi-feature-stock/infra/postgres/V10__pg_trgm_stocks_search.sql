-- V10: pg_trgm GIN 인덱스 — stocks 테이블 ILIKE 풀스캔 제거
-- api/routers/stocks.py의 name ILIKE '%q%' / code ILIKE '%q%' 쿼리 가속

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stocks_name_trgm
    ON stocks USING GIN (name gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stocks_code_trgm
    ON stocks USING GIN (code gin_trgm_ops);
