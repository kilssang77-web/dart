#!/bin/bash
set -e
LOG() { echo "[$(date '+%H:%M:%S')] $*"; }

TOTAL=1546188
THRESHOLD=1500000   # 97% 이상이면 완료 간주

LOG "=== Step 1: 벡터 백필 완료 대기 ==="
while true; do
  HAS_VEC=$(docker exec fstock-postgres psql -U stockuser -d feature_stock -t -c \
    "SELECT COUNT(*) FROM feature_events WHERE pattern_vector IS NOT NULL;" 2>/dev/null | tr -d ' ')
  LOG "벡터 완료: ${HAS_VEC}/${TOTAL}"
  if [ "${HAS_VEC:-0}" -ge "$THRESHOLD" ] 2>/dev/null; then
    LOG "백필 충분히 완료 (${HAS_VEC}건)"
    break
  fi
  sleep 120
done

LOG "=== Step 2: HNSW 인덱스 생성 ==="
docker exec fstock-postgres psql -U stockuser -d feature_stock -c \
  "SET max_parallel_maintenance_workers = 0;
   SET maintenance_work_mem = '512MB';
   CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fevent_pattern_hnsw
     ON feature_events USING hnsw (pattern_vector vector_cosine_ops)
     WITH (m = 16, ef_construction = 64);" 2>&1
HNSW_CODE=$?

if [ $HNSW_CODE -eq 0 ]; then
  LOG "HNSW 인덱스 생성 성공 — IVFFlat 교체"
  docker exec fstock-postgres psql -U stockuser -d feature_stock -c \
    "DROP INDEX IF EXISTS idx_fevent_pattern;
     ALTER INDEX idx_fevent_pattern_hnsw RENAME TO idx_fevent_pattern;" 2>&1
  LOG "인덱스 교체 완료"
else
  LOG "HNSW 실패(코드=$HNSW_CODE) — IVFFlat 유지"
fi

LOG "=== Step 3: make train ==="
cd /d/a2m/atom-harness-base-Dart/kospi-feature-stock
docker compose exec -T ml python walk_forward_train.py \
  --train-start 2022-01-01 --train-end 2024-06-30 \
  --val-start 2024-07-01   --val-end   2025-06-30 \
  --test-start 2025-07-01  --test-end  2026-06-15 \
  --smote --model-dir /models/lgbm --max-codes 500 2>&1
TRAIN_CODE=$?

LOG "=== 완료 (train exit=$TRAIN_CODE) ==="
docker exec fstock-postgres psql -U stockuser -d feature_stock -t -c \
  "SELECT version, metrics->>'auc' AS val_auc, metrics->>'test_auc' AS test_auc
   FROM ml_models ORDER BY trained_at DESC LIMIT 1;" 2>/dev/null
