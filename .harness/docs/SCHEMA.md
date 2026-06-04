# 데이터베이스 스키마

> AI 에이전트가 코드를 작성할 때 이 문서를 참조합니다.
>
> **관리 방침**: 이 문서는 `/a2m_improve` 중에도 마이그레이션 파일(`V{n}__...sql`)과 **동시에** 직접 수정합니다.

---

## DBMS

| 항목 | 내용 |
|------|------|
| DBMS | PostgreSQL 16 |
| ORM | SQLAlchemy 2.x (비동기 미사용, 동기 Session) |
| 마이그레이션 도구 | Alembic (또는 수동 SQL) |
| 파일 위치 | `bid-system/backend/app/models.py` |

---

## ER 다이어그램

```mermaid
erDiagram
    users {
        int id PK
        varchar email UK
        varchar hashed_password
        varchar name
        varchar role
        varchar department
        bool is_active
        timestamp created_at
    }
    agencies {
        int id PK
        varchar code UK
        varchar name
        varchar type
        int region_id FK
        timestamp created_at
    }
    bids {
        bigint id PK
        varchar announcement_no UK
        varchar title
        int agency_id FK
        int industry_id FK
        int region_id FK
        bigint base_amount
        bigint estimated_price
        bigint a_value
        numeric min_bid_rate
        date notice_date
        timestamp bid_open_date
        varchar status
        timestamp created_at
    }
    competitors {
        int id PK
        varchar name
        varchar biz_reg_no UK
        int region_id FK
        text[] industry_codes
        timestamp created_at
    }
    bid_results {
        bigint id PK
        bigint bid_id FK
        int competitor_id FK
        bigint bid_amount
        numeric bid_rate
        int rank
        bool is_winner
        numeric assessment_rate
    }
    feature_store {
        bigint id PK
        bigint bid_id FK UK
        numeric agency_avg_rate_12m
        numeric agency_win_rate_12m
        numeric industry_avg_rate_12m
        numeric expected_competitor_count
        timestamp computed_at
    }
    my_bid_records {
        bigint id PK
        bigint bid_id FK
        int user_id FK
        varchar title
        numeric submitted_rate
        numeric recommendation_rate
        varchar result
        numeric actual_winner_rate
        timestamp created_at
    }
    bid_bookmarks {
        int id PK
        int user_id FK
        bigint bid_id FK
        varchar note
    }
    competitor_stats {
        bigint id PK
        int competitor_id FK
        int period_year
        int period_month
        int total_bid_count
        int win_count
        numeric win_rate
        numeric avg_bid_rate
    }

    agencies ||--o{ bids : "발주"
    bids ||--o{ bid_results : "포함"
    competitors ||--o{ bid_results : "참여"
    competitors ||--o{ competitor_stats : "통계"
    bids ||--|| feature_store : "피처"
    users ||--o{ my_bid_records : "기록"
    users ||--o{ bid_bookmarks : "북마크"
    bids ||--o{ bid_bookmarks : "북마크됨"
```

---

## 테이블 설계

### `users` — 시스템 사용자

| 컬럼 | 타입 | NULL | 기본값 | 설명 |
|------|------|------|--------|------|
| `id` | `INTEGER` | NOT NULL | auto | PK |
| `email` | `VARCHAR(200)` | NOT NULL | — | 로그인 이메일, UNIQUE |
| `hashed_password` | `VARCHAR(200)` | NOT NULL | — | bcrypt 해시 |
| `name` | `VARCHAR(100)` | NULL | — | 표시 이름 |
| `role` | `VARCHAR(20)` | NOT NULL | `'viewer'` | viewer / admin |
| `department` | `VARCHAR(100)` | NULL | — | 부서 |
| `is_active` | `BOOLEAN` | NOT NULL | `true` | 활성 여부 |
| `last_login` | `TIMESTAMP TZ` | NULL | — | 마지막 로그인 |
| `created_at` | `TIMESTAMP TZ` | NOT NULL | `now()` | 생성일시 |

---

### `bids` — 입찰 공고

| 컬럼 | 타입 | NULL | 설명 |
|------|------|------|------|
| `id` | `BIGINT` | NOT NULL | PK |
| `announcement_no` | `VARCHAR(60)` | NOT NULL | 공고번호, UNIQUE |
| `title` | `VARCHAR(500)` | NOT NULL | 공고명 |
| `agency_id` | `INTEGER` | NOT NULL | FK → agencies |
| `industry_id` | `INTEGER` | NULL | FK → industries |
| `region_id` | `INTEGER` | NULL | FK → regions |
| `base_amount` | `BIGINT` | NOT NULL | 기초금액 |
| `estimated_price` | `BIGINT` | NULL | 예정가격 |
| `a_value` | `BIGINT` | NULL | A값 (예가 기준) |
| `min_bid_rate` | `NUMERIC(7,4)` | NULL | 최저 투찰률 |
| `notice_date` | `DATE` | NULL | 공고일 |
| `bid_open_date` | `TIMESTAMP TZ` | NULL | 개찰일시 |
| `status` | `VARCHAR(20)` | NOT NULL | `'closed'` / `'open'` |
| `source` | `VARCHAR(20)` | NOT NULL | `'api'` / `'manual'` |
| `created_at` | `TIMESTAMP TZ` | NOT NULL | `now()` |

