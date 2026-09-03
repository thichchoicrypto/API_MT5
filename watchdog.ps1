# Watchdog: tu dong restart bot neu crash
# Setup: Task Scheduler -> run at startup -> "powershell -File C:\Projects\API_MT5\watchdog.ps1"

$BotDir   = "C:\Projects\API_MT5"
$PythonCmd = "python"
$BotArgs   = "main.py live"
$LogFile   = "$BotDir\logs\watchdog.log"
$CheckSec  = 30   # kiem tra moi 30 giay

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts | $msg" | Tee-Object -FilePath $LogFile -Append
}

Write-Log "Watchdog started"

while ($true) {
    # Kiem tra process bot con song khong
    $proc = Get-Process -Name "python" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*main.py live*" } |
            Select-Object -First 1

    if (-not $proc) {
        Write-Log "Bot not running — starting..."
        $p = Start-Process -FilePath $PythonCmd `
                           -ArgumentList $BotArgs `
                           -WorkingDirectory $BotDir `
                           -PassThru `
                           -WindowStyle Hidden
        Write-Log "Bot started (PID=$($p.Id))"
        Start-Sleep -Seconds 10  # cho bot khoi dong
    }

    Start-Sleep -Seconds $CheckSec
}
