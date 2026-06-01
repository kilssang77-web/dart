@echo off
chcp 65001 > nul
echo 건설 입찰 분석 시스템 시작 중...
docker compose up -d
echo.
echo 접속 주소: http://localhost:3001
echo 종료하려면 stop.bat 실행
