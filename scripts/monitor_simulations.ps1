# Monitor Simulations - Quick Status Check
# Run this to check if new simulations are being created

Write-Host "`n=== SIMULATION MONITOR ===" -ForegroundColor Cyan
Write-Host ""

# Check watcher status
$watcherRunning = $false
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    $cmd = (Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine
    if ($cmd -like "*realtime_whale_watcher*") {
        $watcherRunning = $true
        $uptime = (Get-Date) - $_.StartTime
        Write-Host "✅ Watcher: RUNNING" -ForegroundColor Green
        Write-Host "   Uptime: $($uptime.Hours)h $($uptime.Minutes)m" -ForegroundColor Gray
    }
}

if (-not $watcherRunning) {
    Write-Host "❌ Watcher: NOT RUNNING" -ForegroundColor Red
    Write-Host "   Start it with: python scripts/realtime_whale_watcher.py" -ForegroundColor Yellow
}

Write-Host ""

# Check latest simulations
if (Test-Path "data/simulations") {
    $files = Get-ChildItem "data/simulations\*.json" | Sort-Object LastWriteTime -Descending
    
    if ($files.Count -eq 0) {
        Write-Host "⏰ No simulations yet" -ForegroundColor Yellow
        Write-Host "   Waiting for high-confidence whale trade..." -ForegroundColor Gray
    } else {
        Write-Host "📊 Latest Simulations:" -ForegroundColor Cyan
        
        $latest = $files | Select-Object -First 1
        $age = (Get-Date) - $latest.LastWriteTime
        
        Write-Host "   Latest: $($latest.Name)" -ForegroundColor White
        Write-Host "   Age: $($age.Hours)h $($age.Minutes)m ago" -ForegroundColor Gray
        
        # Check if it's new format
        $content = Get-Content $latest.FullName | ConvertFrom-Json
        $status = $content.status
        
        if ($status -eq "old_format" -or (-not $status)) {
            Write-Host "   ⚠️  Old format (before scheduled delays fix)" -ForegroundColor Yellow
            Write-Host "   Waiting for new simulation..." -ForegroundColor Gray
        } elseif ($status -eq "completed") {
            Write-Host "   ✅ Completed - All delay checks done!" -ForegroundColor Green
        } elseif ($status -eq "pending") {
            $results = $content.results.Count
            $scheduled = $content.delays_scheduled.Count
            $remaining = $scheduled - $results
            Write-Host "   ⏳ In Progress: $results/$scheduled delays checked" -ForegroundColor Yellow
            if ($remaining -gt 0) {
                Write-Host "   $remaining check(s) remaining..." -ForegroundColor Gray
            }
        }
        
        Write-Host ""
        Write-Host "   Run verification: python scripts/verify_simulation.py" -ForegroundColor Cyan
    }
} else {
    Write-Host "❌ Simulations directory not found" -ForegroundColor Red
}

Write-Host ""
