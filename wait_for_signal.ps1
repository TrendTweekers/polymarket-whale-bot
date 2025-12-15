# Wait for new signal row in CSV and display it
# Usage: .\wait_for_signal.ps1

$today = Get-Date -Format "yyyy-MM-dd"
$signalsFile = "logs\signals_$today.csv"

if (-not (Test-Path $signalsFile)) {
    Write-Host "⚠️ CSV file not found: $signalsFile" -ForegroundColor Yellow
    Write-Host "   Waiting for file to be created..." -ForegroundColor Yellow
    Write-Host ""
    
    # Wait for file to be created
    $timeout = 300  # 5 minutes max wait
    $elapsed = 0
    while (-not (Test-Path $signalsFile) -and $elapsed -lt $timeout) {
        Start-Sleep -Seconds 2
        $elapsed += 2
        Write-Host "  Waiting... ($elapsed seconds)" -ForegroundColor Gray
    }
    
    if (-not (Test-Path $signalsFile)) {
        Write-Host "❌ Timeout: File not created after $timeout seconds" -ForegroundColor Red
        exit
    }
}

# Get initial line count
$initialLines = (Get-Content $signalsFile -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
Write-Host "📊 Initial CSV state: $initialLines lines" -ForegroundColor Cyan
Write-Host "⏳ Waiting for new signal row..." -ForegroundColor Yellow
Write-Host ""

# Monitor for new rows
$maxWait = 300  # 5 minutes max wait
$startTime = Get-Date
$lastLineCount = $initialLines

while ($true) {
    Start-Sleep -Seconds 2
    
    if (Test-Path $signalsFile) {
        $currentLines = (Get-Content $signalsFile -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
        
        if ($currentLines -gt $lastLineCount) {
            Write-Host "✅ New row detected! ($currentLines lines total)" -ForegroundColor Green
            Write-Host ""
            Write-Host "=== Latest CSV Row ===" -ForegroundColor Cyan
            Write-Host ""
            
            $allLines = Get-Content $signalsFile
            $lastRow = $allLines[-1]
            Write-Host $lastRow -ForegroundColor White
            Write-Host ""
            
            # Also show formatted version if it's valid CSV
            try {
                $signals = Import-Csv $signalsFile
                if ($signals.Count -gt 0) {
                    Write-Host "=== Formatted View ===" -ForegroundColor Cyan
                    $signals[-1] | Format-List
                }
            } catch {
                # Not valid CSV yet, just show raw row
            }
            
            break
        }
    }
    
    $elapsed = ((Get-Date) - $startTime).TotalSeconds
    if ($elapsed -gt $maxWait) {
        Write-Host "❌ Timeout: No new row after $maxWait seconds" -ForegroundColor Red
        break
    }
    
    # Show progress every 10 seconds
    if ([math]::Floor($elapsed) % 10 -eq 0 -and $elapsed -gt 0) {
        Write-Host "  Still waiting... ($([math]::Floor($elapsed)) seconds)" -ForegroundColor Gray
    }
}

