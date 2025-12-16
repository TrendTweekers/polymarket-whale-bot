# Watch and maintain recent log file (last 50 lines)
# Usage: .\watch_recent_log.ps1
# Press Ctrl+C to stop

$today = Get-Date -Format "yyyy-MM-dd"
$logFile = "logs\engine_$today.log"
$recentLogFile = "logs\engine_recent.log"

Write-Host "=== Watching Recent Log (Last 50 Lines) ===" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

# Create recent log file if it doesn't exist
if (-not (Test-Path $recentLogFile)) {
    "" | Set-Content $recentLogFile -Encoding UTF8
}

$lastCheck = Get-Date

while ($true) {
    if (Test-Path $logFile) {
        $currentCheck = (Get-Item $logFile).LastWriteTime
        
        # Only update if log file has changed
        if ($currentCheck -gt $lastCheck) {
            $lines = Get-Content $logFile -ErrorAction SilentlyContinue
            $last50 = if ($lines.Count -gt 50) { $lines[-50..-1] } else { $lines }
            
            $last50 | Set-Content $recentLogFile -Encoding UTF8
            
            Write-Host "$(Get-Date -Format 'HH:mm:ss') - Updated recent log ($($last50.Count) lines)" -ForegroundColor Green
            $lastCheck = $currentCheck
        }
    }
    
    Start-Sleep -Seconds 2
}

