# 🔍 Simulation Verification Guide

## Quick Verification After First Simulation

### Step 1: Wait for Simulation
- Wait at least **6 minutes** after a high-confidence whale trade
- You should see Telegram notifications:
  - "🔬 Simulation Started" (immediate)
  - "✅ Delay Check Complete (+1min)" (after 60s)
  - "✅ Delay Check Complete (+3min)" (after 180s)
  - "✅ Delay Check Complete (+5min)" (after 300s)
  - "🎉 All delay checks complete!" (after 300s)

### Step 2: Run Verification Script

**Python (Recommended):**
```bash
python scripts/verify_simulation.py
```

**PowerShell (Alternative):**
```powershell
$latest = Get-ChildItem data/simulations/*.json | 
    Sort-Object LastWriteTime -Descending | 
    Select-Object -First 1

Write-Host "Latest simulation: $($latest.Name)"
Write-Host "Last modified: $($latest.LastWriteTime)"

$sim = Get-Content $latest.FullName | ConvertFrom-Json

Write-Host "`nSimulation Status: $($sim.status)"
Write-Host "Results count: $($sim.results.Count)"

Write-Host "`nDelay Results:"
foreach ($result in $sim.results) {
    Write-Host "  Delay: $($result.delay_seconds)s"
    Write-Host "  Price: $($result.market_state_at_entry.price)"
    Write-Host "  Entry: $($result.simulated_entry_price)"
    Write-Host "  Source: $($result.market_state_at_entry.source)"
    Write-Host ""
}

$prices = $sim.results | ForEach-Object { $_.market_state_at_entry.price }
$unique = $prices | Select-Object -Unique

Write-Host "Unique prices: $($unique.Count)"
if ($unique.Count -gt 1) {
    Write-Host "✅ SUCCESS - Prices differ! Scheduled delays working!"
} else {
    Write-Host "⚠️ All prices same - market may not have moved"
}
```

## Expected Output

### Success Case:
```
📄 File: sim_20251220_012345_0xabc123.json
   Last modified: 2025-12-20 01:28:45

📊 Status: completed
📈 Results count: 3

🔍 Delay Results:
  Delay: +1min (60s)
    Price: 0.998000
    Entry: 1.008000
    Source: actual_lookup
    Checked: 2025-12-20T01:24:45

  Delay: +3min (180s)
    Price: 0.999000
    Entry: 1.009000
    Source: actual_lookup
    Checked: 2025-12-20T01:26:45

  Delay: +5min (300s)
    Price: 1.001000
    Entry: 1.011000
    Source: actual_lookup
    Checked: 2025-12-20T01:28:45

✅ Price Analysis:
   Unique prices: 3
   Price range: 0.998000 to 1.001000
   Price change: 0.30%

🎉 SUCCESS - Prices differ! Scheduled delays working!

✅ Source Analysis:
   Actual lookups: 3/3
   ✅ All delays used actual prices!

🎉 Simulation Complete!
```

## What to Look For

### ✅ Success Indicators:
1. **Status = "completed"** - All delay checks finished
2. **Results count = 3** - All delays checked
3. **Unique prices > 1** - Prices differ (market moved)
4. **Source = "actual_lookup"** - Real prices used
5. **Checked timestamps** - Show actual execution times

### ⚠️ Normal Cases:
- **All prices same**: Market didn't move (normal for stable markets)
- **Status = "pending"**: Still waiting for delays (check back later)
- **Some fallback sources**: Price not found for that delay (rare)

### ❌ Issues to Watch For:
- **No results**: Simulation didn't start (check watcher logs)
- **All fallback sources**: Price tracking not working
- **Missing delays**: Some tasks didn't complete (check watcher)

## Troubleshooting

### No Simulation File:
- Check watcher is running
- Check for high-confidence whale trades (≥65%)
- Check watcher logs for errors

### Simulation Not Completing:
- Check watcher is still running
- Check for errors in watcher logs
- Verify Telegram notifications received

### All Prices Same:
- **Normal** if market is very stable
- Check if prices actually moved during delays
- Verify price tracking is recording trades

## Next Steps After Verification

### If Verified ✅:
- System is working correctly
- Let it run for remaining 37 hours
- Collecting real delay profitability data
- Ready for Phase 2 analysis at Hour 48

### If Issues Found ❌:
- Check watcher logs
- Verify price tracking is recording
- Check Telegram notifications
- Restart watcher if needed

## Timeline

```
Hour 0-11: ✅ Implementation Complete
Hour 11-48: ⏳ Data Collection (37h remaining)
Hour 48: ⭐ Phase 2 Analysis
Day 3-5: 📊 Paper Trading
Day 6-9: 💰 Live Trading
```

**Status: ON TRACK** ✅
