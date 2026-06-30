-- V18: feature_events 중복 제거
-- (code, 날짜, event_type) 그룹당 1건 유지
-- 우선순위: result_5d 있는 것 > signal_score 높은 것 > id 큰 것(최신)
BEGIN;

SET timescaledb.max_tuples_decompressed_per_dml_transaction = 0;

DELETE FROM feature_events
WHERE id NOT IN (
    SELECT DISTINCT ON (code, DATE_TRUNC('day', detected_at AT TIME ZONE 'Asia/Seoul'), event_type)
        id
    FROM feature_events
    ORDER BY
        code,
        DATE_TRUNC('day', detected_at AT TIME ZONE 'Asia/Seoul'),
        event_type,
        CASE WHEN result_5d IS NOT NULL THEN 0 ELSE 1 END,
        signal_score DESC NULLS LAST,
        id DESC
);

COMMIT;
