# ============================================================
# nightly_cleanup.ps1  — 매일 새벽 2시 Windows Task Scheduler 실행
# 목적: Docker 메모리 누수·로그·Dead tuple 자동 정리
# ============================================================

$LOG = "D:\a2m\atom-harness-base-Dart\kospi-feature-stock\infra\maintenance\cleanup.log"
$TS  = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")

function Log($msg) { "$TS $msg" | Tee-Object -FilePath $LOG -Append }

Log "===== 야간 정비 시작 ====="

# ── 1. Python 서비스 재시작 (메모리 누수 초기화) ─────────────────
$RESTART_TARGETS = @(
    "fstock-api",          # 1.06GB — FastAPI, 장시간 누수
    "fstock-analyzer",     # 325MB  — 감성분석 모델 상주
    "fstock-recommender",  # ML 추론 캐시
    "fstock-detector",     # Kafka consumer
    "fstock-notifier"
)

foreach ($svc in $RESTART_TARGETS) {
    Log "  재시작: $svc"
    docker restart $svc 2>&1 | Out-Null
    Start-Sleep -Seconds 3
}
Log "  서비스 재시작 완료"

# ── 2. PostgreSQL VACUUM (dead tuples 정리) ──────────────────────
Log "  PostgreSQL VACUUM ANALYZE 시작"
$TABLES = @("daily_bars", "supply_demand", "feature_events", "news", "disclosures", "recommendations")
foreach ($tbl in $TABLES) {
    docker exec fstock-postgres psql -U stockuser -d feature_stock -c "VACUUM ANALYZE $tbl;" 2>&1 | Out-Null
}
# TimescaleDB 청크 압축 (오래된 청크)
docker exec fstock-postgres psql -U stockuser -d feature_stock -c `
    "SELECT compress_chunk(c) FROM show_chunks('daily_bars', older_than => INTERVAL '30 days') c;" 2>&1 | Out-Null
Log "  VACUUM 완료"

# ── 3. Docker 컨테이너 로그 초기화 (100MB 이상) ──────────────────
Log "  컨테이너 로그 정리"
docker ps -q | ForEach-Object {
    $info = docker inspect --format='{{.LogPath}}' $_ 2>$null
    if ($info -and (Test-Path $info)) {
        $sizeMB = [math]::Round((Get-Item $info).Length / 1MB, 1)
        if ($sizeMB -gt 100) {
            Clear-Content $info -ErrorAction SilentlyContinue
            Log "    로그 초기화: $_ (${sizeMB}MB)"
        }
    }
}

# ── 4. Docker 이미지·빌드캐시 정리 (7일 이상 미사용) ────────────
Log "  Docker 정리"
$reclaimed = docker image prune -f 2>&1 | Select-String "reclaimed"
docker builder prune --filter "until=168h" -f 2>&1 | Out-Null
Log "  $reclaimed"

# ── 5. Redis 캐시 통계 확인 (이상 시 flush) ─────────────────────
$redisMem = docker exec fstock-redis redis-cli INFO memory 2>$null |
    Select-String "used_memory_human" | ForEach-Object { $_.Line }
Log "  Redis: $redisMem"

# ── 6. WSL2 메모리 반환 유도 ────────────────────────────────────
Log "  WSL2 메모리 정리"
wsl --exec bash -c "echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null 2>&1" 2>$null
Log "  완료"

# ── 7. 디스크 여유 확인 ─────────────────────────────────────────
$disk = Get-PSDrive C | Select-Object @{N='free_GB';E={[math]::Round($_.Free/1GB,1)}}
Log "  C: 드라이브 여유: $($disk.free_GB) GB"

Log "===== 야간 정비 완료 ====="
