# 성능 최적화 배포 스크립트
# 사용법: ./deploy_perf.ps1
Set-Location $PSScriptRoot

Write-Host "=== 1. DB 인덱스 적용 ===" -ForegroundColor Cyan
docker exec bid_postgres psql -U biduser -d biddb -c @'
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bids_status         ON bids(status);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bids_agency_id      ON bids(agency_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bids_industry_id    ON bids(industry_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bids_region_id      ON bids(region_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bids_notice_date    ON bids(notice_date);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bids_bid_open_date  ON bids(bid_open_date);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bid_results_bid_id        ON bid_results(bid_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bid_results_competitor_id ON bid_results(competitor_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bid_results_bid_winner    ON bid_results(bid_id, is_winner);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_inpo21c_part_bid_winner   ON inpo21c_participants(inpo21c_bid_id, is_winner);
'@

Write-Host "=== 2. Redis 재시작 (메모리 1gb 적용) ===" -ForegroundColor Cyan
docker compose restart redis

Write-Host "=== 3. 백엔드 재빌드 ===" -ForegroundColor Cyan
docker compose build --no-cache backend
docker compose up -d backend

Write-Host "=== 4. 프론트엔드 재빌드 ===" -ForegroundColor Cyan
docker compose build --no-cache frontend
docker compose up -d frontend nginx

Write-Host "=== 완료 ===" -ForegroundColor Green
docker compose ps
