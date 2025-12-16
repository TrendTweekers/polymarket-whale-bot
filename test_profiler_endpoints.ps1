# Test data-api endpoints (PowerShell 5.1 compatible)
# Uses Invoke-RestMethod (irm) instead of curl

$u = "0x56687bf447db6ffa42ffe2204a05edaa20f55839"

Write-Host "=== Testing Data-API Endpoints ===" -ForegroundColor Cyan
Write-Host ""

Write-Host "1. Trades Endpoint:" -ForegroundColor Yellow
irm "https://data-api.polymarket.com/trades?user=$u&limit=5&offset=0&takerOnly=true" | ConvertTo-Json -Depth 50

Write-Host ""
Write-Host "2. Activity Endpoint:" -ForegroundColor Yellow
irm "https://data-api.polymarket.com/activity?user=$u&limit=5&offset=0&sortBy=TIMESTAMP&sortDirection=DESC" | ConvertTo-Json -Depth 50

Write-Host ""
Write-Host "3. Value Endpoint:" -ForegroundColor Yellow
irm "https://data-api.polymarket.com/value?user=$u" | ConvertTo-Json -Depth 50

