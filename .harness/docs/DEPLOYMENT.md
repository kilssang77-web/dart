# 배포 가이드 (DEPLOYMENT)

---

## 로컬 개발 환경 기동

### 사전 요구사항

- Docker Desktop (Docker Compose v2)
- Python 3.12+ (스크립트 직접 실행 시)
- KIS OpenAPI 앱키/시크릿/계좌번호

### 전체 스택 실행

```bash
# 1. 환경변수 설정
cp .env.example .env
# .env 파일을 실제 값으로 채움

# 2. 전체 서비스 기동 (PostgreSQL + Kafka + 5개 마이크로서비스)
docker compose up -d

# 3. 헬스 체크
curl http://localhost:8000/api/v1/health   # api service
curl http://localhost:8001/health           # ml service
```

### 서비스별 포트

| 서비스 | 포트 | 설명 |
|--------|------|------|
| api | 8000 | 외부 REST API |
| ml | 8001 | ML 추론 내부 API |
| PostgreSQL | 5432 | TimescaleDB + pgvector |
| Kafka | 9092 | 메시지 브로커 |
| Zookeeper | 2181 | Kafka 의존 |

### DB 마이그레이션

마이그레이션 SQL은 `infra/postgres/` 에서 순서대로 적용:

```
V1__init.sql                             # 기본 테이블 생성
V2__feature_events_hypertable.sql        # TimescaleDB hypertable 변환
V3__recommendations_feature_event_id.sql # feature_event_id FK 인덱스
seed_data.sql                            # KOSPI/KOSDAQ 의사 종목 추가
```

---

## 환경변수 목록

`.env.example` 기준 전체 항목:

| 변수 | 필수 | 예시값 | 설명 |
|------|------|--------|------|
| `KIS_APP_KEY` | ✅ | `PSxxxxxxxx` | KIS OpenAPI 앱키 |
| `KIS_APP_SECRET` | ✅ | `(secret)` | KIS OpenAPI 시크릿 |
| `KIS_ACCOUNT_NO` | ✅ | `12345678-01` | 계좌번호 |
| `DB_DSN` | ✅ | `postgresql://user:pass@postgres:5432/kospi` | PostgreSQL DSN |
| `KAFKA_BOOTSTRAP` | ✅ | `kafka:9092` | Kafka 브로커 |
| `REC_MIN_PROB` | — | `0.35` | BUY 최소 확률 임계값 |
| `REC_MAX_RISK` | — | `0.60` | BUY 최대 리스크 |
| `REC_MIN_RISK_REWARD` | — | `2.0` | 최소 손익비 |
| `ML_SERVICE_URL` | — | `http://ml:8001` | ML 서비스 URL |
| `ML_API_PORT` | — | `8001` | ML 서비스 포트 |

---

## Docker Compose 구성

```yaml
services:
  collector:   # KIS API 수집
  detector:    # 패턴 탐지
  recommender: # 추천 판단 (ML_SERVICE_URL: "http://ml:8001")
  ml:          # ML 추론 (ports: ["8001:8001"])
  api:         # REST API (ports: ["8000:8000"])
  postgres:    # TimescaleDB + pgvector
  kafka:
  zookeeper:
```

---

## 모델 재학습 절차

### 수동 재학습

```bash
# Docker 컨테이너 내부에서 실행
docker compose exec ml python train_model.py

# 또는 호스트에서 직접
python scripts/train_model.py
```

학습 완료 후 모델 핫스왑:

```bash
curl -X POST http://localhost:8001/reload
```

### 자동 재학습 (주간)

ml 서비스 내 `_weekly_retrain_loop()` 가 매주 일요일 02:00 KST 자동 실행.
재학습 중에도 기존 모델로 정상 서비스 유지 (atomic rename 핫스왑).

---

## 백테스트 실행

```bash
# feature_events 기반 (기본)
python scripts/backtest_run.py --mode events

# daily_bars 기반 룰 재적용
python scripts/backtest_run.py --mode replay --start 2025-09-18 --end 2026-04-30

# 결과: output/backtest_report.json 저장
```

---

## pattern_vector 백필

pgvector 유사도 검색 비활성화 시 실행:

```bash
python scripts/backfill_vectors.py          # 전체
python scripts/backfill_vectors.py --limit 100  # N건만
```

---

## 배포 형태

| 환경 | 배포 방식 | 비고 |
|------|-----------|------|
| local | Docker Compose | 개발·검증 |
| prod | Docker Compose (MVP) / K8s (이후) | 미정 |

---

## 관측 (Logging)

- 모든 서비스: Python `logging` 모듈, `%(levelname)s %(name)s — %(message)s` 포맷
- 로그 레벨: 개발 `DEBUG`, 운영 `INFO`
- 주요 로그 포인트: Recovery 완료 건수, ML 추론 결과(`ml_prob=`), 재학습 AUC/Brier score

로그에 API 키·토큰·패스워드 출력 금지.
