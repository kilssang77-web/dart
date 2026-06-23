-- V15: 백필 작업 이력 테이블
CREATE TABLE IF NOT EXISTS backfill_history (
    id            BIGSERIAL PRIMARY KEY,
    job_type      VARCHAR(50)  NOT NULL,
    triggered_by  VARCHAR(20)  NOT NULL DEFAULT 'auto',
    status        VARCHAR(20)  NOT NULL DEFAULT 'running',
    target_count  INT,
    success_count INT,
    skip_count    INT,
    fail_count    INT,
    rows_added    BIGINT,
    started_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finished_at   TIMESTAMPTZ,
    error_msg     TEXT,
    meta          JSONB
);
CREATE INDEX IF NOT EXISTS idx_backfill_history_type_started
    ON backfill_history(job_type, started_at DESC);
