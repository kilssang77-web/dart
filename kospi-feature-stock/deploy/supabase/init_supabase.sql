-- ============================================================
-- Quant Eye — Supabase 초기화 SQL
-- PostgreSQL 16 + pgvector (TimescaleDB 없이 동작)
--
-- 적용 방법:
--   Supabase Dashboard → SQL Editor → 이 파일 전체 붙여넣기 → Run
--
-- 변경사항 (기존 TimescaleDB 대비):
--   - tick_data 테이블 제거 (신규 아키텍처에서 틱 미저장)
--   - create_hypertable / add_compression_policy 제거
--   - feature_events PRIMARY KEY 단순화 (id만)
--   - 표준 PostgreSQL 시계열 인덱스로 대체
--   - pgvector HNSW 인덱스 유지
-- ============================================================

-- ── 확장 기능 ────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS vector;          -- pgvector (Supabase 기본 제공)
CREATE EXTENSION IF NOT EXISTS pg_trgm;         -- 텍스트 검색 (종목명 검색)

-- ════════════════════════════════════════════════════════════
-- 1. 종목 마스터
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS stocks (
    code            VARCHAR(10) PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    market          VARCHAR(10) NOT NULL,
    sector          VARCHAR(100),
    industry        VARCHAR(100),
    listing_date    DATE,
    par_value       INTEGER,
    shares_total    BIGINT,
    market_cap      BIGINT,
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
CREATE INDEX IF NOT EXISTS idx_stocks_name_trgm ON stocks USING gin(name gin_trgm_ops);

-- ════════════════════════════════════════════════════════════
-- 2. 분봉 데이터 (최근 데이터만 보관, 히스토리 불필요)
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS minute_bars (
    time            TIMESTAMPTZ NOT NULL,
    code            VARCHAR(10) NOT NULL,
    interval_min    SMALLINT NOT NULL DEFAULT 1,
    open            INTEGER NOT NULL,
    high            INTEGER NOT NULL,
    low             INTEGER NOT NULL,
    close           INTEGER NOT NULL,
    volume          BIGINT NOT NULL,
    amount          BIGINT NOT NULL,
    buy_volume      BIGINT DEFAULT 0,
    sell_volume     BIGINT DEFAULT 0,
    bid_ask_ratio   DECIMAL(7,2),
    PRIMARY KEY (code, interval_min, time)
);

CREATE INDEX IF NOT EXISTS idx_minbar_time ON minute_bars(time DESC);

-- ════════════════════════════════════════════════════════════
-- 3. 일봉 데이터 (핵심 히스토리 — 최근 2년 보관)
-- ════════════════════════════════════════════════════════════
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
    adj_open        DECIMAL(14,2),
    adj_high        DECIMAL(14,2),
    adj_low         DECIMAL(14,2),
    adj_close       DECIMAL(14,2),
    adj_factor      DECIMAL(12,6) DEFAULT 1.0,
    foreign_net_buy  BIGINT DEFAULT 0,
    inst_net_buy     BIGINT DEFAULT 0,
    indiv_net_buy    BIGINT DEFAULT 0,
    prog_net_buy     BIGINT DEFAULT 0,
    short_sell_vol   BIGINT DEFAULT 0,
    short_balance    BIGINT DEFAULT 0,
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
    market_cap      BIGINT,
    PRIMARY KEY (date, code)
);

CREATE INDEX IF NOT EXISTS idx_dailybar_code      ON daily_bars(code, date DESC);
CREATE INDEX IF NOT EXISTS idx_dailybar_date      ON daily_bars(date DESC);
CREATE INDEX IF NOT EXISTS idx_dailybar_amount    ON daily_bars(date DESC, amount DESC);

-- ════════════════════════════════════════════════════════════
-- 4. 수급 데이터
-- ════════════════════════════════════════════════════════════
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

