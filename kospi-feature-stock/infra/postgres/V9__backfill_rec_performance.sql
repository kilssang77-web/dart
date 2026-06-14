-- 기존 BUY 추천 데이터를 recommendation_performance 에 백필
-- recommender 서비스 재시작 후 한 번 실행하면 됨
INSERT INTO recommendation_performance (rec_id, code, entry_price, event_type, signal_time)
SELECT
    r.id,
    r.code,
    r.entry_price,
    (r.rationale::json ->> 'event_type'),
    r.created_at
FROM recommendations r
WHERE r.action = 'BUY'
ON CONFLICT (rec_id) DO NOTHING;
