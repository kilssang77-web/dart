#!/bin/bash
# KIS 실전 계좌 승인 후 REST 폴링 → WebSocket 실시간 탐지 전환 스크립트
# 실행 위치: quant-eye-server GCP VM
# 사전 조건: .env에 KIS_APP_KEY / KIS_APP_SECRET / KIS_ACCOUNT_NO 설정 완료
#
# 사용법:
#   chmod +x switch_to_websocket.sh
#   ./switch_to_websocket.sh

set -euo pipefail

COMPOSE_FILE="$(dirname "$0")/docker-compose.detector.yml"
ENV_FILE="$(dirname "$0")/.env"

echo "====== WebSocket 전환 스크립트 ======"

# 1. KIS 키 설정 확인
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ .env 파일 없음: $ENV_FILE"
    exit 1
fi

if ! grep -q "KIS_APP_KEY=" "$ENV_FILE" || grep -q "KIS_APP_KEY=$" "$ENV_FILE"; then
    echo "❌ .env에 KIS_APP_KEY 미설정. 실전 계좌 승인 후 설정하세요."
    exit 1
fi
if ! grep -q "KIS_APP_SECRET=" "$ENV_FILE" || grep -q "KIS_APP_SECRET=$" "$ENV_FILE"; then
    echo "❌ .env에 KIS_APP_SECRET 미설정."
    exit 1
fi

echo "✅ KIS 키 확인 완료"

# 2. 코드 최신화
echo "→ git pull..."
cd ~/quant/repo
git pull origin master

# 3. fstock-intraday-poller 중지 (REST 폴링 → WebSocket으로 대체)
echo "→ fstock-intraday-poller 중지 (REST 폴링 중단)..."
if docker ps --format '{{.Names}}' | grep -q "fstock-intraday-poller"; then
    docker stop fstock-intraday-poller || true
    docker rm   fstock-intraday-poller || true
    echo "  ✅ REST 폴링 컨테이너 중지"
else
    echo "  ℹ️  fstock-intraday-poller 미실행 상태"
fi

# 4. WebSocket 탐지기 빌드 & 시작
echo "→ realtime-ws-detector 빌드 및 시작..."
cd ~/quant/repo/kospi-feature-stock
docker compose -f deploy/gcp/docker-compose.detector.yml \
    up -d --build realtime-ws-detector

echo "→ 30초 대기 후 상태 확인..."
sleep 30

STATUS=$(docker inspect --format='{{.State.Status}}' fstock-realtime-ws-detector 2>/dev/null || echo "not_found")
if [ "$STATUS" = "running" ]; then
    echo "✅ fstock-realtime-ws-detector 정상 실행 중"
    echo ""
    echo "=== 최근 로그 ==="
    docker logs fstock-realtime-ws-detector --tail=20
else
    echo "❌ 컨테이너 상태: $STATUS"
    echo "=== 오류 로그 ==="
    docker logs fstock-realtime-ws-detector --tail=30
    echo ""
    echo "⚠️  WebSocket 전환 실패. fstock-intraday-poller 재시작 권장:"
    echo "    docker start fstock-intraday-poller"
    exit 1
fi

echo ""
echo "====== 전환 완료 ======"
echo "REST 폴링 → WebSocket 실시간 탐지 전환 성공"
echo "모니터링: docker logs -f fstock-realtime-ws-detector"
