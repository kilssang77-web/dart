.PHONY: up down restart logs ps build pull stats train backtest load-stocks migrate health

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

# ── 모델 학습 ──────────────────────────────────────────────────
train:
	docker compose exec ml python scripts/train_model.py \
		--start 2022-01-01 --end 2024-12-31
	@echo "Training complete."

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
