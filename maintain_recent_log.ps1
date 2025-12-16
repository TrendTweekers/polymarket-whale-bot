# Maintain a rolling log file with only the last 50 lines
# Usage: .\maintain_recent_log.ps1

$today = Get-Date -Format "yyyy-MM-dd"
$logFile = "logs\engine_$today.log"
$recentLogFile = "logs\engine_recent.log"

Write-Host "=== Maintaining Recent Log ===" -ForegroundColor Cyan
Write-Host ""

if (Test-Path $logFile) {
    # Read the last 50 lines from the main log file
    $lines = Get-Content $logFile -ErrorAction SilentlyContinue
    $last50 = if ($lines.Count -gt 50) { $lines[-50..-1] } else { $lines }
    
    # Write to recent log file
    $last50 | Set-Content $recentLogFile -Encoding UTF8
    
    Write-Host "✅ Recent log updated" -ForegroundColor Green
    Write-Host "   Source: $logFile" -ForegroundColor Cyan
    Write-Host "   Output: $recentLogFile" -ForegroundColor Cyan
    Write-Host "   Lines: $($last50.Count)" -ForegroundColor Cyan
} else {
    Write-Host "⚠️ Main log file doesn't exist: $logFile" -ForegroundColor Yellow
    if (Test-Path $recentLogFile) {
        Write-Host "   Keeping existing recent log" -ForegroundColor Gray
    }
}

