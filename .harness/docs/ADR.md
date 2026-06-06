# Architecture Decision Records

---

## 철학

작동하는 최소 구현 우선. 서비스 독립성 보장. 데이터 파이프라인 안정성 > 기능 추가 속도.

---

### ADR-001: Python 3.12 + FastAPI + asyncpg 채택

- **결정**: 전 서비스를 Python 3.12 기반 FastAPI + asyncio 비동기 스택으로 구현한다.
- **이유**:
  - Kafka(aiokafka), DB(asyncpg), HTTP(httpx) 전부 비동기 처리로 I/O 병목 최소화
  - ML 스택(LightGBM, pandas, scikit-learn)과 동일 언어 사용 → 서비스 경계 단순화
  - FastAPI Pydantic 스키마로 입력 검증 자동화
- **트레이드오프**:
  - GIL 제한으로 CPU-bound 작업 병렬화 불리 → ML 추론은 별도 ml 서비스로 분리

---

### ADR-002: PostgreSQL + TimescaleDB + pgvector 단일 DB 채택

- **결정**: 시계열 데이터는 TimescaleDB Hypertable, 벡터 유사도 검색은 pgvector로 PostgreSQL 확장만 사용한다.
- **이유**:
  - 별도 시계열 DB(InfluxDB 등) 도입 없이 익숙한 SQL로 운영 가능
  - pgvector로 패턴 유사도 검색(pattern_vector)을 추가 인프라 없이 구현
  - TimescaleDB Hypertable이 일봉·feature_events 시간 범위 쿼리를 자동 파티셔닝으로 최적화
- **트레이드오프**:
  - TimescaleDB는 FK 제약 일부 미지원 → feature_event_id는 인덱스로 대체

---

### ADR-003: Kafka 기반 서비스 간 비동기 통신

- **결정**: collector → detector → recommender 데이터 흐름은 Kafka 토픽으로만 연결한다. 서비스 간 직접 HTTP 호출 금지.
- **이유**:
  - 서비스 독립 배포 가능 — 한 서비스 장애가 타 서비스로 전파되지 않음
  - 재시작 후 미처리 이벤트 Recovery 가능 (Kafka 오프셋 관리)
  - 향후 알림 서비스 추가 시 `signal-generated` 토픽만 소비하면 됨
- **트레이드오프**:
  - 동기 처리 대비 디버깅 복잡도 증가 (분산 추적 필요)

---

### ADR-004: ML 추론 서비스 분리 (FastAPI 독립 서비스, port 8001)

- **결정**: LightGBM 추론 로직을 recommender에서 분리하여 독립 FastAPI 서비스(ml service)로 운영한다.
- **이유**:
  - 모델 재학습 중 추론 서비스 무중단 (atomic rename 핫스왑)
  - 추론 부하가 급증해도 recommender 로직과 독립적으로 스케일 가능
  - `/reload` 엔드포인트로 재학습 완료 후 즉시 모델 교체
- **트레이드오프**:
  - HTTP 호출 오버헤드 발생 → fallback(local LightGBM → rule-based)으로 가용성 보장

---

### ADR-005: Recovery 중복 처리 방지 — feature_event_id 기반

- **결정**: recommender 재시작 시 Recovery는 `feature_event_id` 정확 매칭으로 미처리 이벤트만 재처리한다.
- **이유**:
  - 기존 시간 범위(±10분) 기반 NOT EXISTS 조건은 재시작 시 134건 중복 처리 버그 발생
  - feature_event_id PK 매칭으로 100% 중복 방지 달성 (재시작 후 0건 확인)
- **트레이드오프**:
  - TimescaleDB hypertable FK 제약 미지원 → 인덱스(`idx_recommendations_feature_event_id`)로 대체
