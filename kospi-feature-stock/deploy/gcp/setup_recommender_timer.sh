#!/usr/bin/env bash
# GCP e2-micro: ML 추천 생성 + Telegram 알림 systemd timer 설정
# 실행: bash ~/repo/kospi-feature-stock/deploy/gcp/setup_recommender_timer.sh
# 사전 조건: ~/quant/venv 가상환경, ~/quant/.env 환경변수 파일 존재

set -e

REPO="/home/kilsnag0910/quant/repo"
VENV="/home/kilsnag0910/quant/venv"
ENV_FILE="/home/kilsnag0910/quant/.env"
LOG_DIR="/home/kilsnag0910/quant/logs"
LGBM_DIR="$REPO/kospi-feature-stock/services/api/lgbm_export"

mkdir -p "$LOG_DIR"

# ── 1. 의존성 설치 ────────────────────────────────────────────
echo "[1/4] 추천 ML 라이브러리 설치..."
"$VENV/bin/pip" install -q -r "$REPO/kospi-feature-stock/services/recommender/requirements.txt"

# ── 2. 추천 생성 실행 스크립트 ───────────────────────────────
cat > /home/kilsnag0910/quant/run_rec_worker.sh << 'SCRIPT'
#!/usr/bin/env bash
set -a
source /home/kilsnag0910/quant/.env
set +a

export LGBM_MODEL_DIR="/home/kilsnag0910/quant/repo/kospi-feature-stock/services/api/lgbm_export"
export REC_RECOVERY_HOURS="3"
export REC_COOLDOWN_MINUTES="90"
export PYTHONPATH="/home/kilsnag0910/quant/repo/kospi-feature-stock/services/recommender"

VENV="/home/kilsnag0910/quant/venv"
REPO="/home/kilsnag0910/quant/repo"
LOG="/home/kilsnag0910/quant/logs/rec_worker.log"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') rec_worker 시작 ===" >> "$LOG"
"$VENV/bin/python" "$REPO/kospi-feature-stock/services/recommender/entrypoints/daily_rec_worker.py" >> "$LOG" 2>&1
echo "=== $(date '+%Y-%m-%d %H:%M:%S') rec_worker 완료 ===" >> "$LOG"

# Telegram 개별 알림 (35분 이내 신규 추천)
"$VENV/bin/python" "$REPO/kospi-feature-stock/scripts/send_telegram_alerts.py" >> "$LOG" 2>&1
echo "=== $(date '+%Y-%m-%d %H:%M:%S') Telegram 알림 완료 ===" >> "$LOG"
SCRIPT
chmod +x /home/kilsnag0910/quant/run_rec_worker.sh

# ── 3. systemd service 파일 ───────────────────────────────────
echo "[2/4] systemd service 파일 생성..."
sudo tee /etc/systemd/system/rec-worker.service > /dev/null << 'SERVICE'
[Unit]
Description=KOSPI ML Recommendation Worker
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=kilsnag0910
ExecStart=/home/kilsnag0910/quant/run_rec_worker.sh
TimeoutStartSec=600
StandardOutput=journal
StandardError=journal
SERVICE

# ── 4. systemd timer 파일 (장중 2시간 간격, 09:00~15:00 KST) ─
echo "[3/4] systemd timer 파일 생성..."
sudo tee /etc/systemd/system/rec-worker.timer > /dev/null << 'TIMER'
[Unit]
Description=Run ML Recommendation Worker every 2 hours during market hours

[Timer]
# KST 09:00, 11:00, 13:00, 15:00 = UTC 00:00, 02:00, 04:00, 06:00
OnCalendar=Mon..Fri 00:00:00 UTC
OnCalendar=Mon..Fri 02:00:00 UTC
OnCalendar=Mon..Fri 04:00:00 UTC
OnCalendar=Mon..Fri 06:00:00 UTC
Persistent=false
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
TIMER

# ── 5. 활성화 ─────────────────────────────────────────────────
echo "[4/4] timer 활성화..."
sudo systemctl daemon-reload
sudo systemctl enable --now rec-worker.timer

echo ""
echo "완료! 현재 timer 상태:"
sudo systemctl list-timers rec-worker.timer --no-pager
echo ""
echo "로그 확인: tail -f /home/kilsnag0910/quant/logs/rec_worker.log"
echo "수동 실행: sudo systemctl start rec-worker.service"
