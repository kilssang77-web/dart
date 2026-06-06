# 프로젝트 구조

---

## 레포 전략

- 전략: 모노레포
- 구성: 5개 마이크로서비스 + 공통 인프라 + 스크립트를 단일 레포에서 관리

---

## 전체 디렉토리 트리

```
kospi-feature-stock/
├── services/
│   ├── collector/
│   │   ├── main.py                     # 수집 서비스 진입점 (asyncio 멀티루프)
│   │   ├── kis/
│   │   │   └── rest_client.py          # KIS REST API 클라이언트 (get_index_bars 등)
│   │   └── requirements.txt
│   │
│   ├── detector/
│   │   ├── main.py                     # Kafka 소비 → 패턴 탐지 → feature-events 발행
│   │   ├── patterns/
│   │   │   └── candlestick.py          # 장대양봉, 망치형, 모닝스타 등 탐지 함수
│   │   └── requirements.txt
│   │
│   ├── recommender/
│   │   ├── main.py                     # 추천 판단, Recovery 루프, signal-generated 발행
│   │   ├── entry_recommender.py        # 진입가·목표가·손절가 계산, 확률 혼합
│   │   ├── ml_client.py                # ML 추론 (HTTP → local LightGBM → rule-based)
│   │   ├── pattern_vector.py           # pgvector 유사도 검색 (pattern_vector 생성)
│   │   └── requirements.txt
│   │
│   ├── ml/
│   │   ├── main.py                     # FastAPI 앱 (/health /predict /reload), 주간 재학습 루프
│   │   ├── train_model.py              # 수동 재학습 진입점 (Brier score 로깅)
│   │   ├── models/
│   │   │   ├── lgbm_predictor.py       # LightGBM 43피처 추론, 캘리브레이터 적용
│   │   │   └── trainer.py              # entry/risk 모델 학습, IsotonicRegression 보정
│   │   ├── features/
│   │   │   └── technical.py            # 기술적 지표 계산, inject_market_features()
│   │   ├── backtest/
│   │   │   └── engine.py               # 백테스트 엔진 (bars pre-indexing 최적화)
│   │   └── requirements.txt            # fastapi, uvicorn, httpx, lightgbm, joblib
│   │
│   └── api/
│       ├── main.py                     # FastAPI 앱 진입점
│       ├── routers/
│       │   ├── recommendations.py      # GET /api/v1/recommendations (min_prob=0.35)
│       │   └── features.py             # GET /api/v1/features (MORNING_STAR 포함)
│       └── requirements.txt
│
├── infra/
│   └── postgres/
│       ├── V1__init.sql
│       ├── V2__feature_events_hypertable.sql
│       ├── V3__recommendations_feature_event_id.sql  # feature_event_id 인덱스
│       └── seed_data.sql               # KOSPI(0001)/KOSDAQ(1001) 의사 종목
│
├── scripts/
│   ├── train_model.py                  # LightGBM 수동 재학습 (load_market_data 포함)
│   ├── backtest_run.py                 # 백테스트 (--mode events|replay)
│   └── backfill_vectors.py             # pattern_vector NULL 이벤트 일괄 백필
│
├── tests/
│   ├── __init__.py
│   ├── requirements-test.txt
│   ├── test_candlestick.py             # 15개 (장대양봉, 망치형, 모닝스타)
│   └── test_entry_recommender.py       # 12개 (진입 판단, 가격 계산, 확률 혼합)
│
├── models/
│   └── lgbm/
│       ├── entry_model.lgb
│       ├── risk_model.lgb
│       ├── entry_calibrator.pkl        # IsotonicRegression 보정 모델
│       └── risk_calibrator.pkl
│
├── docker-compose.yml
└── .env.example
```

---

## 빌드 · 실행 명령

### 사전 요구사항

- Docker Desktop (Docker Compose v2)
- Python 3.12+ (스크립트 직접 실행 시)

### 전체 스택

```bash
cp .env.example .env
docker compose up -d
docker compose logs -f recommender    # 실시간 로그 확인
```

### 특정 서비스만 재시작

```bash
docker compose restart recommender
docker compose up --force-recreate recommender   # 환경변수 반영 시
```

### 테스트

```bash
pip install -r tests/requirements-test.txt
pytest tests/ -v
```

### 모델 재학습

```bash
docker compose exec ml python train_model.py
curl -X POST http://localhost:8001/reload
```

---

## 환경변수

| 변수 | 서비스 | 설명 |
|------|--------|------|
| `KIS_APP_KEY` | collector | KIS OpenAPI 앱키 |
| `KIS_APP_SECRET` | collector | KIS OpenAPI 시크릿 |
| `KIS_ACCOUNT_NO` | collector | 계좌번호 |
| `DB_DSN` | 전체 | PostgreSQL DSN |
| `KAFKA_BOOTSTRAP` | 전체 | Kafka 브로커 주소 |
| `REC_MIN_PROB` | recommender, api | BUY 최소 확률 (기본 0.35) |
| `REC_MAX_RISK` | recommender | BUY 최대 리스크 (기본 0.60) |
| `REC_MIN_RISK_REWARD` | recommender | 최소 손익비 (기본 2.0) |
| `ML_SERVICE_URL` | recommender | ML 서비스 URL (기본 `http://ml:8001`) |
| `ML_API_PORT` | ml | ML 서비스 포트 (기본 8001) |

---

## 브랜치 전략

| 브랜치 | 용도 |
|--------|------|
| `main` | 최신 안정 코드 |
| `feat/<name>` | 기능 개발 |
| `fix/<name>` | 버그 수정 |
| `feat-<task>` | 하네스 자동 생성 브랜치 |
