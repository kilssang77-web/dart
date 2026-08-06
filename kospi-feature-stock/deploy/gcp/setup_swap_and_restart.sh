#!/usr/bin/env bash
# Step 3 + 4: GCP e2-micro swap 2GB 추가 + systemd RestartSec 10초 변경
# 실행: bash ~/repo/kospi-feature-stock/deploy/gcp/setup_swap_and_restart.sh

set -e

# ── Step 4: swap 2GB ──────────────────────────────────────────
if [ ! -f /swapfile ]; then
    echo "[Step 4] swap 파일 생성 (2GB)..."
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "swap 활성화 완료:"
    free -h
else
    echo "[Step 4] swap 파일 이미 존재 — 스킵"
    free -h
fi

# ── Step 3: systemd RestartSec 10초 변경 ─────────────────────
for SVC in ws-detector ws-notifier; do
    SVC_FILE="/etc/systemd/system/${SVC}.service"
    if [ -f "$SVC_FILE" ]; then
        echo "[Step 3] ${SVC}.service RestartSec 설정..."
        # RestartSec이 있으면 10으로, 없으면 추가
        if grep -q "RestartSec" "$SVC_FILE"; then
            sudo sed -i 's/RestartSec=.*/RestartSec=10/' "$SVC_FILE"
        else
            sudo sed -i '/^\[Service\]/a RestartSec=10\nStartLimitIntervalSec=0' "$SVC_FILE"
        fi
        echo "  수정 완료"
    else
        echo "  [경고] ${SVC_FILE} 파일 없음 — 스킵"
    fi
done

sudo systemctl daemon-reload
sudo systemctl restart ws-detector ws-notifier 2>/dev/null || true

echo ""
echo "=== 완료 ==="
echo "서비스 상태:"
sudo systemctl status ws-detector ws-notifier --no-pager -l | tail -20
