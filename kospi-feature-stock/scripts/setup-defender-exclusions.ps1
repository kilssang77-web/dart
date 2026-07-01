# ─────────────────────────────────────────────────────────────────────────────
# setup-defender-exclusions.ps1
# Windows Defender 실시간 검사에서 Docker·WSL 경로를 제외합니다.
#
# 실행 방법 (반드시 관리자 PowerShell에서):
#   우클릭 → "관리자 권한으로 실행"
#   .\scripts\setup-defender-exclusions.ps1
# ─────────────────────────────────────────────────────────────────────────────

if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]"Administrator")) {
    Write-Host "이 스크립트는 관리자 권한으로 실행해야 합니다." -ForegroundColor Red
    Write-Host "PowerShell을 우클릭 → '관리자 권한으로 실행' 후 다시 시도하세요."
    exit 1
}

Write-Host "Windows Defender 제외 경로 설정 중..." -ForegroundColor Cyan

$exclusionPaths = @(
    # Docker Desktop 관련
    "$env:LOCALAPPDATA\Docker",
    "C:\ProgramData\DockerDesktop",
    "$env:USERPROFILE\.docker",
    # WSL 관련
    "$env:LOCALAPPDATA\Packages\CanonicalGroupLimited.Ubuntu_79rhkp1fndgsc",
    "$env:LOCALAPPDATA\Packages\CanonicalGroupLimited.UbuntuonWindows_79rhkp1fndgsc",
    # 프로젝트 디렉토리 (자주 변경되는 파일 → 검사 불필요)
    "D:\a2m"
)

$exclusionProcesses = @(
    "docker.exe",
    "dockerd.exe",
    "com.docker.proxy.exe",
    "wsl.exe",
    "wslhost.exe"
)

foreach ($path in $exclusionPaths) {
    try {
        Add-MpPreference -ExclusionPath $path -ErrorAction Stop
        Write-Host "  [경로 제외] $path" -ForegroundColor Green
    } catch {
        Write-Host "  [실패] $path — $_" -ForegroundColor Yellow
    }
}

foreach ($proc in $exclusionProcesses) {
    try {
        Add-MpPreference -ExclusionProcess $proc -ErrorAction Stop
        Write-Host "  [프로세스 제외] $proc" -ForegroundColor Green
    } catch {
        Write-Host "  [실패] $proc — $_" -ForegroundColor Yellow
    }
}

# Defender 예약 검사를 새벽 3시로 변경 (Docker 실행 중 검사 방지)
Write-Host "`n예약 검사 시간을 새벽 3시로 변경 중..." -ForegroundColor Cyan
try {
    Set-MpPreference -ScanScheduleTime 03:00:00 -ErrorAction Stop
    Set-MpPreference -ScanScheduleDay 1 -ErrorAction Stop  # 1=일요일
    Write-Host "  예약 검사: 매주 일요일 03:00 으로 설정됨" -ForegroundColor Green
} catch {
    Write-Host "  예약 검사 변경 실패: $_" -ForegroundColor Yellow
}

Write-Host "`n완료!" -ForegroundColor Green
Write-Host "현재 제외 목록 확인:"
Get-MpPreference | Select-Object -ExpandProperty ExclusionPath | ForEach-Object { Write-Host "  $_" }
