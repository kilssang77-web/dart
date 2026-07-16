-- 일별·이벤트 유형별 추천 성과 집계 Materialized View
-- /ml/performance-trend, /ml/event-performance 쿼리 가속
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_rec_stats; (API가 1시간 주기 자동 갱신)
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_daily_rec_stats AS
SELECT
    DATE(rec.created_at AT TIME ZONE 'Asia/Seoul')          AS day,
    COALESCE(rp.event_type, 'UNKNOWN')                      AS event_type,
    COUNT(*)                                                 AS total,
    COUNT(*) FILTER (WHERE rp.tracking_complete = TRUE)     AS completed,
    COUNT(*) FILTER (WHERE rp.is_success = TRUE)            AS wins,
    ROUND(AVG(rp.r_1d)::NUMERIC,  4)                        AS avg_return_1d,
    ROUND(AVG(rp.r_3d)::NUMERIC,  4)                        AS avg_return_3d,
    ROUND(AVG(rp.r_5d)::NUMERIC,  4)                        AS avg_return_5d,
    ROUND(AVG(rp.r_10d)::NUMERIC, 4)                        AS avg_return_10d,
    ROUND(AVG(rp.max_return)::NUMERIC, 4)                   AS avg_max_return,
    ROUND(AVG(rec.success_prob)::NUMERIC, 4)                AS avg_pred_prob
FROM recommendations rec
JOIN recommendation_performance rp ON rp.rec_id = rec.id
GROUP BY 1, 2;

-- CONCURRENTLY refresh를 위해 UNIQUE 인덱스 필수
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mv_daily_rec_stats_day_event
    ON mv_daily_rec_stats (day, event_type);
