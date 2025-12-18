# Stop All Polymarket Bot Services
# Stops bot, heartbeat monitors, and all related processes

Write-Host "`n" -NoNewline
Write-Host "="*80 -ForegroundColor Cyan
Write-Host "🛑 STOPPING ALL POLYMARKET SERVICES" -ForegroundColor Yellow
Write-Host "="*80 -ForegroundColor Cyan
Write-Host ""

$found = $false

# Find all Python processes related to polymarket bot
$processes = Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $proc = Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)"
        $cmd = $proc.CommandLine
        
        # Check if it's a bot-related process
        if ($cmd -like "*polymarket*" -or 
            $cmd -like "*heartbeat*" -or 
            $cmd -like "*engine.py*" -or 
            $cmd -like "*bot.py*" -or 
            $cmd -like "*main.py*" -or
            $cmd -like "*scripts*" -and ($cmd -like "*enhanced_heartbeat*" -or $cmd -like "*quick_heartbeat*" -or $cmd -like "*market_scanner*")) {
            
            $found = $true
            [PSCustomObject]@{
                PID = $_.Id
                StartTime = $_.StartTime
                CommandLine = $cmd
            }
        }
    } catch {
        # Skip processes we can't access
    }
}

if ($found) {
    Write-Host "Found running services:" -ForegroundColor Yellow
    Write-Host ""
    
    foreach ($proc in $processes) {
        $uptime = (Get-Date) - $proc.StartTime
        $uptimeStr = "{0}h {1}m" -f [int]$uptime.TotalHours, $uptime.Minutes
        
        Write-Host "  PID $($proc.PID) | Uptime: $uptimeStr" -ForegroundColor White
        Write-Host "    $($proc.CommandLine)" -ForegroundColor Gray
        Write-Host ""
    }
    
    Write-Host "Stopping all services..." -ForegroundColor Yellow
    Write-Host ""
    
    foreach ($proc in $processes) {
        try {
            Stop-Process -Id $proc.PID -Force -ErrorAction Stop
            Write-Host "  ✅ Stopped PID $($proc.PID)" -ForegroundColor Green
        } catch {
            Write-Host "  ❌ Failed to stop PID $($proc.PID): $_" -ForegroundColor Red
        }
    }
    
    Write-Host ""
    Write-Host "✅ All services stopped!" -ForegroundColor Green
} else {
    Write-Host "✅ No running services found." -ForegroundColor Green
}

Write-Host ""
Write-Host "="*80 -ForegroundColor Cyan
Write-Host ""
