# ─────────────────────────────────────────────────────────────────────────────
# docker-start.ps1  — 메모리 절약 모드 Docker 시작 스크립트
#
# 사용법:
#   .\scripts\docker-start.ps1           # 핵심 서비스만 (기본, 권장)
#   .\scripts\docker-start.ps1 monitoring # + Grafana/Prometheus
#   .\scripts\docker-start.ps1 retrain    # ML 재학습 (완료 후 자동 종료)
#   .\scripts\docker-start.ps1 backfill   # 일봉 재백필 (완료 후 자동 종료)
#   .\scripts\docker-start.ps1 all        # 전체 (메모리 여유 있을 때만)
# ─────────────────────────────────────────────────────────────────────────────

param([string]$Mode = "core")

Set-Location $PSScriptRoot\..

function Show-MemoryStatus {
    $os = Get-CimInstance Win32_OperatingSystem
    $freeMB = [math]::Round($os.FreePhysicalMemory / 1024)
    $totalMB = [math]::Round($os.TotalVisibleMemorySize / 1024)
    $usedMB = $totalMB - $freeMB
    $pct = [math]::Round($usedMB / $totalMB * 100)
    $color = if ($freeMB -lt 2000) { "Red" } elseif ($freeMB -lt 4000) { "Yellow" } else { "Green" }
    Write-Host "현재 RAM: ${usedMB}MB / ${totalMB}MB 사용 (여유: ${freeMB}MB, ${pct}% 사용)" -ForegroundColor $color
    if ($freeMB -lt 2000) {
        Write-Host "경고: 여유 RAM이 2GB 미만입니다. VS Code를 닫거나 불필요한 앱을 종료하세요." -ForegroundColor Red
    }
}

Show-MemoryStatus

switch ($Mode) {
    "core" {
        Write-Host "`n[핵심 서비스 시작] postgres, redis, collector, detector, analyzer, ml, recommender, notifier, api" -ForegroundColor Cyan
        docker compose up -d postgres redis collector-tick collector-daily collector-supply collector-news collector-batch collector-financials collector-govdata detector analyzer ml recommender notifier api
    }
    "monitoring" {
        Write-Host "`n[모니터링 포함 시작] 핵심 서비스 + Prometheus + Grafana" -ForegroundColor Cyan
        docker compose up -d postgres redis collector-tick collector-daily collector-supply collector-news collector-batch collector-financials collector-govdata detector analyzer ml recommender notifier api
        docker compose --profile monitoring up -d prometheus grafana
    }
    "retrain" {
        Write-Host "`n[ML 재학습] ml-autoretrain 단독 실행 (완료 후 자동 종료)" -ForegroundColor Yellow
        Write-Host "주의: 재학습 중 RAM 2GB 추가 사용. 다른 무거운 작업 자제하세요." -ForegroundColor Yellow
        docker compose --profile tools up ml-autoretrain
    }
    "backfill" {
        Write-Host "`n[일봉 백필] collector-bars-backfill 실행 (완료 후 자동 종료)" -ForegroundColor Yellow
        docker compose --profile backfill up collector-bars-backfill
    }
    "all" {
        Write-Host "`n[전체 시작] 모든 서비스 + 모니터링" -ForegroundColor Magenta
        Write-Host "주의: 전체 실행 시 Docker 7GB 상한에 도달할 수 있습니다." -ForegroundColor Yellow
        docker compose up -d
        docker compose --profile monitoring up -d prometheus grafana
    }
    default {
        Write-Host "알 수 없는 모드: $Mode" -ForegroundColor Red
        Write-Host "사용법: .\scripts\docker-start.ps1 [core|monitoring|retrain|backfill|all]"
    }
}

Write-Host "`n[시작 후 메모리]"
Start-Sleep -Seconds 3
Show-MemoryStatus
