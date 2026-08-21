

#
source .venv/bin/activate
python3 main.py download

# Nếu muốn test 5m (cần update .env local trước):
python3 main.py backtest --symbol XAUUSD --tf 5m

# Hoặc dùng 15m (data đã có nếu đã download trước đây):
python3 main.py backtest --symbol XAUUSD --tf 15m

# pust from MAC
cd /Users/ngocdang/Claude/Projects/API_MT5
git push

# reset
cd C:\Projects\API_MT5
git pull
Stop-ScheduledTask -TaskName "MT5_Watchdog"
Stop-ScheduledTask -TaskName "MT5_Bot"
Start-Sleep -Seconds 3
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
Start-ScheduledTask -TaskName "MT5_Bot"
Start-Sleep -Seconds 5
Start-ScheduledTask -TaskName "MT5_Watchdog"

