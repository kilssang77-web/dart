#!/usr/bin/env bash
# HNSW 인덱스 생성 → 인덱스 교체 → ML 학습 자동화 스크립트
# 백필 완료(1,481,667건) 확인 후 직접 실행

set -euo pipefail
LOG="/d/a2m/atom-harness-base-Dart/kospi-feature-stock/scripts/hnsw_and_train.log"
COMPOSE_DIR="/d/a2m/atom-harness-base-Dart/kospi-feature-stock"
DB_USER="stockuser"
DB_NAME="feature_stock"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

log "=== Step 1: HNSW 인덱스 생성 시작 ==="
log "현재 벡터 보유 수 확인..."
CNT=$(docker exec fstock-postgres psql -U "$DB_USER" -d "$DB_NAME" -tAc \
  "SELECT COUNT(*) FROM feature_events WHERE pattern_vector IS NOT NULL;")
log "벡터 보유: ${CNT}건"

log "maintenance_work_mem=512MB, max_parallel_maintenance_workers=0 설정 후 CREATE INDEX CONCURRENTLY..."
docker exec fstock-postgres psql -U "$DB_USER" -d "$DB_NAME" <<'SQL'
SET maintenance_work_mem = '512MB';
SET max_parallel_maintenance_workers = 0;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fevent_pattern_hnsw
  ON feature_events
  USING hnsw (pattern_vector vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
SQL

log "=== Step 2: HNSW 인덱스 생성 완료 — 인덱스 교체 ==="
docker exec fstock-postgres psql -U "$DB_USER" -d "$DB_NAME" -c \
  "SELECT indexname, indexdef FROM pg_indexes WHERE tablename='feature_events' AND indexname LIKE '%pattern%';"

# IVFFlat 인덱스가 존재하면 교체
IVFFLAT_EXISTS=$(docker exec fstock-postgres psql -U "$DB_USER" -d "$DB_NAME" -tAc \
  "SELECT COUNT(*) FROM pg_indexes WHERE tablename='feature_events' AND indexname='idx_fevent_pattern';")
HNSW_EXISTS=$(docker exec fstock-postgres psql -U "$DB_USER" -d "$DB_NAME" -tAc \
  "SELECT COUNT(*) FROM pg_indexes WHERE tablename='feature_events' AND indexname='idx_fevent_pattern_hnsw';")

if [ "$HNSW_EXISTS" = "1" ] && [ "$IVFFLAT_EXISTS" = "1" ]; then
  log "IVFFlat 삭제 + HNSW 이름 교체..."
  docker exec fstock-postgres psql -U "$DB_USER" -d "$DB_NAME" -c \
    "DROP INDEX CONCURRENTLY idx_fevent_pattern;"
  docker exec fstock-postgres psql -U "$DB_USER" -d "$DB_NAME" -c \
    "ALTER INDEX idx_fevent_pattern_hnsw RENAME TO idx_fevent_pattern;"
  log "인덱스 교체 완료: idx_fevent_pattern (HNSW)"
elif [ "$HNSW_EXISTS" = "1" ] && [ "$IVFFLAT_EXISTS" = "0" ]; then
  log "IVFFlat 없음, HNSW만 이름 변경..."
  docker exec fstock-postgres psql -U "$DB_USER" -d "$DB_NAME" -c \
    "ALTER INDEX idx_fevent_pattern_hnsw RENAME TO idx_fevent_pattern;"
  log "인덱스 교체 완료"
else
  log "ERROR: HNSW 인덱스 생성 실패! 건너뜀."
fi

log "최종 인덱스 상태:"
docker exec fstock-postgres psql -U "$DB_USER" -d "$DB_NAME" -c \
  "SELECT indexname, indexdef FROM pg_indexes WHERE tablename='feature_events' AND indexname LIKE '%pattern%';"

log "=== Step 3: ML 모델 학습 시작 ==="
cd "$COMPOSE_DIR"
docker compose exec -T ml python walk_forward_train.py \
  --train-start 2022-01-01 \
  --train-end   2024-06-30 \
  --val-start   2024-07-01 \
  --val-end     2025-06-30 \
  --test-start  2025-07-01 \
  --test-end    2026-06-15 \
  --smote \
  --model-dir /models/lgbm \
  --max-codes 500 \
  2>&1 | tee -a "$LOG"

log "=== 전체 완료 — HNSW 인덱스 + ML 학습 ==="
