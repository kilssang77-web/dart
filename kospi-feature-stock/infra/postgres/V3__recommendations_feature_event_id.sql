-- recommendations.feature_event_id 인덱스 추가
-- TimescaleDB hypertable은 복합 PK (id, detected_at)이므로 FK 제약 대신 인덱스만 추가
-- NOT EXISTS(SELECT 1 FROM recommendations WHERE feature_event_id = fe.id) 조건을 효율적으로 처리하기 위해 필요

ALTER TABLE recommendations
  ADD COLUMN IF NOT EXISTS feature_event_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_recommendations_feature_event_id
  ON recommendations(feature_event_id)
  WHERE feature_event_id IS NOT NULL;