-- ════════════════════════════════════════════════════════════
-- 5. 공시 데이터
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS disclosures (
    id              BIGSERIAL PRIMARY KEY,
    rcept_no        VARCHAR(200) UNIQUE NOT NULL,
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

CREATE INDEX IF NOT EXISTS idx_disc_code      ON disclosures(code, disclosed_at DESC);
CREATE INDEX IF NOT EXISTS idx_disc_type      ON disclosures(disclosure_type);
CREATE INDEX IF NOT EXISTS idx_disc_category  ON disclosures(category);
CREATE INDEX IF NOT EXISTS idx_disc_embedding ON disclosures
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- ════════════════════════════════════════════════════════════
-- 6. 공시 필터
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS disclosure_filters (
    id         BIGSERIAL PRIMARY KEY,
    type       VARCHAR(10) NOT NULL CHECK (type IN ('keyword', 'stock')),
    value      VARCHAR(200) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (type, value)
);

CREATE INDEX IF NOT EXISTS idx_disc_filter_type ON disclosure_filters(type);

-- ════════════════════════════════════════════════════════════
-- 7. 뉴스
-- ════════════════════════════════════════════════════════════
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_news_url_unique ON news(url) WHERE url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_news_published  ON news(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_embedding  ON news
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- ════════════════════════════════════════════════════════════
-- 8. 특징주 이벤트 (탐지 결과)
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS feature_events (
    id              BIGSERIAL PRIMARY KEY,   -- TimescaleDB 복합PK 단순화
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
    result_1h       DECIMAL(7,2),
    result_3h       DECIMAL(7,2),
    result_1d       DECIMAL(7,2),
    result_3d       DECIMAL(7,2),
    result_5d       DECIMAL(7,2),
    pattern_vector  vector(256),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fevent_code    ON feature_events(code, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_fevent_type    ON feature_events(event_type, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_fevent_score   ON feature_events(signal_score DESC) WHERE signal_score IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_fevent_date    ON feature_events(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_fevent_pattern ON feature_events
    USING hnsw (pattern_vector vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ════════════════════════════════════════════════════════════
-- 9. 매매 추천
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS recommendations (
    id                  BIGSERIAL PRIMARY KEY,
    feature_event_id    BIGINT REFERENCES feature_events(id) ON DELETE SET NULL,
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
CREATE INDEX IF NOT EXISTS idx_rec_action  ON recommendations(action, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rec_prob    ON recommendations(success_prob DESC) WHERE success_prob IS NOT NULL;

-- ════════════════════════════════════════════════════════════
-- 10. 재무 데이터
-- ════════════════════════════════════════════════════════════
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

-- ════════════════════════════════════════════════════════════
-- 11. ML 모델 메타데이터
-- ════════════════════════════════════════════════════════════
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

-- ════════════════════════════════════════════════════════════
-- 12. 시스템 로그 (경량화 — 최근 7일치만 유지)
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS system_logs (
    id          BIGSERIAL PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    service     VARCHAR(50),
    level       VARCHAR(10),
    message     TEXT,
    extra       JSONB
);

CREATE INDEX IF NOT EXISTS idx_syslog_created  ON system_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_syslog_service  ON system_logs(service, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_syslog_level    ON system_logs(level) WHERE level IN ('ERROR','WARNING');

-- ════════════════════════════════════════════════════════════
-- 13. 한국 공휴일
-- ════════════════════════════════════════════════════════════
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

-- ════════════════════════════════════════════════════════════
-- 14. 관심종목 (V6)
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS watchlist (
    id         BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL DEFAULT 'default',
    code       TEXT NOT NULL,
    added_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    note       TEXT,
    UNIQUE(session_id, code)
);

CREATE INDEX IF NOT EXISTS idx_watchlist_session ON watchlist(session_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_code    ON watchlist(code);

-- ════════════════════════════════════════════════════════════
-- 15. 텔레그램 발송 이력 (V7)
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS telegram_logs (
    id          BIGSERIAL PRIMARY KEY,
    msg_type    VARCHAR(20)  NOT NULL,
    code        VARCHAR(10),
    name        VARCHAR(100),
    title       TEXT         NOT NULL DEFAULT '',
    message     TEXT         NOT NULL,
    success     BOOLEAN      NOT NULL DEFAULT TRUE,
    error_msg   TEXT,
    sent_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_telegram_logs_sent_at  ON telegram_logs(sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_telegram_logs_msg_type ON telegram_logs(msg_type);
CREATE INDEX IF NOT EXISTS idx_telegram_logs_code     ON telegram_logs(code) WHERE code IS NOT NULL;

-- ════════════════════════════════════════════════════════════
-- 16. 추천 성과 추적 (V8)
-- ════════════════════════════════════════════════════════════
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

CREATE INDEX IF NOT EXISTS idx_rec_perf_code     ON recommendation_performance(code);
CREATE INDEX IF NOT EXISTS idx_rec_perf_complete ON recommendation_performance(tracking_complete) WHERE tracking_complete = FALSE;
CREATE INDEX IF NOT EXISTS idx_rec_perf_signal   ON recommendation_performance(signal_time DESC);

-- ════════════════════════════════════════════════════════════
-- 17. Redis 통계 스냅샷 (V11)
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS redis_stats_snapshot (
    code        VARCHAR(20)      NOT NULL,
    stat_key    VARCHAR(50)      NOT NULL,
    stat_value  DOUBLE PRECISION NOT NULL,
    computed_at TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    PRIMARY KEY (code, stat_key)
);

CREATE INDEX IF NOT EXISTS idx_rss_computed_at ON redis_stats_snapshot(computed_at);

-- ════════════════════════════════════════════════════════════
-- 18. 백필 이력 (V15)
-- ════════════════════════════════════════════════════════════
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

-- ════════════════════════════════════════════════════════════
-- 19. 트레이더 (V19) — paper 모드만 사용 권장
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS trader_settings (
    id                      SERIAL PRIMARY KEY,
    is_active               BOOLEAN     NOT NULL DEFAULT FALSE,
    mode                    VARCHAR(20) NOT NULL DEFAULT 'paper',
    sizing_method           VARCHAR(20) NOT NULL DEFAULT 'fixed_fraction',
    max_invest_per_trade    NUMERIC(15,0) NOT NULL DEFAULT 500000,
    max_total_invest        NUMERIC(15,0) NOT NULL DEFAULT 3000000,
    max_positions           INT         NOT NULL DEFAULT 5,
    daily_loss_limit        NUMERIC(15,0) NOT NULL DEFAULT 100000,
    min_prob                NUMERIC(5,4) NOT NULL DEFAULT 0.45,
    kelly_fraction          NUMERIC(5,4) NOT NULL DEFAULT 0.25,
    fixed_fraction_pct      NUMERIC(5,2) NOT NULL DEFAULT 10.0,
    auto_sell               BOOLEAN     NOT NULL DEFAULT TRUE,
    allow_manual_order      BOOLEAN     NOT NULL DEFAULT TRUE,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO trader_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS orders (
    id              BIGSERIAL PRIMARY KEY,
    order_no        VARCHAR(30),
    rec_id          BIGINT,
    code            VARCHAR(10) NOT NULL,
    name            VARCHAR(100),
    side            VARCHAR(4)  NOT NULL,
    order_type      VARCHAR(10) NOT NULL DEFAULT 'MARKET',
    order_price     NUMERIC(15,0) NOT NULL DEFAULT 0,
    order_qty       INT         NOT NULL,
    filled_qty      INT         NOT NULL DEFAULT 0,
    avg_filled_price NUMERIC(15,2),
    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    mode            VARCHAR(10) NOT NULL DEFAULT 'paper',
    error_msg       TEXT,
    raw_response    JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_code_created ON orders(code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_status       ON orders(status) WHERE status IN ('PENDING','PARTIAL');

CREATE TABLE IF NOT EXISTS positions (
    id              BIGSERIAL PRIMARY KEY,
    code            VARCHAR(10) NOT NULL,
    name            VARCHAR(100),
    qty             INT         NOT NULL,
    avg_price       NUMERIC(15,2) NOT NULL,
    current_price   NUMERIC(15,2),
    target_price    NUMERIC(15,2),
    stop_loss_price NUMERIC(15,2),
    rec_id          BIGINT,
    entry_order_id  BIGINT,
    entry_date      DATE        NOT NULL DEFAULT CURRENT_DATE,
    status          VARCHAR(20) NOT NULL DEFAULT 'HOLDING',
    close_reason    VARCHAR(30),
    exit_order_id   BIGINT,
    closed_at       TIMESTAMPTZ,
    closed_price    NUMERIC(15,2),
    pnl_pct         NUMERIC(8,4),
    pnl_amount      NUMERIC(15,0),
    mode            VARCHAR(10) NOT NULL DEFAULT 'paper',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(code, status, mode)
);

CREATE INDEX IF NOT EXISTS idx_positions_code   ON positions(code);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status, mode);

CREATE TABLE IF NOT EXISTS daily_pnl (
    id              BIGSERIAL PRIMARY KEY,
    trade_date      DATE        NOT NULL,
    mode            VARCHAR(10) NOT NULL DEFAULT 'paper',
    realized_pnl    NUMERIC(15,0) NOT NULL DEFAULT 0,
    unrealized_pnl  NUMERIC(15,0) NOT NULL DEFAULT 0,
    total_trades    INT         NOT NULL DEFAULT 0,
    win_trades      INT         NOT NULL DEFAULT 0,
    loss_trades     INT         NOT NULL DEFAULT 0,
    buy_amount      NUMERIC(15,0) NOT NULL DEFAULT 0,
    sell_amount     NUMERIC(15,0) NOT NULL DEFAULT 0,
    is_limit_hit    BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(trade_date, mode)
);

CREATE INDEX IF NOT EXISTS idx_daily_pnl_date ON daily_pnl(trade_date DESC, mode);

-- ════════════════════════════════════════════════════════════
-- 20. 사용자 계정 (JWT 인증용)
-- ════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS users (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username      VARCHAR(50)  UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name  VARCHAR(100),
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_login    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- ════════════════════════════════════════════════════════════
-- 뷰 (Views)
-- ════════════════════════════════════════════════════════════
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

CREATE OR REPLACE VIEW v_active_positions AS
SELECT
    p.id, p.code, p.name, p.qty, p.avg_price, p.current_price,
    p.target_price, p.stop_loss_price,
    CASE WHEN p.current_price IS NOT NULL
         THEN ROUND((p.current_price - p.avg_price) / p.avg_price * 100, 2)
         ELSE NULL END AS unrealized_pct,
    CASE WHEN p.current_price IS NOT NULL
         THEN (p.current_price - p.avg_price) * p.qty
         ELSE NULL END AS unrealized_amount,
    p.avg_price * p.qty AS invest_amount,
    p.entry_date, p.mode, p.rec_id, p.created_at
FROM positions p
WHERE p.status = 'HOLDING';

CREATE OR REPLACE VIEW v_today_orders AS
SELECT
    o.id, o.order_no, o.code, o.name, o.side, o.order_type,
    o.order_price, o.order_qty, o.filled_qty, o.avg_filled_price,
    o.status, o.mode, o.rec_id, o.error_msg, o.created_at
FROM orders o
WHERE o.created_at >= CURRENT_DATE::TIMESTAMPTZ;

-- ════════════════════════════════════════════════════════════
-- Materialized View: 시장 등락 캐시
-- 갱신: REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_change_rate;
-- ════════════════════════════════════════════════════════════
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_daily_change_rate AS
WITH
latest_dt AS (SELECT MAX(date) AS d FROM daily_bars),
prev_dt   AS (SELECT MAX(date) AS d FROM daily_bars
               WHERE date < (SELECT d FROM latest_dt))
SELECT
    c.code,
    s.name,
    s.market,
    s.sector,
    c.close AS price,
    c.volume,
    c.amount,
    CASE
        WHEN c.change_rate IS NOT NULL AND c.change_rate <> 0 THEN c.change_rate
        WHEN p.close IS NOT NULL AND p.close > 0 AND c.close IS NOT NULL
            THEN ROUND(((c.close - p.close)::NUMERIC / p.close * 100), 2)
        ELSE 0
    END AS change_rate,
    c.date AS data_date
FROM daily_bars c
CROSS JOIN latest_dt
LEFT JOIN daily_bars p ON p.code = c.code
                       AND p.date = (SELECT d FROM prev_dt)
JOIN stocks s ON s.code = c.code
WHERE c.date = latest_dt.d AND c.close > 0
  AND s.market IN ('KOSPI', 'KOSDAQ');

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_dcr_code         ON mv_daily_change_rate(code);
CREATE INDEX IF NOT EXISTS idx_mv_dcr_change              ON mv_daily_change_rate(change_rate DESC);
CREATE INDEX IF NOT EXISTS idx_mv_dcr_market_change       ON mv_daily_change_rate(market, change_rate DESC);

-- ════════════════════════════════════════════════════════════
-- 완료
-- ════════════════════════════════════════════════════════════
DO $$ BEGIN
    RAISE NOTICE 'Quant Eye Supabase DB initialized successfully (pgvector, no TimescaleDB).';
END $$;
