# Kill all running Python processes that match polymarket/engine.py
# Run this before starting a new engine to ensure no old processes are running

Write-Host "Checking for running polymarket engines..." -ForegroundColor Yellow

# Show any running python processes that mention polymarket or engine.py
$processes = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -match "python" -and $_.CommandLine -match "polymarket|engine\.py" } |
  Select-Object ProcessId, CommandLine

if ($processes) {
    Write-Host "Found running engines:" -ForegroundColor Red
    $processes | ForEach-Object {
        Write-Host "  PID $($_.ProcessId): $($_.CommandLine)" -ForegroundColor Red
    }
    
    Write-Host "`nKilling all matching processes..." -ForegroundColor Yellow
    Get-CimInstance Win32_Process |
      Where-Object { $_.Name -match "python" -and $_.CommandLine -match "polymarket|engine\.py" } |
      ForEach-Object { 
          Stop-Process -Id $_.ProcessId -Force
          Write-Host "  Killed PID $($_.ProcessId)" -ForegroundColor Green
      }
    Write-Host "`nAll engines stopped." -ForegroundColor Green
} else {
    Write-Host "No running engines found." -ForegroundColor Green
}
