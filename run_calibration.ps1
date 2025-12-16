# Calibration Mode Runner
# Temporarily lowers MIN_WHALE_SCORE to collect histogram data

param(
    [string]$Threshold = "0.02"
)

Write-Host "=== Starting Calibration Mode ===" -ForegroundColor Green
Write-Host ""
Write-Host "Threshold: MIN_WHALE_SCORE=$Threshold" -ForegroundColor Cyan
Write-Host ""
Write-Host "Expected Output:" -ForegroundColor Yellow
Write-Host "  • Histogram every 10 cycles (~5 minutes)" -ForegroundColor White
Write-Host "  • Score distribution buckets" -ForegroundColor White
Write-Host "  • Top 20 highest whale scores" -ForegroundColor White
Write-Host ""
Write-Host "Typical Thresholds:" -ForegroundColor Yellow
Write-Host "  0.0  → See all trades (very noisy)" -ForegroundColor Gray
Write-Host "  0.02 → Noisy but active" -ForegroundColor Gray
Write-Host "  0.03-0.04 → Realistic 'whale' alerts" -ForegroundColor Gray
Write-Host "  0.06+ → Rare, very strong wallets" -ForegroundColor Gray
Write-Host ""
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

# Set environment variable and run
$env:MIN_WHALE_SCORE = $Threshold
python .\src\polymarket\engine.py

