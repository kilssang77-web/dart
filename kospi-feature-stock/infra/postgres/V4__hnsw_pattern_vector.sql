-- Upgrade feature_events pattern_vector index from ivfflat to HNSW
-- HNSW provides better recall and no training requirement
DROP INDEX IF EXISTS idx_fevent_pattern;
CREATE INDEX IF NOT EXISTS idx_fevent_pattern ON feature_events
    USING hnsw (pattern_vector vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
COMMENT ON INDEX idx_fevent_pattern IS 'HNSW ANN index for cosine similarity search on 256-dim pattern vectors';
