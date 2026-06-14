.PHONY: up down restart logs ps build pull stats train backtest load-stocks migrate health \
        bootstrap test test-resilience migrate-v5 migrate-v6 migrate-v7 migrate-v8 migrate-v9 \
        migrate-all audit-features validate-data train-full backfill-results pipeline-status

# ── 환경 설정 ──────────────────────────────────────────────────
CP_ENV := cp .env.example .env

setup:
	@echo "Setting up environment..."
	@if not exist .env $(CP_ENV)
	@echo "Done. Edit .env with your API keys before running 'make up'"

# ── 서비스 제어 ────────────────────────────────────────────────
up:
	docker compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 10
	docker compose ps

down:
	docker compose down

restart:
	docker compose restart $(svc)

logs:
	docker compose logs -f --tail=100 $(svc)

ps:
	docker compose ps

build:
	docker compose build --no-cache $(svc)

pull:
	docker compose pull

# ── DB 초기화 ──────────────────────────────────────────────────
migrate:
	docker compose exec postgres psql \
		-U $$POSTGRES_USER -d $$POSTGRES_DB \
		-f /docker-entrypoint-initdb.d/01_init.sql

# ── 종목 리스트 갱신 (장 마감 후) ──────────────────────────────
load-stocks:
	docker compose exec collector python scripts/load_stock_list.py

# ── 통계 갱신 (매일 16:00 이후 실행) ───────────────────────────
stats:
	docker compose exec ml python scripts/update_stats.py
	@echo "Stats updated."

# ── 모델 학습 (walk-forward) ────────────────────────────────────
train:
	docker compose exec ml python walk_forward_train.py \
		--train-start 2022-01-01 --val-start 2024-01-01 \
		--val-end 2024-12-31 --smote
	@echo "Training complete."

# ── 학습 데이터 검증 → 학습 → 평가 ──────────────────────────────
validate-data:
	docker compose exec ml python -c "\
import asyncio, asyncpg, os; \
async def check(): \
    conn = await asyncpg.connect(os.environ['POSTGRES_DSN'].replace('+asyncpg','')); \
    total = await conn.fetchval(\"SELECT COUNT(*) FROM feature_events fe JOIN daily_bars db ON db.code=fe.code AND db.date=fe.detected_at::date WHERE fe.detected_at BETWEEN '2022-01-01' AND '2024-12-31' AND fe.result_5d IS NOT NULL\"); \
    print(f'학습 가능 이벤트: {total:,}개'); \
    print('OK 학습 가능' if total >= 5000 else 'WARNING 데이터 부족 (최소 5000개 필요)'); \
asyncio.run(check())"

train-full: validate-data
	@echo "=== ML Walk-Forward 학습 시작 ==="
	docker compose exec ml python walk_forward_train.py \
		--train-start 2022-01-01 --val-start 2024-01-01 \
		--val-end 2024-12-31 --smote
	@echo "=== 학습 완료 ==="

backfill-results:
	@echo "=== 과거 이벤트 결과값 백필 ==="
	docker compose exec ml python backfill_feature_events.py
	@echo "=== 백필 완료 ==="

pipeline-status:
	curl -s http://localhost:8000/api/v1/admin/pipeline-status | python3 -m json.tool

# ── 백테스트 ───────────────────────────────────────────────────
backtest:
	docker compose exec ml python scripts/backtest_run.py \
		--start 2023-01-01 --end 2024-12-31
	@echo "Backtest complete. Check output/backtest_report.json"

# ── 헬스 체크 ──────────────────────────────────────────────────
health:
	curl -s http://localhost:8000/health | python -m json.tool

metrics:
	curl -s http://localhost:8000/metrics | python -m json.tool

# ── Kafka 토픽 확인 ────────────────────────────────────────────
topics:
	docker compose exec kafka kafka-topics \
		--bootstrap-server localhost:9092 --list

# ── 로그 서비스별 단축키 ────────────────────────────────────────
logs-collector:
	docker compose logs -f --tail=100 collector

logs-detector:
	docker compose logs -f --tail=100 detector

