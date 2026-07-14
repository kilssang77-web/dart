@echo off
chcp 65001 > nul
echo ============================================
echo   건설 입찰 분석 시스템 설치 프로그램
echo ============================================
echo.

:: 관리자 권한 확인
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [오류] 관리자 권한으로 실행해주세요.
    echo 이 파일을 우클릭 → "관리자 권한으로 실행"
    pause
    exit /b 1
)

:: Docker Desktop 설치 여부 확인
docker --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [1/4] Docker Desktop을 설치합니다...
    echo.
    echo Docker Desktop 다운로드 페이지를 엽니다.
    echo 설치 완료 후 이 스크립트를 다시 실행하세요.
    start https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
) else (
    echo [1/4] Docker Desktop 확인 완료
)

:: .env 파일 생성
if not exist ".env" (
    echo [2/4] 환경설정 파일 생성 중...
    copy .env.example .env
    echo     .env 파일이 생성되었습니다.
    echo     필요시 .env 파일을 수정하세요.
) else (
    echo [2/4] .env 파일 이미 존재 - 건너뜀
)

:: Docker 이미지 빌드
echo [3/4] Docker 이미지 빌드 중... (최초 실행 시 10-20분 소요)
docker compose build
if %errorLevel% neq 0 (
    echo [오류] 이미지 빌드 실패. Docker Desktop이 실행 중인지 확인하세요.
    pause
    exit /b 1
)

:: 서비스 시작
echo [4/4] 서비스 시작 중...
docker compose up -d
if %errorLevel% neq 0 (
    echo [오류] 서비스 시작 실패.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   설치 완료!
echo ============================================
echo.
echo 브라우저에서 아래 주소로 접속하세요:
echo   http://localhost:3001
echo.
echo 초기 관리자 계정:
echo   이메일: admin@bid.local
echo   비밀번호: admin1234
echo.
echo (DB 초기화까지 약 30초 소요됩니다)
echo.
pause
