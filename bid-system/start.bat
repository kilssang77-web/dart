@echo off
chcp 65001 > nul
echo 건설 입찰 분석 시스템 시작 중...

:: .env에서 APP_PORT 읽기 (없으면 기본값 3003)
set APP_PORT=3003
for /f "tokens=1,2 delims==" %%A in (.env) do (
    if "%%A"=="APP_PORT" set APP_PORT=%%B
)

docker compose up -d
echo.
echo 접속 주소: http://localhost:%APP_PORT%
echo 종료하려면 stop.bat 실행
