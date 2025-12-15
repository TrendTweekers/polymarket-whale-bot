# Watch engine log file in real-time
# Usage: .\watch_logs.ps1

$today = Get-Date -Format "yyyy-MM-dd"
$logFile = "logs\engine_$today.log"

if (-not (Test-Path $logFile)) {
    Write-Host "⚠️ Log file not found: $logFile" -ForegroundColor Yellow
    Write-Host "   Engine may not have started yet." -ForegroundColor Yellow
    exit
}

Write-Host "📝 Watching: $logFile" -ForegroundColor Cyan
Write-Host "   Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

Get-Content $logFile -Tail 50 -Wait

