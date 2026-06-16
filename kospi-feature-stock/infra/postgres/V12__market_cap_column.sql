-- V12: daily_bars에 시가총액 컬럼 추가 (금융위원회 API 수집)
ALTER TABLE daily_bars ADD COLUMN IF NOT EXISTS market_cap BIGINT DEFAULT 0;
