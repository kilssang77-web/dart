-- 관심종목 테이블 (사용자 세션 기반)
CREATE TABLE IF NOT EXISTS watchlist (
    id         BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL DEFAULT 'default',
    code       TEXT NOT NULL,
    added_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    note       TEXT,
    UNIQUE(session_id, code)
);

CREATE INDEX IF NOT EXISTS idx_watchlist_session ON watchlist (session_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_code    ON watchlist (code);