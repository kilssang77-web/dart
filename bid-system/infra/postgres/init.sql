-- ============================
-- 건설 입찰 분석 시스템 DB 초기화
-- ============================

-- 확장 기능
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================
-- 기준 테이블
-- ============================

CREATE TABLE IF NOT EXISTS regions (
    id         SERIAL PRIMARY KEY,
    code       VARCHAR(10)  NOT NULL UNIQUE,
    name       VARCHAR(50)  NOT NULL,
    parent_id  INTEGER REFERENCES regions(id)
);

CREATE TABLE IF NOT EXISTS industries (
    id         SERIAL PRIMARY KEY,
    code       VARCHAR(20)  NOT NULL UNIQUE,
    name       VARCHAR(100) NOT NULL,
    parent_id  INTEGER REFERENCES industries(id)
);

CREATE TABLE IF NOT EXISTS agencies (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(20)  UNIQUE,
    name        VARCHAR(200) NOT NULL,
    type        VARCHAR(50),
    region_id   INTEGER REFERENCES regions(id),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================
-- 경쟁사 테이블
-- ============================

CREATE TABLE IF NOT EXISTS competitors (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(200) NOT NULL,
    biz_reg_no     VARCHAR(20) UNIQUE,
    region_id      INTEGER REFERENCES regions(id),
    industry_codes TEXT[],
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_competitors_name ON competitors USING gin(name gin_trgm_ops);

-- ============================
-- 입찰 공고 테이블
-- ============================

CREATE TABLE IF NOT EXISTS bids (
    id                   BIGSERIAL PRIMARY KEY,
    announcement_no      VARCHAR(60)   NOT NULL UNIQUE,
    title                VARCHAR(500)  NOT NULL,
    agency_id            INTEGER       NOT NULL REFERENCES agencies(id),
    industry_id          INTEGER       REFERENCES industries(id),
    region_id            INTEGER       REFERENCES regions(id),
    base_amount          BIGINT        NOT NULL DEFAULT 0,
    estimated_price      BIGINT,
    a_value              BIGINT,
    min_bid_rate         NUMERIC(7,4),
    notice_date          DATE,
    bid_open_date        TIMESTAMPTZ,
    construction_period  INTEGER,
    region_restriction   BOOLEAN       DEFAULT FALSE,
    license_codes        TEXT[],
    status               VARCHAR(20)   DEFAULT 'closed'
                             CHECK (status IN ('open','closed','canceled')),
    source               VARCHAR(20)   DEFAULT 'api'
                             CHECK (source IN ('api','crawl','manual','seed')),
    created_at           TIMESTAMPTZ   DEFAULT NOW(),
    updated_at           TIMESTAMPTZ   DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bids_agency_date    ON bids(agency_id, bid_open_date DESC);
CREATE INDEX IF NOT EXISTS idx_bids_industry_date  ON bids(industry_id, bid_open_date DESC);
CREATE INDEX IF NOT EXISTS idx_bids_region         ON bids(region_id);
CREATE INDEX IF NOT EXISTS idx_bids_amount         ON bids(base_amount);
CREATE INDEX IF NOT EXISTS idx_bids_status         ON bids(status);
CREATE INDEX IF NOT EXISTS idx_bids_title_trgm     ON bids USING gin(title gin_trgm_ops);

-- ============================
-- 개찰 결과 테이블
-- ============================

CREATE TABLE IF NOT EXISTS bid_results (
    id              BIGSERIAL PRIMARY KEY,
    bid_id          BIGINT        NOT NULL REFERENCES bids(id) ON DELETE CASCADE,
    competitor_id   INTEGER       NOT NULL REFERENCES competitors(id),
    bid_amount      BIGINT        NOT NULL,
    bid_rate        NUMERIC(7,4)  NOT NULL,
    rank            SMALLINT      NOT NULL,
    is_winner       BOOLEAN       DEFAULT FALSE,
    assessment_rate NUMERIC(7,4),
    created_at      TIMESTAMPTZ   DEFAULT NOW(),
    CONSTRAINT uq_bid_competitor UNIQUE(bid_id, competitor_id)
);

CREATE INDEX IF NOT EXISTS idx_results_bid        ON bid_results(bid_id);
CREATE INDEX IF NOT EXISTS idx_results_competitor ON bid_results(competitor_id, bid_rate);
CREATE INDEX IF NOT EXISTS idx_results_winner     ON bid_results(bid_id) WHERE is_winner = TRUE;
CREATE INDEX IF NOT EXISTS idx_results_rate       ON bid_results(bid_rate);

-- ============================
-- 피처 스토어 테이블
-- ============================

CREATE TABLE IF NOT EXISTS feature_store (
    id                        BIGSERIAL PRIMARY KEY,
    bid_id                    BIGINT       NOT NULL UNIQUE REFERENCES bids(id),
    agency_avg_rate_12m       NUMERIC(7,4),
    agency_win_rate_12m       NUMERIC(5,4),
    agency_bid_count_12m      INTEGER,
    region_avg_rate_12m       NUMERIC(7,4),
    industry_avg_rate_12m     NUMERIC(7,4),
    expected_competitor_count SMALLINT,
    competitor_strength_score NUMERIC(5,2),
    season_index              SMALLINT,
    amount_log10              NUMERIC(10,4),
    amount_bucket             SMALLINT,
    similar_bid_count         SMALLINT,
    similar_avg_rate          NUMERIC(7,4),
    similar_std_rate          NUMERIC(7,4),
    computed_at               TIMESTAMPTZ   DEFAULT NOW()
);

-- ============================
-- AI 추천 이력 테이블
-- ============================

CREATE TABLE IF NOT EXISTS prediction_logs (
    id                    BIGSERIAL PRIMARY KEY,
    bid_id                BIGINT       REFERENCES bids(id),
    user_id               INTEGER,
    model_version         VARCHAR(50),
    input_features        JSONB,
    rate_safe_lower       NUMERIC(7,4),
    rate_lower            NUMERIC(7,4),
    rate_center           NUMERIC(7,4),
    rate_upper            NUMERIC(7,4),
    rate_safe_upper       NUMERIC(7,4),
    win_prob_center       NUMERIC(5,4),
    risk_level            VARCHAR(10),
    shap_values           JSONB,
    explanation_text      TEXT,
    created_at            TIMESTAMPTZ    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pred_logs_created ON prediction_logs(created_at DESC);

-- ============================
-- 사용자 테이블
-- ============================

CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(200) NOT NULL UNIQUE,
    hashed_password VARCHAR(200) NOT NULL,
    name            VARCHAR(100),
    role            VARCHAR(20)  DEFAULT 'viewer'
                        CHECK (role IN ('admin','analyst','viewer')),
    department      VARCHAR(100),
    is_active       BOOLEAN      DEFAULT TRUE,
    last_login      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);

-- ============================
-- 감사 로그 테이블
-- ============================

CREATE TABLE IF NOT EXISTS audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    user_id     INTEGER,
    action      VARCHAR(50),
    entity_type VARCHAR(50),
    entity_id   VARCHAR(50),
    ip_address  VARCHAR(50),
    detail      JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_user    ON audit_logs(user_id, created_at DESC);

-- ============================
-- 경쟁사 통계 (집계 캐시)
-- ============================

CREATE TABLE IF NOT EXISTS competitor_stats (
    id                   BIGSERIAL PRIMARY KEY,
    competitor_id        INTEGER   NOT NULL REFERENCES competitors(id),
    period_year          SMALLINT  NOT NULL,
    period_month         SMALLINT,
    total_bid_count      INTEGER   DEFAULT 0,
    win_count            INTEGER   DEFAULT 0,
    win_rate             NUMERIC(5,4),
    avg_bid_rate         NUMERIC(7,4),
    std_bid_rate         NUMERIC(7,4),
    aggression_score     NUMERIC(5,2),
    consistency_score    NUMERIC(5,2),
    updated_at           TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_comp_period UNIQUE(competitor_id, period_year, period_month)
);

-- ============================
-- inpo21c 수집 테이블
-- ============================

CREATE TABLE IF NOT EXISTS inpo21c_bids (
    inpo21c_bid_id   VARCHAR(30)  PRIMARY KEY,
    announcement_no  VARCHAR(50),
    industry         VARCHAR(200),
    region           VARCHAR(200),
    agency_name      VARCHAR(200),
    open_datetime    TIMESTAMP,
    base_amount      BIGINT,
    estimated_amount BIGINT,
    min_bid_rate     NUMERIC(8,4),
    preset_amount    BIGINT,
    yega_ratio       NUMERIC(8,4),
    net_cost         BIGINT,
    created_at       TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_inpo21c_bids_announcement
    ON inpo21c_bids(announcement_no);

CREATE TABLE IF NOT EXISTS inpo21c_yega (
    id              SERIAL PRIMARY KEY,
    inpo21c_bid_id  VARCHAR(30)  NOT NULL,
    yega_no         SMALLINT     NOT NULL,
    amount          BIGINT,
    base_ratio      NUMERIC(8,4),
    base_ratio_pct  NUMERIC(8,4),
    is_selected     BOOLEAN DEFAULT FALSE,  -- 복수예가 추첨에서 선발된 값 (text-orange). 평균값 = preset_amount
    UNIQUE(inpo21c_bid_id, yega_no)
);

CREATE INDEX IF NOT EXISTS idx_inpo21c_yega_bid
    ON inpo21c_yega(inpo21c_bid_id);

CREATE TABLE IF NOT EXISTS inpo21c_bid_notices (
    inpo21c_bid_id   VARCHAR(30)  PRIMARY KEY,
    announcement_no  VARCHAR(50),
    industry         VARCHAR(200),
    region           VARCHAR(200),
    agency_name      VARCHAR(200),
    yega_method      VARCHAR(100),
    yega_draw_count  SMALLINT,
    yega_total_count SMALLINT,
    yega_range_min   SMALLINT,
    yega_range_max   SMALLINT,
    min_bid_rate     NUMERIC(8,4),
    contract_method  VARCHAR(100),
    reg_deadline     TIMESTAMP,
    bid_deadline     TIMESTAMP,
    open_datetime    TIMESTAMP,
    base_amount      BIGINT,
    estimated_amount BIGINT,
    created_at       TIMESTAMP DEFAULT now(),
    updated_at       TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_inpo21c_notices_announcement
    ON inpo21c_bid_notices(announcement_no);

-- ============================
-- 기준 데이터 삽입
-- ============================

INSERT INTO regions (code, name) VALUES
  ('11','서울'),('21','부산'),('22','대구'),('23','인천'),
  ('24','광주'),('25','대전'),('26','울산'),('29','세종'),
  ('31','경기'),('32','강원'),('33','충북'),('34','충남'),
  ('35','전북'),('36','전남'),('37','경북'),('38','경남'),('39','제주')
ON CONFLICT (code) DO NOTHING;

INSERT INTO industries (code, name) VALUES
  ('10000','토목공사'),('20000','건축공사'),('30000','산업설비공사'),
  ('40000','조경공사'),('50000','환경공사'),('60000','철도공사'),
  ('70000','도로공사'),('80000','항만공사'),('90000','기계설비공사'),
  ('11000','토공사'),('12000','포장공사'),('21000','주거건축'),
  ('22000','상업건축'),('23000','공공건축')
ON CONFLICT (code) DO NOTHING;

INSERT INTO agencies (code, name, type) VALUES
  ('LH001','한국토지주택공사','공기업'),
  ('KH001','국가철도공단','공기업'),
  ('KW001','한국수자원공사','공기업'),
  ('HR001','한국도로공사','공기업'),
  ('SE001','서울시','지자체'),
  ('BS001','부산시','지자체'),
  ('GG001','경기도','지자체'),
  ('MOL001','국토교통부','중앙부처'),
  ('MND001','국방부','중앙부처'),
  ('MOE001','교육부','중앙부처')
ON CONFLICT (code) DO NOTHING;
