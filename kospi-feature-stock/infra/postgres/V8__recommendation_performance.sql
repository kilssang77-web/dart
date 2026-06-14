-- 추천 종목 성과 추적
CREATE TABLE IF NOT EXISTS recommendation_performance (
    id               BIGSERIAL PRIMARY KEY,
    rec_id           BIGINT NOT NULL,
    code             VARCHAR(10) NOT NULL,
    entry_price      NUMERIC NOT NULL,
    event_type       VARCHAR(50),
    signal_time      TIMESTAMPTZ NOT NULL,

    r_1h   NUMERIC, t_1h   TIMESTAMPTZ,
    r_3h   NUMERIC, t_3h   TIMESTAMPTZ,
    r_5h   NUMERIC, t_5h   TIMESTAMPTZ,
    r_1d   NUMERIC, t_1d   TIMESTAMPTZ,
    r_2d   NUMERIC, t_2d   TIMESTAMPTZ,
    r_3d   NUMERIC, t_3d   TIMESTAMPTZ,
    r_4d   NUMERIC, t_4d   TIMESTAMPTZ,
    r_5d   NUMERIC, t_5d   TIMESTAMPTZ,
    r_7d   NUMERIC, t_7d   TIMESTAMPTZ,
    r_10d  NUMERIC, t_10d  TIMESTAMPTZ,

    r_special    NUMERIC,
    t_special    TIMESTAMPTZ,
    special_type VARCHAR(30),
    special_date DATE,

    is_success        BOOLEAN,
    max_return        NUMERIC,
    hit_target        BOOLEAN DEFAULT FALSE,
    hit_stop          BOOLEAN DEFAULT FALSE,
    tracking_complete BOOLEAN DEFAULT FALSE,
    last_updated      TIMESTAMPTZ DEFAULT NOW(),
    created_at        TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(rec_id)
);

CREATE INDEX IF NOT EXISTS idx_rec_perf_code     ON recommendation_performance (code);
CREATE INDEX IF NOT EXISTS idx_rec_perf_complete ON recommendation_performance (tracking_complete) WHERE tracking_complete = FALSE;
CREATE INDEX IF NOT EXISTS idx_rec_perf_signal   ON recommendation_performance (signal_time DESC);
