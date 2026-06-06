# 데이터베이스 스키마

**DBMS**: PostgreSQL 16 + TimescaleDB + pgvector  
**마이그레이션**: `infra/postgres/` SQL 파일 순서대로 수동 적용  
**마이그레이션 파일**: `init.sql` → `migrate_keyword_filters.sql` → `V3__recommendations_feature_event_id.sql`

---

## ER 개요

```
stocks ─┬─< daily_bars (TimescaleDB)
        ├─< tick_data (TimescaleDB)
        ├─< minute_bars (TimescaleDB)
        ├─< supply_demand
        ├─< disclosures
        ├─< feature_events (TimescaleDB, pgvector)
        └─< recommendations ──> feature_events (feature_event_id)

news ─< news_stock_links ──> stocks
```

---

## 테이블 정의

### stocks — 종목 마스터

| 컬럼 | 타입 | 설명 |
|------|------|------|
| code | VARCHAR(10) PK | 종목코드 |
| name | VARCHAR(100) | 종목명 |
| market | VARCHAR(10) | KOSPI / KOSDAQ |
| sector | VARCHAR(100) | 업종 |
| is_active | BOOLEAN | 활성 여부 |
| is_trading_halt | BOOLEAN | 거래정지 여부 |

---

### daily_bars — 일봉 데이터 (TimescaleDB Hypertable)

**PRIMARY KEY**: (date, code)  
**특이사항**: `code='0001'`(KOSPI), `'1001'`(KOSDAQ) 지수 데이터도 포함

| 컬럼 | 타입 | 설명 |
|------|------|------|
| date | DATE | 거래일 |
| code | VARCHAR(10) | 종목코드 / 지수코드 |
| open/high/low/close | INTEGER | OHLC |
| volume | BIGINT | 거래량 |
| amount | BIGINT | 거래대금 |
| change_rate | DECIMAL(7,2) | 전일비 등락률(%) |
| foreign_net_buy | BIGINT | 외국인 순매수 |
| inst_net_buy | BIGINT | 기관 순매수 |
| indiv_net_buy | BIGINT | 개인 순매수 |
| short_sell_vol | BIGINT | 공매도 거래량 |
| ma5/ma20/ma60/ma120 | DECIMAL | 이동평균 (사전계산 캐시) |
| rsi14 | DECIMAL(6,2) | RSI 14일 |
| macd / macd_signal | DECIMAL | MACD |
| bb_upper / bb_lower | DECIMAL | 볼린저밴드 |

---

### supply_demand — 수급 데이터 (상세)

**PRIMARY KEY**: (date, code)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| date | DATE | 거래일 |
| code | VARCHAR(10) | 종목코드 |
| foreign_net | BIGINT | 외국인 순매수 수량 |
| inst_net | BIGINT | 기관 순매수 수량 |
| indiv_net | BIGINT | 개인 순매수 수량 |
| pension_net | BIGINT | 연기금 순매수 |
| prog_arbitrage_net | BIGINT | 프로그램 차익 |

**수집 경로**: `collector/_supply_demand_loop()` (장중 30분 간격) + `_supply_demand_eod_loop()` (장 마감 후 전체 종목 1회)

---

### feature_events — 특징주 탐지 이벤트 (TimescaleDB Hypertable, pgvector)

**PRIMARY KEY**: (id, detected_at) — TimescaleDB 복합 PK

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | BIGSERIAL | 이벤트 ID |
| detected_at | TIMESTAMPTZ | 탐지 시각 |
| code | VARCHAR(10) | 종목코드 |
| event_type | VARCHAR(50) | 이벤트 유형 (VOLUME_SURGE, BREAKOUT_52W 등) |
| price | INTEGER | 탐지 시점 가격 |
| signal_score | DECIMAL(5,3) | 신호 강도 (0~1) |
| risk_score | DECIMAL(5,3) | 위험도 (0~1) |
| signal_data | JSONB | 이벤트별 상세 데이터 |
| result_1d/3d/5d | DECIMAL(7,2) | 사후 수익률(%) — ML이 1시간마다 업데이트 |
| pattern_vector | vector(256) | 패턴 벡터 (pgvector 유사도 검색용) |