logs-api:
	docker compose logs -f --tail=100 api

logs-ml:
	docker compose logs -f --tail=100 ml

# ── 사후 주가반응 업데이트 (매일 16:30 이후) ────────────────────
update-results:
	docker compose exec ml python scripts/update_event_results.py

# ── 원클릭 초기화 (신규 설치 시 1회 실행) ──────────────────────
bootstrap:
	@echo "=== 신규 설치 초기화 시작 ==="
	@echo "소요 시간: 30분~2시간 (데이터 크기에 따라)"
	docker compose up -d postgres redis kafka
	@echo "인프라 기동 대기 (30초)..."
	@sleep 30
	docker compose run --rm collector-tick python /app/../../setup_bootstrap.py
	@echo "=== Bootstrap 완료 ==="
	@echo "서비스 시작: make up"

# ── DB 마이그레이션 V5: HNSW 인덱스 ───────────────────────────
migrate-v5:
	docker compose exec postgres psql \
		-U $${POSTGRES_USER} -d $${POSTGRES_DB} \
		-f /docker-entrypoint-initdb.d/V5__hnsw_disclosure_embedding.sql

# ── DB 마이그레이션 V6: 관심종목 테이블 ───────────────────────
migrate-v6:
	docker compose exec postgres psql \
		-U ${POSTGRES_USER} -d ${POSTGRES_DB} \
		-f /docker-entrypoint-initdb.d/V6__watchlist.sql

# ── DB 마이그레이션 V7~V9: 텔레그램·성과·역산 ─────────────────
migrate-v7:
	docker compose exec postgres psql \
		-U $${POSTGRES_USER} -d $${POSTGRES_DB} \
		-f /docker-entrypoint-initdb.d/03_V7__telegram_logs.sql

migrate-v8:
	docker compose exec postgres psql \
		-U $${POSTGRES_USER} -d $${POSTGRES_DB} \
		-f /docker-entrypoint-initdb.d/04_V8__recommendation_performance.sql

migrate-v9:
	docker compose exec postgres psql \
		-U $${POSTGRES_USER} -d $${POSTGRES_DB} \
		-f /docker-entrypoint-initdb.d/05_V9__backfill_rec_performance.sql

migrate-all: migrate migrate-v5 migrate-v6 migrate-v7 migrate-v8 migrate-v9
	@echo "All migrations applied."

# ── 단위 테스트 ─────────────────────────────────────────────────
test:
	docker compose run --rm --no-deps collector-tick \
		python -m pytest tests/ -v --tb=short

# ── 장애 복구 테스트 ─────────────────────────────────────────────
test-resilience:
	docker compose run --rm --no-deps collector-tick \
		python -m pytest tests/test_resilience.py -v --tb=short

# ── Feature 품질 감사 ────────────────────────────────────────────
audit-features:
	@echo "=== Feature 품질 감사 ==="
	docker compose exec ml python -c "\
import sys; sys.path.insert(0,'/app'); \
from models.lgbm_predictor import FEATURE_COLUMNS; \
from features.technical import TechnicalFeatureExtractor; \
from features.supply_demand import SupplyDemandFeatureExtractor; \
import pandas as pd, numpy as np; \
te = TechnicalFeatureExtractor(); sd = SupplyDemandFeatureExtractor(); \
dummy = pd.DataFrame({'date': pd.date_range('2023-01-01', periods=30), \
  'open':[100]*30,'high':[105]*30,'low':[95]*30,'close':[102]*30, \
  'volume':[1000000]*30,'amount':[100000000000]*30, \
  'foreign_net':[1000000]*30,'inst_net':[500000]*30, \
  'short_sell_vol':[100000]*30}); \
f = te.extract(dummy); f = sd.extract(f); \
computed = set(f.columns); \
missing = [c for c in FEATURE_COLUMNS if c not in computed]; \
zeros = [c for c in FEATURE_COLUMNS if c in computed and f[c].std() < 1e-8]; \
print(f'피처 총 {len(FEATURE_COLUMNS)}개'); \
print(f'미구현: {missing}'); \
print(f'항상 0: {zeros}') \
"
