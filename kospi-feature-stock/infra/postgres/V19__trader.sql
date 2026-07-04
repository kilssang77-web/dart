-- ══════════════════════════════════════════════════════════════
-- V19: 자동 매매 트레이더 스키마
-- ══════════════════════════════════════════════════════════════

-- ── 트레이더 설정 (단일 행, 기본값 포함) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS trader_settings (
    id                      SERIAL PRIMARY KEY,
    is_active               BOOLEAN     NOT NULL DEFAULT FALSE,
    mode                    VARCHAR(20) NOT NULL DEFAULT 'paper',    -- paper | live
    sizing_method           VARCHAR(20) NOT NULL DEFAULT 'fixed_fraction', -- kelly | fixed_fraction | fixed_ratio
    max_invest_per_trade    NUMERIC(15,0) NOT NULL DEFAULT 500000,   -- 종목당 최대 투자금 (원)
    max_total_invest        NUMERIC(15,0) NOT NULL DEFAULT 3000000,  -- 총 최대 투자금 (원)
    max_positions           INT         NOT NULL DEFAULT 5,          -- 동시 최대 보유 종목 수
    daily_loss_limit        NUMERIC(15,0) NOT NULL DEFAULT 100000,   -- 일일 최대 허용 손실 (원, 양수)
    min_prob                NUMERIC(5,4) NOT NULL DEFAULT 0.45,      -- 최소 성공 확률
    kelly_fraction          NUMERIC(5,4) NOT NULL DEFAULT 0.25,      -- Quarter-Kelly 비율
    fixed_fraction_pct      NUMERIC(5,2) NOT NULL DEFAULT 10.0,      -- 자본 대비 % (고정비율)
    auto_sell               BOOLEAN     NOT NULL DEFAULT TRUE,       -- 목표가/손절가 자동 매도
    allow_manual_order      BOOLEAN     NOT NULL DEFAULT TRUE,       -- 수동 주문 허용
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 기본 행 (없을 때만 삽입)
INSERT INTO trader_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- ── 주문 기록 ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    id              BIGSERIAL PRIMARY KEY,
    order_no        VARCHAR(30),                      -- KIS 주문번호 (ODNO)
    rec_id          BIGINT,                           -- recommendations.id (nullable: 수동 주문)
    code            VARCHAR(10)  NOT NULL,
    name            VARCHAR(100),
    side            VARCHAR(4)   NOT NULL,            -- BUY | SELL
    order_type      VARCHAR(10)  NOT NULL DEFAULT 'MARKET', -- MARKET | LIMIT
    order_price     NUMERIC(15,0) NOT NULL DEFAULT 0,
    order_qty       INT          NOT NULL,
    filled_qty      INT          NOT NULL DEFAULT 0,
    avg_filled_price NUMERIC(15,2),
    status          VARCHAR(20)  NOT NULL DEFAULT 'PENDING', -- PENDING|FILLED|PARTIAL|CANCELLED|FAILED|REJECTED
    mode            VARCHAR(10)  NOT NULL DEFAULT 'paper',   -- paper | live
    error_msg       TEXT,
    raw_response    JSONB,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_code_created  ON orders(code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_status        ON orders(status) WHERE status IN ('PENDING','PARTIAL');
CREATE INDEX IF NOT EXISTS idx_orders_rec_id        ON orders(rec_id) WHERE rec_id IS NOT NULL;

-- ── 보유 포지션 ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS positions (
    id              BIGSERIAL PRIMARY KEY,
    code            VARCHAR(10)  NOT NULL,
    name            VARCHAR(100),
    qty             INT          NOT NULL,
    avg_price       NUMERIC(15,2) NOT NULL,
    current_price   NUMERIC(15,2),
    target_price    NUMERIC(15,2),
    stop_loss_price NUMERIC(15,2),
    rec_id          BIGINT,
    entry_order_id  BIGINT,
    entry_date      DATE         NOT NULL DEFAULT CURRENT_DATE,
    status          VARCHAR(20)  NOT NULL DEFAULT 'HOLDING', -- HOLDING | CLOSED
    close_reason    VARCHAR(30),                             -- TARGET_HIT | STOP_HIT | MANUAL | TIMEOUT
    exit_order_id   BIGINT,
    closed_at       TIMESTAMPTZ,
    closed_price    NUMERIC(15,2),
    pnl_pct         NUMERIC(8,4),
    pnl_amount      NUMERIC(15,0),
    mode            VARCHAR(10)  NOT NULL DEFAULT 'paper',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE(code, status, mode)
);

CREATE INDEX IF NOT EXISTS idx_positions_code    ON positions(code);
CREATE INDEX IF NOT EXISTS idx_positions_status  ON positions(status, mode);
CREATE INDEX IF NOT EXISTS idx_positions_closed  ON positions(closed_at DESC) WHERE status='CLOSED';

-- ── 일일 손익 ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_pnl (
    id              BIGSERIAL PRIMARY KEY,
    trade_date      DATE         NOT NULL,
    mode            VARCHAR(10)  NOT NULL DEFAULT 'paper',
    realized_pnl    NUMERIC(15,0) NOT NULL DEFAULT 0,   -- 실현 손익 (원)
    unrealized_pnl  NUMERIC(15,0) NOT NULL DEFAULT 0,   -- 미실현 손익 (원)
    total_trades    INT          NOT NULL DEFAULT 0,
    win_trades      INT          NOT NULL DEFAULT 0,
    loss_trades     INT          NOT NULL DEFAULT 0,
    buy_amount      NUMERIC(15,0) NOT NULL DEFAULT 0,   -- 총 매수금액
    sell_amount     NUMERIC(15,0) NOT NULL DEFAULT 0,   -- 총 매도금액
    is_limit_hit    BOOLEAN      NOT NULL DEFAULT FALSE, -- 일일 손실 한도 초과 여부
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE(trade_date, mode)
);

CREATE INDEX IF NOT EXISTS idx_daily_pnl_date ON daily_pnl(trade_date DESC, mode);

-- ── 뷰: 활성 포지션 현황 ──────────────────────────────────────────────────────
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

-- ── 뷰: 오늘 주문 현황 ────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_today_orders AS
SELECT
    o.id, o.order_no, o.code, o.name, o.side, o.order_type,
    o.order_price, o.order_qty, o.filled_qty, o.avg_filled_price,
    o.status, o.mode, o.rec_id, o.error_msg, o.created_at
FROM orders o
WHERE o.created_at >= CURRENT_DATE::TIMESTAMPTZ;
