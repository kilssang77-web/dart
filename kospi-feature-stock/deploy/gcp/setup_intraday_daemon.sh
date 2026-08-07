#!/usr/bin/env bash
# quant-scanner에서 실행 — 장중 5분 polling daemon 설치
# 역할: GitHub Actions market-scan-intraday.yml 을 대체
# 실행: bash ~/quant/repo/kospi-feature-stock/deploy/gcp/setup_intraday_daemon.sh
set -e

REPO="/home/kilsnag0910/quant/repo/kospi-feature-stock"
VENV="/home/kilsnag0910/quant/venv"
LOG_DIR="/home/kilsnag0910/quant/logs"
ENV_FILE="/home/kilsnag0910/.env"
USER="kilsnag0910"

mkdir -p "$LOG_DIR"

# ── 실행 스크립트 생성 ──────────────────────────────────────────────
cat > /home/kilsnag0910/quant/run_intraday_scan.sh << 'SCRIPT'
#!/usr/bin/env bash
# 장중에만 실행 (KST 09:00~15:35 = UTC 00:00~06:35, 평일)
HOUR_UTC=$(date -u +%H)
MIN_UTC=$(date -u +%M)
DOW=$(date -u +%u)  # 1=월 ~ 7=일

# 평일(1-5)만
if [ "$DOW" -gt 5 ]; then exit 0; fi

# UTC 00:00~06:35 (KST 09:00~15:35) 만
TOTAL_MIN=$((HOUR_UTC * 60 + MIN_UTC))
if [ "$TOTAL_MIN" -lt 0 ] || [ "$TOTAL_MIN" -gt 395 ]; then exit 0; fi

set -a; source /home/kilsnag0910/.env; set +a
export PYTHONPATH="/home/kilsnag0910/quant/repo/kospi-feature-stock/services/collector"
export PYTHONPATH="$PYTHONPATH:/home/kilsnag0910/quant/repo/kospi-feature-stock/services/recommender"
export REC_RECOVERY_HOURS="2"
export REC_COOLDOWN_MINUTES="60"
LOG="/home/kilsnag0910/quant/logs/intraday_scan.log"

echo "=== $(date '+%Y-%m-%d %H:%M:%S KST') intraday scan ===" >> "$LOG"

# 1단계: 장중 종목 스캔 + feature_events 생성
/home/kilsnag0910/quant/venv/bin/python \
  /home/kilsnag0910/quant/repo/kospi-feature-stock/services/collector/entrypoints/intraday_poller.py \
  >> "$LOG" 2>&1 || true

# 2단계: 신규 feature_events → ML 추천 생성
/home/kilsnag0910/quant/venv/bin/python \
  /home/kilsnag0910/quant/repo/kospi-feature-stock/services/recommender/entrypoints/daily_rec_worker.py \
  >> "$LOG" 2>&1 || true

# 3단계: 신규 추천 → Telegram 즉시 발송
/home/kilsnag0910/quant/venv/bin/python \
  /home/kilsnag0910/quant/repo/kospi-feature-stock/scripts/send_telegram_alerts.py \
  >> "$LOG" 2>&1 || true

echo "=== $(date '+%Y-%m-%d %H:%M:%S KST') 완료 ===" >> "$LOG"
SCRIPT

chmod +x /home/kilsnag0910/quant/run_intraday_scan.sh

# ── systemd service 생성 ──────────────────────────────────────────
sudo tee /etc/systemd/system/intraday-scan.service << EOF
[Unit]
Description=Intraday Market Scanner (5min polling)
After=network.target

[Service]
Type=oneshot
User=$USER
ExecStart=/home/kilsnag0910/quant/run_intraday_scan.sh
TimeoutStartSec=240
StandardOutput=journal
StandardError=journal
EOF

# ── systemd timer 생성 (5분마다) ─────────────────────────────────
sudo tee /etc/systemd/system/intraday-scan.timer << EOF
[Unit]
Description=Run intraday scan every 5 minutes
Requires=intraday-scan.service

[Timer]
# 매 5분마다 실행, 장중 여부는 스크립트 내부에서 판단
OnCalendar=*:0/5
Persistent=false
RandomizedDelaySec=10

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable intraday-scan.timer
sudo systemctl start intraday-scan.timer

echo ""
echo "=== 설치 완료 ==="
echo "타이머 상태:"
systemctl list-timers intraday-scan.timer --no-pager
echo ""
echo "다음 실행 시간 확인:"
systemctl status intraday-scan.timer --no-pager | head -10
