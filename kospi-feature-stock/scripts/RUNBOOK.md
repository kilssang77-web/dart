# 운영 런북 (RUNBOOK)

모든 스크립트는 `scripts/` 디렉터리 하나에서 관리합니다.
`services/collector/scripts/`, `services/ml/scripts/` 는 삭제되었습니다.

---

## 초기 구축 순서

### 0. 종목 목록 적재
```bash
docker compose run --rm collector python /app/scripts/load_stock_list.py
```
KOSPI/KOSDAQ 전체 종목을 `stocks` 테이블에 적재합니다.

### 1. market='UNKNOWN' 보정
```bash
docker compose run --rm collector python /app/scripts/update_stock_markets.py
# 전체 재보정 시:
docker compose run --rm collector python /app/scripts/update_stock_markets.py --all
```
DART corpCode.xml로 KOSPI/KOSDAQ 구분을 갱신합니다.
환경변수: `DART_API_KEY`

### 2. 과거 일봉 백필 (1년치)
```bash
# 일봉만
docker compose run --rm collector python /app/scripts/backfill_daily_bars.py --days 365

# 일봉 + 수급 동시
docker compose run --rm collector python /app/scripts/backfill_daily_bars.py --days 365 --supply
```
KIS API를 120일 청크로 분할 호출합니다. 약 2,500 종목 × 3회 = 7,500 API 호출.
약 40~60분 소요 예상. 환경변수: `KIS_APP_KEY`, `KIS_APP_SECRET`, `REDIS_URL`, `POSTGRES_DSN`

### 3. Redis 통계 갱신
백필 스크립트 완료 시 자동 갱신됩니다.
수동 갱신이 필요한 경우:
```bash
docker compose run --rm collector python /app/scripts/update_stats.py
```

### 4. ML 모델 학습

#### 4-a. 합성 데이터로 즉시 기동 (실데이터 전 서비스 우선 시작)
```bash
docker compose run --rm ml python /app/scripts/train_synthetic.py
```
50종목 × 500일 합성 데이터로 entry/risk 모델을 즉시 생성합니다.
`/models/lgbm/entry_model.lgb`, `risk_model.lgb` 저장.

#### 4-b. 실데이터로 정식 학습 (백필 후)
```bash
# 최근 2년치
docker compose run --rm ml python /app/scripts/train_model.py \
  --start 2023-01-01 --end $(date +%Y-%m-%d)
```
학습 후 recommender 컨테이너를 재시작해야 모델이 로드됩니다:
```bash
docker compose restart recommender
```

---

## 정기 운영

### 결과 업데이트 (result_1d/3d/5d 백필)
`ml` 서비스가 매시간 자동 실행하지만, 수동 트리거가 필요한 경우:
```bash
docker compose run --rm ml python /app/scripts/update_event_results.py
```

### 백테스트 실행
```bash
docker compose run --rm ml python /app/scripts/backtest_run.py \
  --start 2024-01-01 --end 2024-12-31 --event_type VOLUME_SURGE
```

---

## 서비스 기동 순서
```
postgres → redis → zookeeper → kafka → kafka-setup
→ collector → detector → analyzer → ml → recommender → api
```

## 관심종목 기준 실시간 100종목 관리

`batch_scanner`가 장 마감 후 자동으로 `stocks:active_codes` 갱신:
- 신호 강도 상위 80종목 (특징주)
- 사용자 관심종목 (프론트엔드 → `/api/v1/stocks/favorites/sync` 동기화)
- 기본 20종목 (시총 상위)
→ 합산 최대 100종목이 다음날 KIS WebSocket 실시간 구독 대상

---

## 스크립트 목록

| 파일 | 용도 | 실행 컨테이너 |
|------|------|--------------|
| `load_stock_list.py` | 종목 목록 초기 적재 | collector |
| `update_stock_markets.py` | market UNKNOWN 보정 | collector |
| `backfill_daily_bars.py` | 일봉+수급 대량 백필 | collector |
| `update_stats.py` | Redis 통계 수동 갱신 | collector |
| `train_synthetic.py` | 합성데이터 즉시 모델 학습 | ml |
| `train_model.py` | 실데이터 LightGBM 학습 | ml |
| `update_event_results.py` | result_1d/3d/5d 수동 업데이트 | ml |
| `backtest_run.py` | 백테스트 CLI 실행 | ml |
| `verify_apis.py` | KIS/DART API 연결 검증 | collector |
| `test_kis_api.py` | KIS API 단위 테스트 | collector |
| `test_detection_rules.py` | 탐지 규칙 단위 테스트 | detector |