**이벤트 유형**: `VOLUME_SURGE`, `AMOUNT_SURGE`, `BREAKOUT_52W/26W/13W/20D`, `LONG_WHITE_CANDLE`, `HAMMER_CANDLE`, `SUPPLY_ANOMALY`

---

### recommendations — 매매 추천

**PRIMARY KEY**: id

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | BIGSERIAL | 추천 ID |
| feature_event_id | BIGINT | 원인 feature_event ID (중복 방지 키) |
| code | VARCHAR(10) | 종목코드 |
| created_at | TIMESTAMPTZ | 생성 시각 |
| action | VARCHAR(10) | BUY / WAIT / SKIP / SELL |
| entry_price | INTEGER | 진입가 |
| entry_price_low/high | INTEGER | 진입가 범위 |
| target_price | INTEGER | 목표가 |
| stop_loss_price | INTEGER | 손절가 |
| expected_hold_days | SMALLINT | 예상 보유 기간 |
| success_prob | DECIMAL(5,3) | 성공 확률 (ML 모델 출력) |
| expected_return | DECIMAL(7,2) | 기대 수익률(%) |
| risk_score | DECIMAL(5,3) | 위험도 |
| risk_reward_ratio | DECIMAL(6,2) | 손익비 |
| rationale | JSONB | 추천 근거 |
| similar_cases | JSONB | 유사사례 목록 |
| actual_return | DECIMAL(7,2) | 실제 수익률 (사후 업데이트) |
| is_success | BOOLEAN | 성공 여부 |
| expired_at | TIMESTAMPTZ | 만료 시각 |

**중복 방지**: `NOT EXISTS (SELECT 1 FROM recommendations WHERE feature_event_id = fe.id)` 조건으로 재시작 시 중복 처리 차단

---

### disclosures — 공시 데이터

| 컬럼 | 타입 | 설명 |
|------|------|------|
| rcept_no | VARCHAR(20) UNIQUE | DART 접수번호 |
| code | VARCHAR(10) | 종목코드 |
| disclosed_at | TIMESTAMPTZ | 공시 시각 |
| title | VARCHAR(500) | 공시 제목 |
| category | VARCHAR(20) | favorable / unfavorable / neutral |
| sentiment_score | DECIMAL(5,3) | 감성 점수 (-1~1) |
| embedding | vector(384) | 텍스트 임베딩 (jhgan/ko-sroberta) |

---

### news / news_stock_links — 뉴스

| 컬럼 | 타입 | 설명 |
|------|------|------|
| source | VARCHAR(50) | 뉴스 출처 (naver 등) |
| published_at | TIMESTAMPTZ | 발행 시각 |
| title | VARCHAR(500) | 제목 |
| sentiment_score | DECIMAL(5,3) | 감성 점수 |
| embedding | vector(384) | 텍스트 임베딩 |

---

## 인덱스 전략

| 테이블 | 인덱스 | 용도 |
|--------|--------|------|
| daily_bars | `(code, date DESC)` | 종목별 최신 일봉 조회 |
| feature_events | `(code, detected_at DESC)` | 종목별 최신 이벤트 |
| feature_events | ivfflat `pattern_vector` | pgvector 유사도 검색 |
| recommendations | `feature_event_id` | 중복 INSERT 방지 |
| recommendations | `(code, created_at DESC)` | 종목별 최신 추천 |
| disclosures | ivfflat `embedding` | 공시 유사도 검색 |

---

## ML 피처 컬럼 (43개)

`services/ml/models/lgbm_predictor.py`의 `FEATURE_COLUMNS` 참조.  
동일 목록이 `services/recommender/ml_client.py`에도 하드코딩됨 (P1-1에서 단일화 예정).

주요 피처:
- 수익률: `return_1d/3d/5d`
- 이동평균: `ma5/20/60_ratio`, `ma5/20_slope`
- 거래량: `vol_ratio_5d/20d`, `vol_surge`, `amount_ratio`
- 기술지표: `rsi14`, `macd_hist`, `bb_pct/width/squeeze`, `atr_ratio`
- 캔들: `body_size`, `is_bullish`, `upper/lower_wick`
- 수급: `foreign/inst_cumnet_5d/20d`, `dual_buy`, `short_ratio`
- 시장: `kospi_return_1d/5d`, `rel_strength_5d` (현재 0 — KOSPI 데이터 수집 후 활성화)
