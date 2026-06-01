@echo off
chcp 65001 > nul
echo ============================================
echo   다른 PC 배포용 패키지 생성
echo ============================================
echo.

set DIST_NAME=bid-system-dist
if exist %DIST_NAME% rmdir /s /q %DIST_NAME%
mkdir %DIST_NAME%

:: 필요 파일만 복사 (node_modules, __pycache__ 제외)
xcopy /E /I /Q /EXCLUDE:exclude_list.txt . %DIST_NAME% > nul

:: 배포 README 생성
echo 설치 방법 > %DIST_NAME%\설치방법.txt
echo. >> %DIST_NAME%\설치방법.txt
echo 1. Docker Desktop 설치 (https://www.docker.com/products/docker-desktop/) >> %DIST_NAME%\설치방법.txt
echo 2. install.bat 을 관리자 권한으로 실행 >> %DIST_NAME%\설치방법.txt
echo 3. 브라우저에서 http://localhost:3000 접속 >> %DIST_NAME%\설치방법.txt
echo. >> %DIST_NAME%\설치방법.txt
echo 기본 계정: admin@bid.local / admin1234 >> %DIST_NAME%\설치방법.txt

echo 완료: %DIST_NAME% 폴더를 ZIP으로 압축해서 다른 PC에 복사하세요.
pause
