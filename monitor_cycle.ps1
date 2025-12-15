# Monitor engine cycles - watch for status lines appearing every ~30 seconds
# Usage: .\monitor_cycle.ps1

$today = Get-Date -Format "yyyy-MM-dd"
$statusFile = "logs\status_$today.log"
$logFile = "logs\engine_$today.log"

Write-Host "=== Monitoring Engine Cycles ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Watching for:" -ForegroundColor Yellow
Write-Host "  • Status lines appearing every ~30 seconds" -ForegroundColor White
Write-Host "  • PHASE1B_USING_ZERO_DISCOUNT events" -ForegroundColor White
Write-Host "  • CSV_WRITE_ATTEMPT / DONE events" -ForegroundColor White
Write-Host ""

$initialStatusCount = 0
if (Test-Path $statusFile) {
    $initialStatusCount = (Get-Content $statusFile | Measure-Object -Line).Lines
}

Write-Host "Initial status entries: $initialStatusCount" -ForegroundColor Cyan
Write-Host "Starting monitoring..." -ForegroundColor Green
Write-Host ""

$lastStatusCount = $initialStatusCount
$cycleCount = 0
$startTime = Get-Date

while ($true) {
    Start-Sleep -Seconds 5
    
    # Check status file
    if (Test-Path $statusFile) {
        $currentStatusCount = (Get-Content $statusFile | Measure-Object -Line).Lines
        
        if ($currentStatusCount -gt $lastStatusCount) {
            $cycleCount++
            $elapsed = ((Get-Date) - $startTime).TotalSeconds
            $newEntries = $currentStatusCount - $lastStatusCount
            
            Write-Host "✅ Cycle #$cycleCount detected!" -ForegroundColor Green
            Write-Host "   Time elapsed: $([math]::Round($elapsed, 1)) seconds" -ForegroundColor Cyan
            Write-Host "   New status entries: $newEntries" -ForegroundColor Cyan
            
            # Show latest status entry
            $lastEntry = Get-Content $statusFile -Tail 1
            if ($lastEntry -match "trades_considered=(\d+).*signals_generated=(\d+)") {
                $trades = $matches[1]
                $signals = $matches[2]
                Write-Host "   Trades: $trades | Signals: $signals" -ForegroundColor $(if ([int]$signals -gt 0) { "Green" } else { "Yellow" })
            }
            
            Write-Host ""
            $lastStatusCount = $currentStatusCount
        }
    }
    
    # Check for key events in log
    if (Test-Path $logFile) {
        $recentLogs = Get-Content $logFile -Tail 20 -ErrorAction SilentlyContinue
        
        if ($recentLogs -match "PHASE1B_USING_ZERO_DISCOUNT") {
            Write-Host "⚠️ PHASE1B bypass detected!" -ForegroundColor Yellow
        }
        
        if ($recentLogs -match "CSV_WRITE_ATTEMPT") {
            Write-Host "📝 CSV write attempt detected!" -ForegroundColor Cyan
        }
        
        if ($recentLogs -match "CSV_WRITE_DONE") {
            Write-Host "✅ CSV write done!" -ForegroundColor Green
            Write-Host ""
            Write-Host "=== Checking CSV for new row ===" -ForegroundColor Cyan
            $signalsFile = "logs\signals_$today.csv"
            if (Test-Path $signalsFile) {
                $lastRow = Get-Content $signalsFile -Tail 1
                Write-Host ""
                Write-Host "Latest CSV row:" -ForegroundColor Yellow
                Write-Host $lastRow -ForegroundColor White
            }
        }
    }
    
    # Show progress every 30 seconds
    $elapsed = ((Get-Date) - $startTime).TotalSeconds
    if ([math]::Floor($elapsed) % 30 -eq 0 -and $elapsed -gt 0) {
        Write-Host "⏳ Still monitoring... ($([math]::Floor($elapsed)) seconds, $cycleCount cycles)" -ForegroundColor Gray
    }
}

