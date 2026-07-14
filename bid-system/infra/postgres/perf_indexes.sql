-- 성능 최적화 인덱스 (2026-06-18)
-- docker exec bid_postgres psql -U biduser -d biddb -f /docker-entrypoint-initdb.d/perf_indexes.sql

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bids_status         ON bids(status);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bids_agency_id      ON bids(agency_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bids_industry_id    ON bids(industry_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bids_region_id      ON bids(region_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bids_notice_date    ON bids(notice_date);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bids_bid_open_date  ON bids(bid_open_date);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bid_results_bid_id        ON bid_results(bid_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bid_results_competitor_id ON bid_results(competitor_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bid_results_bid_winner    ON bid_results(bid_id, is_winner);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_inpo21c_part_bid_winner   ON inpo21c_participants(inpo21c_bid_id, is_winner);
