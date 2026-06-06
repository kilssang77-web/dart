-- ============================================================
-- Feature Stock Detection System — DB 초기화
-- PostgreSQL 16 + TimescaleDB + pgvector
-- ============================================================

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- ────────────────────────────────────────────────────────────
-- 종목 마스터
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS stocks (
    code            VARCHAR(10) PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    market          VARCHAR(10) NOT NULL,       -- KOSPI / KOSDAQ
    sector          VARCHAR(100),
    industry        VARCHAR(100),
    listing_date    DATE,
    par_value       INTEGER,                    -- 액면가
    shares_total    BIGINT,
    is_active       BOOLEAN DEFAULT TRUE,
    is_trading_halt BOOLEAN DEFAULT FALSE,
    halt_reason     VARCHAR(200),
    split_history   JSONB DEFAULT '[]'::JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stocks_market  ON stocks(market);
CREATE INDEX IF NOT EXISTS idx_stocks_sector  ON stocks(sector);
CREATE INDEX IF NOT EXISTS idx_stocks_active  ON stocks(is_active) WHERE is_active = TRUE;

-- ────────────────────────────────────────────────────────────
-- 실시간 체결 (TimescaleDB Hypertable)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tick_data (
    time            TIMESTAMPTZ NOT NULL,
    code            VARCHAR(10) NOT NULL,
    price           INTEGER NOT NULL,
    volume          INTEGER NOT NULL,
    amount          BIGINT NOT NULL,
    change_rate     DECIMAL(7,2),
    bid_ask_ratio   DECIMAL(7,2),
    is_buy          BOOLEAN
);

SELECT create_hypertable('tick_data', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);
SELECT add_compression_policy('tick_data', INTERVAL '7 days', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_tick_code_time ON tick_data(code, time DESC);

-- ────────────────────────────────────────────────────────────
-- 분봉 데이터
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS minute_bars (
    time            TIMESTAMPTZ NOT NULL,
    code            VARCHAR(10) NOT NULL,
    interval_min    SMALLINT NOT NULL,
    open            INTEGER NOT NULL,
    high            INTEGER NOT NULL,
    low             INTEGER NOT NULL,
    close           INTEGER NOT NULL,
    volume          BIGINT NOT NULL,
    amount          BIGINT NOT NULL,
    buy_volume      BIGINT DEFAULT 0,
    sell_volume     BIGINT DEFAULT 0,
    bid_ask_ratio   DECIMAL(7,2)
);

SELECT create_hypertable('minute_bars', 'time',
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists => TRUE
);
SELECT add_compression_policy('minute_bars', INTERVAL '30 days', if_not_exists => TRUE);

CREATE UNIQUE INDEX IF NOT EXISTS idx_minbar_pk ON minute_bars(code, interval_min, time DESC);

-- ────────────────────────────────────────────────────────────
-- 일봉 데이터
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_bars (
    date            DATE NOT NULL,
    code            VARCHAR(10) NOT NULL,
    open            INTEGER NOT NULL,
    high            INTEGER NOT NULL,
    low             INTEGER NOT NULL,
    close           INTEGER NOT NULL,
    volume          BIGINT NOT NULL,
    amount          BIGINT NOT NULL,
    change_rate     DECIMAL(7,2),
    -- 조정가 (액면분할 반영)
    adj_open        DECIMAL(14,2),
    adj_high        DECIMAL(14,2),
    adj_low         DECIMAL(14,2),
    adj_close       DECIMAL(14,2),
    adj_factor      DECIMAL(12,6) DEFAULT 1.0,
    -- 수급
    foreign_net_buy  BIGINT DEFAULT 0,
    inst_net_buy     BIGINT DEFAULT 0,
    indiv_net_buy    BIGINT DEFAULT 0,
    prog_net_buy     BIGINT DEFAULT 0,
    short_sell_vol   BIGINT DEFAULT 0,
    short_balance    BIGINT DEFAULT 0,
    -- 기술지표 (사전계산 캐시)
    ma5             DECIMAL(14,2),
    ma20            DECIMAL(14,2),
    ma60            DECIMAL(14,2),
    ma120           DECIMAL(14,2),
    rsi14           DECIMAL(6,2),
    macd            DECIMAL(14,4),
    macd_signal     DECIMAL(14,4),
    bb_upper        DECIMAL(14,2),
    bb_lower        DECIMAL(14,2),
    atr14           DECIMAL(14,2),
    PRIMARY KEY (date, code)
);

SELECT create_hypertable('daily_bars', 'date',
    chunk_time_interval => INTERVAL '1 year',
    if_not_exists => TRUE
);
SELECT add_compression_policy('daily_bars', INTERVAL '2 years', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_dailybar_code ON daily_bars(code, date DESC);

-- ────────────────────────────────────────────────────────────
-- 수급 데이터 (상세)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS supply_demand (
    date                    DATE NOT NULL,
    code                    VARCHAR(10) NOT NULL,
    foreign_buy             BIGINT DEFAULT 0,
    foreign_sell            BIGINT DEFAULT 0,
    foreign_net             BIGINT DEFAULT 0,
    foreign_hold_rate       DECIMAL(6,2),
    inst_buy                BIGINT DEFAULT 0,
    inst_sell               BIGINT DEFAULT 0,
    inst_net                BIGINT DEFAULT 0,
    pension_net             BIGINT DEFAULT 0,
    insurance_net           BIGINT DEFAULT 0,
    trust_net               BIGINT DEFAULT 0,
    bank_net                BIGINT DEFAULT 0,
    private_eq_net          BIGINT DEFAULT 0,
    indiv_buy               BIGINT DEFAULT 0,
    indiv_sell              BIGINT DEFAULT 0,
    indiv_net               BIGINT DEFAULT 0,
    prog_arbitrage_net      BIGINT DEFAULT 0,
    prog_nonarbitrage_net   BIGINT DEFAULT 0,
    PRIMARY KEY (date, code)
);

CREATE INDEX IF NOT EXISTS idx_sd_code ON supply_demand(code, date DESC);

-- ────────────────────────────────────────────────────────────
-- 공시 데이터
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS disclosures (
    id              BIGSERIAL PRIMARY KEY,
    rcept_no        VARCHAR(20) UNIQUE NOT NULL,
    code            VARCHAR(10),
    corp_name       VARCHAR(100),
    disclosed_at    TIMESTAMPTZ NOT NULL,
    report_type     VARCHAR(50),
    disclosure_type VARCHAR(100),
    title           VARCHAR(500) NOT NULL,
    content         TEXT,
    category        VARCHAR(20) CHECK (category IN ('favorable','unfavorable','neutral')),
    sentiment_score DECIMAL(5,3),
    amount          BIGINT,
    amount_text     VARCHAR(200),
    keywords        JSONB DEFAULT '[]'::JSONB,
    counterparty    VARCHAR(200),
    contract_period VARCHAR(100),
    pre_close       INTEGER,
    post_1h_change  DECIMAL(7,2),
    post_1d_change  DECIMAL(7,2),
    post_3d_change  DECIMAL(7,2),
    embedding       vector(768),
    raw_json        JSONB,
    is_flagged      BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 기존 DB 호환: is_flagged 컬럼 없으면 추가
DO $$ BEGIN
    ALTER TABLE disclosures ADD COLUMN IF NOT EXISTS is_flagged BOOLEAN DEFAULT FALSE;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- ────────────────────────────────────────────────────────────
-- 공시 필터 (키워드/종목 관리)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS disclosure_filters (
    id         BIGSERIAL PRIMARY KEY,
    type       VARCHAR(10) NOT NULL CHECK (type IN ('keyword', 'stock')),
    value      VARCHAR(200) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (type, value)
);

CREATE INDEX IF NOT EXISTS idx_disc_filter_type ON disclosure_filters(type);

CREATE INDEX IF NOT EXISTS idx_disc_code       ON disclosures(code, disclosed_at DESC);
CREATE INDEX IF NOT EXISTS idx_disc_type       ON disclosures(disclosure_type);
CREATE INDEX IF NOT EXISTS idx_disc_category   ON disclosures(category);
CREATE INDEX IF NOT EXISTS idx_disc_embedding  ON disclosures
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ────────────────────────────────────────────────────────────
-- 뉴스 데이터
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS news (
    id              BIGSERIAL PRIMARY KEY,
    source          VARCHAR(50),
    published_at    TIMESTAMPTZ NOT NULL,
    title           VARCHAR(500) NOT NULL,
    content         TEXT,
    url             VARCHAR(1000),
    sentiment_score DECIMAL(5,3),
    keywords        JSONB DEFAULT '[]'::JSONB,
    themes          JSONB DEFAULT '[]'::JSONB,
    embedding       vector(768),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS news_stock_links (
    news_id     BIGINT REFERENCES news(id) ON DELETE CASCADE,
    code        VARCHAR(10),
    relevance   DECIMAL(5,3),
    PRIMARY KEY (news_id, code)
);

CREATE INDEX IF NOT EXISTS idx_news_published  ON news(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_embedding  ON news
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ────────────────────────────────────────────────────────────
-- 특징주 이벤트 (탐지 결과)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS feature_events (
    id              BIGSERIAL,
    detected_at     TIMESTAMPTZ NOT NULL,
    code            VARCHAR(10) NOT NULL,
    event_type      VARCHAR(50) NOT NULL,
    price           INTEGER,
    change_rate     DECIMAL(7,2),
    volume          BIGINT,
    volume_ratio    DECIMAL(10,2),
    amount          BIGINT,
    signal_data     JSONB DEFAULT '{}'::JSONB,
    signal_score    DECIMAL(5,3),
    risk_score      DECIMAL(5,3),
    -- 결과 추적 (사후 업데이트)
    result_1h       DECIMAL(7,2),
    result_3h       DECIMAL(7,2),
    result_1d       DECIMAL(7,2),
    result_3d       DECIMAL(7,2),
    result_5d       DECIMAL(7,2),
    -- 벡터 (유사사례 검색)
    pattern_vector  vector(256),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (id, detected_at)
);

SELECT create_hypertable('feature_events', 'detected_at',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_fevent_code    ON feature_events(code, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_fevent_type    ON feature_events(event_type);
CREATE INDEX IF NOT EXISTS idx_fevent_score   ON feature_events(signal_score DESC);
CREATE INDEX IF NOT EXISTS idx_fevent_pattern ON feature_events
    USING ivfflat (pattern_vector vector_cosine_ops) WITH (lists = 100);

-- ────────────────────────────────────────────────────────────
-- 매매 추천
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS recommendations (
    id                  BIGSERIAL PRIMARY KEY,
    feature_event_id    BIGINT,
    code                VARCHAR(10) NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    action              VARCHAR(10) CHECK (action IN ('BUY','WAIT','SKIP','SELL')),
    entry_price         INTEGER,
    entry_price_low     INTEGER,
    entry_price_high    INTEGER,
    target_price        INTEGER,
    stop_loss_price     INTEGER,
    expected_hold_days  SMALLINT,
    success_prob        DECIMAL(5,3),
    expected_return     DECIMAL(7,2),
    risk_score          DECIMAL(5,3),
    risk_reward_ratio   DECIMAL(6,2),
    rationale           JSONB DEFAULT '{}'::JSONB,
    similar_cases       JSONB DEFAULT '[]'::JSONB,
    actual_return       DECIMAL(7,2),
    is_success          BOOLEAN,
    expired_at          TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_rec_code    ON recommendations(code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rec_action  ON recommendations(action);
CREATE INDEX IF NOT EXISTS idx_rec_prob    ON recommendations(success_prob DESC);

-- ────────────────────────────────────────────────────────────
-- 재무 데이터
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS financials (
    code              VARCHAR(10) NOT NULL,
    year              SMALLINT NOT NULL,
    quarter           SMALLINT,
    revenue           BIGINT,
    operating_profit  BIGINT,
    net_profit        BIGINT,
    eps               INTEGER,
    bps               INTEGER,
    per               DECIMAL(10,2),
    pbr               DECIMAL(8,2),
    roe               DECIMAL(7,2),
    debt_ratio        DECIMAL(7,2),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (code, year, quarter)
);

-- ────────────────────────────────────────────────────────────
-- ML 모델 메타데이터
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ml_models (
    id              BIGSERIAL PRIMARY KEY,
    model_type      VARCHAR(50) NOT NULL,
    version         VARCHAR(20) NOT NULL,
    trained_at      TIMESTAMPTZ NOT NULL,
    metrics         JSONB DEFAULT '{}'::JSONB,
    feature_names   JSONB DEFAULT '[]'::JSONB,
    model_path      VARCHAR(500),
    is_active       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────
-- 시스템 로그 (TimescaleDB)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_logs (
    id          BIGSERIAL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    service     VARCHAR(50),
    level       VARCHAR(10),
    message     TEXT,
    extra       JSONB
);

SELECT create_hypertable('system_logs', 'created_at',
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists => TRUE
);
SELECT add_compression_policy('system_logs', INTERVAL '30 days', if_not_exists => TRUE);

-- ────────────────────────────────────────────────────────────
-- 한국 공휴일 (연간 관리)
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS kr_holidays (
    holiday_date DATE PRIMARY KEY,
    name         VARCHAR(100)
);

INSERT INTO kr_holidays (holiday_date, name) VALUES
    ('2025-01-01','신정'), ('2025-01-28','설날연휴'), ('2025-01-29','설날'),
    ('2025-01-30','설날연휴'), ('2025-03-01','삼일절'), ('2025-05-05','어린이날'),
    ('2025-05-06','대체공휴일'), ('2025-06-06','현충일'), ('2025-08-15','광복절'),
    ('2025-10-03','개천절'), ('2025-10-05','추석연휴'), ('2025-10-06','추석'),
    ('2025-10-07','추석연휴'), ('2025-10-09','한글날'), ('2025-12-25','성탄절'),
    ('2026-01-01','신정'), ('2026-02-17','설날연휴'), ('2026-02-18','설날'),
    ('2026-02-19','설날연휴'), ('2026-03-01','삼일절'), ('2026-05-05','어린이날'),
    ('2026-05-25','부처님오신날'), ('2026-06-06','현충일'), ('2026-08-17','광복절대체'),
    ('2026-09-24','추석연휴'), ('2026-09-25','추석'), ('2026-09-28','추석연휴'),
    ('2026-10-09','한글날'), ('2026-12-25','성탄절')
ON CONFLICT DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 유용한 뷰
-- ────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_today_features AS
SELECT
    fe.id,
    fe.detected_at,
    fe.code,
    s.name,
    s.market,
    fe.event_type,
    fe.price,
    fe.change_rate,
    fe.volume_ratio,
    fe.signal_score,
    fe.risk_score
FROM feature_events fe
JOIN stocks s ON s.code = fe.code
WHERE fe.detected_at >= CURRENT_DATE
ORDER BY fe.signal_score DESC;

CREATE OR REPLACE VIEW v_active_recommendations AS
SELECT
    r.*,
    s.name,
    s.market,
    s.sector
FROM recommendations r
JOIN stocks s ON s.code = r.code
WHERE r.created_at >= NOW() - INTERVAL '8 hours'
  AND r.action = 'BUY'
ORDER BY r.success_prob DESC;

-- 완료 메시지
DO $$ BEGIN
    RAISE NOTICE 'Feature Stock DB initialized successfully.';
END $$;
