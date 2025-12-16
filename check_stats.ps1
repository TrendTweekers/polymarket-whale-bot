# Check statistics since last engine restart
$logFile = "logs\engine_2025-12-15.log"
if (-not (Test-Path $logFile)) {
    Write-Host "Log file not found: $logFile" -ForegroundColor Red
    exit
}

$allLines = Get-Content $logFile
$startups = $allLines | Select-String "engine_starting"
if ($startups.Count -eq 0) {
    Write-Host "No engine startup found in log" -ForegroundColor Yellow
    exit
}

$lastStartup = $startups[-1]
$startupLineNum = [array]::IndexOf($allLines, $lastStartup.Line)

Write-Host "=== Statistics Since Last Restart ===" -ForegroundColor Green
Write-Host ""
Write-Host "Last Startup: $($lastStartup.Line)" -ForegroundColor Cyan
Write-Host ""

# Get all gate_breakdown entries after startup
$breakdowns = $allLines | Select-String "gate_breakdown" | Where-Object { $_.LineNumber -gt $startupLineNum }

if ($breakdowns.Count -eq 0) {
    Write-Host "No cycles completed since startup" -ForegroundColor Yellow
    exit
}

Write-Host "Cycles since startup: $($breakdowns.Count)" -ForegroundColor Yellow
Write-Host ""

# Parse statistics
$totalTrades = 0
$totalSignals = 0
$totalRejectedLowScore = 0
$totalRejectedLowDiscount = 0
$totalRejectedDiscountMissing = 0
$totalRejectedBelowClusterMin = 0

foreach ($breakdown in $breakdowns) {
    $line = $breakdown.Line
    
    if ($line -match "trades_considered.*?:\s*(\d+)") {
        $totalTrades += [int]$matches[1]
    }
    if ($line -match "signals_generated.*?:\s*(\d+)") {
        $totalSignals += [int]$matches[1]
    }
    if ($line -match "rejected_low_score.*?:\s*(\d+)") {
        $totalRejectedLowScore += [int]$matches[1]
    }
    if ($line -match "rejected_low_discount.*?:\s*(\d+)") {
        $totalRejectedLowDiscount += [int]$matches[1]
    }
    if ($line -match "rejected_discount_missing.*?:\s*(\d+)") {
        $totalRejectedDiscountMissing += [int]$matches[1]
    }
    if ($line -match "rejected_below_cluster_min.*?:\s*(\d+)") {
        $totalRejectedBelowClusterMin += [int]$matches[1]
    }
}

Write-Host "Aggregated Statistics:" -ForegroundColor Cyan
Write-Host "  Total Trades Considered: $totalTrades" -ForegroundColor Green
Write-Host "  Total Signals Generated: $totalSignals" -ForegroundColor $(if ($totalSignals -gt 0) { "Green" } else { "Yellow" })
Write-Host ""
Write-Host "Rejections:" -ForegroundColor Cyan
Write-Host "  Rejected Low Score: $totalRejectedLowScore" -ForegroundColor Red
Write-Host "  Rejected Low Discount: $totalRejectedLowDiscount" -ForegroundColor Red
Write-Host "  Rejected Discount Missing: $totalRejectedDiscountMissing" -ForegroundColor Red
Write-Host "  Rejected Below Cluster Min: $totalRejectedBelowClusterMin" -ForegroundColor Red
Write-Host ""
Write-Host "Latest Cycle:" -ForegroundColor Cyan
$latest = $breakdowns[-1].Line
Write-Host $latest -ForegroundColor Gray

