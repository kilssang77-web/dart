#!/usr/bin/env bash
# GCP quant-scanner crontab 설정 스크립트
# Usage: bash setup_gcp_cron.sh
# 실행 후 crontab -l 로 확인

set -e

VENV="/home/kilsnag0910/quant/venv/bin/python"
SCRIPTS="/home/kilsnag0910/quant/repo/kospi-feature-stock/scripts"
LOG="/home/kilsnag0910/quant/logs"

mkdir -p "$LOG"

# realtime_pipeline.py 는 systemd 로 관리 (cron 아님)
# 아래는 보조 cron 작업만 등록

crontab -l 2>/dev/null | grep -v "quant" | grep -v "^#.*quant" > /tmp/crontab_clean.txt || true

cat >> /tmp/crontab_clean.txt << CRON
# ── KOSPI Quant Scanner (GCP quant-scanner) ──────────────────
# 장 마감 스캔: KST 16:30 = UTC 07:30
30 7 * * 1-5 $VENV $SCRIPTS/market_scan.py >> $LOG/market_scan.log 2>&1

# 성과 추적: KST 18:00 = UTC 09:00
0 9 * * 1-5 $VENV $SCRIPTS/result_tracker.py >> $LOG/result_tracker.log 2>&1

# Telegram 봇 폴링: 5분 간격 (24시간)
*/5 * * * * $VENV $SCRIPTS/telegram_bot.py >> $LOG/telegram_bot.log 2>&1

# 보유 종목 손절/목표가 모니터: 장 중 30분 간격 (KST 09:00~15:30)
*/30 0-6 * * 1-5 $VENV $SCRIPTS/hold_monitor.py >> $LOG/hold_monitor.log 2>&1

# ─────────────────────────────────────────────────────────────
CRON

crontab /tmp/crontab_clean.txt
rm /tmp/crontab_clean.txt

echo "crontab 등록 완료:"
crontab -l

echo ""
echo "=== realtime_pipeline systemd 서비스 설치 ==="
echo "아래 명령어를 root로 실행하세요:"
echo "  sudo cp /home/kilsnag0910/quant/repo/kospi-feature-stock/deploy/realtime_pipeline.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable realtime-pipeline"
echo "  sudo systemctl start realtime-pipeline"
echo "  sudo systemctl status realtime-pipeline"
