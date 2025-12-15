# Quick check of latest log entries
# Usage: .\check_logs.ps1 [number_of_lines]

param(
    [int]$Lines = 30
)

$today = Get-Date -Format "yyyy-MM-dd"
$logFile = "logs\engine_$today.log"

if (-not (Test-Path $logFile)) {
    Write-Host "⚠️ Log file not found: $logFile" -ForegroundColor Yellow
    exit
}

Write-Host "=== Last $Lines Lines from engine_$today.log ===" -ForegroundColor Cyan
Write-Host ""

Get-Content $logFile -Tail $Lines | ForEach-Object {
    # Color code by log level
    if ($_ -match "\[ERROR\]") {
        Write-Host $_ -ForegroundColor Red
    } elseif ($_ -match "\[WARNING\]|PHASE1B") {
        Write-Host $_ -ForegroundColor Yellow
    } elseif ($_ -match "signal_generated|CSV_WRITE") {
        Write-Host $_ -ForegroundColor Green
    } else {
        Write-Host $_ -ForegroundColor White
    }
}

