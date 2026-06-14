-- V11: Redis 탐지 통계 DB 백업 (Redis 재시작 시 복구용)
CREATE TABLE IF NOT EXISTS redis_stats_snapshot (
    code        VARCHAR(20)              NOT NULL,
    stat_key    VARCHAR(50)              NOT NULL,
    stat_value  DOUBLE PRECISION         NOT NULL,
    computed_at TIMESTAMPTZ              NOT NULL DEFAULT NOW(),
    PRIMARY KEY (code, stat_key)
);

CREATE INDEX IF NOT EXISTS idx_rss_computed_at ON redis_stats_snapshot(computed_at);

COMMENT ON TABLE redis_stats_snapshot IS
    'Redis 탐지 통계(avg_vol_20d, high_* 등) DB 백업 — Redis 재시작 시 복구에 사용';
