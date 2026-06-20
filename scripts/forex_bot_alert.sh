#!/bin/bash
# Gửi cảnh báo Telegram khi forex-bot.service fail, có cooldown để chống spam
# khi service bị crash-loop (restart liên tục).
#
# Cài đặt:
#   1. chmod +x forex_bot_alert.sh
#   2. Thêm OnFailure=forex-bot-alert.service vào [Unit] của forex-bot.service
#   3. Tạo forex-bot-alert.service (xem systemd/forex-bot-alert.service)
#   4. systemctl daemon-reload

set -euo pipefail

BOT_TOKEN="8821195660:AAFg4DyaWQhJNztpE6elW06A91_34xz50k4"
CHAT_ID="7457950702"
COOLDOWN_FILE="/root/API_FOREX/.alert_cooldown"
COOLDOWN_SECONDS=600   # 10 phút

now=$(date +%s)
last=0
if [[ -f "$COOLDOWN_FILE" ]]; then
    last=$(cat "$COOLDOWN_FILE" 2>/dev/null || echo 0)
fi

if (( now - last < COOLDOWN_SECONDS )); then
    # Vẫn trong thời gian cooldown -> không gửi, tránh spam
    exit 0
fi

echo "$now" > "$COOLDOWN_FILE"

MSG="🔴 forex-bot.service FAILED on $(hostname) at $(date -u '+%Y-%m-%d %H:%M:%S UTC')
Check: systemctl status forex-bot --no-pager | journalctl -u forex-bot -n 30 --no-pager"

curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -d chat_id="${CHAT_ID}" \
    -d text="${MSG}" > /dev/null
