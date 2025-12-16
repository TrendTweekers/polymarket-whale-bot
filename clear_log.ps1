# Clear the engine log file
# Usage: .\clear_log.ps1

$today = Get-Date -Format "yyyy-MM-dd"
$logFile = "logs\engine_$today.log"

Write-Host "=== Clearing Engine Log ===" -ForegroundColor Cyan
Write-Host ""

if (Test-Path $logFile) {
    try {
        $size = (Get-Item $logFile).Length
        Write-Host "File: $logFile" -ForegroundColor Yellow
        Write-Host "Size: $([math]::Round($size / 1KB, 2)) KB" -ForegroundColor Yellow
        Write-Host ""
        
        Clear-Content $logFile -ErrorAction Stop
        Write-Host "✅ Log file cleared!" -ForegroundColor Green
        Write-Host "   Ready for fresh logging" -ForegroundColor Cyan
    } catch {
        Write-Host "⚠️ Error: File is locked (engine may be running)" -ForegroundColor Red
        Write-Host "   Stop the engine first, then run this script again" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Error: $_" -ForegroundColor Gray
    }
} else {
    Write-Host "✅ Log file doesn't exist yet" -ForegroundColor Green
    Write-Host "   Will be created when engine starts" -ForegroundColor Cyan
}

