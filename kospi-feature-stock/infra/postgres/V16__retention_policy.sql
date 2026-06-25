-- V16: TimescaleDB 데이터 보존 정책 (Retention Policy)
-- tick_data: 2개월, minute_bars: 1년
-- add_retention_policy는 DROP CHUNKS를 자동 스케줄링 (기본 1일 주기)

-- tick_data: 틱 데이터는 2개월 후 자동 삭제
-- 청크 단위(1일)로 삭제되므로 실제 삭제 시점은 만료 후 다음 스케줄 실행 시
SELECT add_retention_policy(
    'tick_data',
    INTERVAL '2 months',
    if_not_exists => TRUE
);

-- minute_bars: 분봉 데이터는 1년 후 자동 삭제
-- 청크 단위(7일)로 삭제
SELECT add_retention_policy(
    'minute_bars',
    INTERVAL '1 year',
    if_not_exists => TRUE
);

-- 적용된 보존 정책 확인
SELECT
    j.hypertable_name,
    j.config ->> 'drop_after' AS drop_after,
    j.schedule_interval,
    j.next_start
FROM timescaledb_information.jobs j
WHERE j.proc_name = 'policy_retention';