---

### `bid_results` — 낙찰 결과

| 컬럼 | 타입 | NULL | 설명 |
|------|------|------|------|
| `id` | `BIGINT` | NOT NULL | PK |
| `bid_id` | `BIGINT` | NOT NULL | FK → bids (CASCADE DELETE) |
| `competitor_id` | `INTEGER` | NOT NULL | FK → competitors |
| `bid_amount` | `BIGINT` | NOT NULL | 투찰금액 |
| `bid_rate` | `NUMERIC(7,4)` | NOT NULL | 투찰률 |
| `rank` | `SMALLINT` | NOT NULL | 순위 |
| `is_winner` | `BOOLEAN` | NOT NULL | `false` | 낙찰 여부 |
| `assessment_rate` | `NUMERIC(7,4)` | NULL | 사정율(예정가/기초) |

**UNIQUE**: `(bid_id, competitor_id)`

---

### `feature_store` — ML 피처 사전 계산

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `bid_id` | `BIGINT` | FK → bids, UNIQUE |
| `agency_avg_rate_12m` | `NUMERIC(7,4)` | 발주처 최근 12개월 평균 사정율 |
| `agency_win_rate_12m` | `NUMERIC(5,4)` | 발주처 최근 12개월 낙찰률 |
| `industry_avg_rate_12m` | `NUMERIC(7,4)` | 공종 평균 사정율 |
| `expected_competitor_count` | `SMALLINT` | 예상 경쟁사 수 |
| `competitor_strength_score` | `NUMERIC(5,2)` | 경쟁 강도 점수 |
| `amount_log10` | `NUMERIC(10,4)` | log10(기초금액) |
| `computed_at` | `TIMESTAMP TZ` | 계산 시각 |

---

### `assessment_rate_stats` — 사정율 집계 통계

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `group_type` | `VARCHAR(20)` | agency / industry / region / global |
| `group_id` | `INTEGER` | NULL = global |
| `period_year` | `SMALLINT` | 연도 |
| `period_month` | `SMALLINT` | 월 (NULL = 연간) |
| `sample_count` | `INTEGER` | 표본 수 |
| `srate_mean` | `NUMERIC(7,4)` | 평균 사정율 |
| `srate_p10~p90` | `NUMERIC(7,4)` | 백분위 |

**UNIQUE**: `(group_type, group_id_safe, period_year, period_month_safe)`

---

### `my_bid_records` — 자사 투찰 이력

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `bid_id` | `BIGINT` | FK → bids (NULL 허용 — 수동 등록) |
| `user_id` | `INTEGER` | FK → users |
| `submitted_rate` | `NUMERIC(7,4)` | 실제 투찰률 |
| `recommendation_rate` | `NUMERIC(7,4)` | AI 추천 투찰률 (정확도 추적용) |
| `result` | `VARCHAR(10)` | pending / won / lost |
| `actual_winner_rate` | `NUMERIC(7,4)` | 실제 낙찰률 (결과 입력 시) |

---

## 관계 정의

| 관계 | 방식 | 주의사항 |
|------|------|---------|
| Agency → Bid | 1:N | `relationship("Bid", back_populates="agency")` |
| Bid → BidResult | 1:N | `cascade="all,delete-orphan"` — 공고 삭제 시 결과 자동 삭제 |
| Competitor → BidResult | 1:N | 경쟁사 삭제 금지 (결과 보존) |
| Bid → FeatureStore | 1:1 | `uselist=False` |
| User → MyBidRecord | 1:N | 사용자 삭제 시 이력 보존 (soft delete 미지원) |

---

## 인덱스 전략

| 테이블 | 컬럼 | 인덱스 종류 | 이유 |
|--------|------|------------|------|
| `users` | `email` | UNIQUE | 로그인 시 이메일 조회 |
| `bids` | `announcement_no` | UNIQUE | 중복 수집 방지 |
| `bids` | `agency_id, bid_open_date` | 복합 | 발주처별 최신 공고 목록 |
| `bids` | `status, bid_open_date` | 복합 | 진행 중 공고 필터 |
| `bid_results` | `bid_id, competitor_id` | UNIQUE | 중복 결과 방지 |
| `bid_results` | `competitor_id, bid_rate` | 복합 | 경쟁사별 투찰률 분석 |
| `competitor_stats` | `competitor_id, period_year, period_month` | UNIQUE | 월별 통계 집계 |
| `bid_bookmarks` | `user_id, bid_id` | UNIQUE | 북마크 중복 방지 |

---

## 마이그레이션 전략

### 파일 명명 규칙

```
V{버전}__{설명}.sql
예: V1__initial_schema.sql
    V2__add_assessment_rate_stats.sql
    V3__add_bid_bookmarks.sql
```

### 금지 사항

- 운영 데이터가 있는 컬럼 직접 삭제 (코드 참조 제거 후 다음 배포에서 삭제)
- NOT NULL 컬럼 추가 시 기본값 없이 추가
- 적용된 마이그레이션 파일 수정 (새 파일로 추가)

---

## 초기 데이터 (Seed)

| 환경 | 방식 | 파일 위치 |
|------|------|----------|
| 개발 | Python seed 스크립트 | `bid-system/backend/app/seed.py` |
| 운영 | 나라장터 API 수집 또는 CSV import | — |
