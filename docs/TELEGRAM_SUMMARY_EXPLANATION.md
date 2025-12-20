# 📊 Telegram Hourly Summary Explanation

## Why You See 0 Trades/Simulations

### The Counter Reset Behavior

**Important:** The hourly summary shows **per-hour counters**, not cumulative totals.

**How It Works:**
1. **At start of hour:** Counters capture current values
2. **Send summary:** Shows trades/simulations from that hour
3. **Reset counters:** Set to 0 for next hour
4. **Next hour:** Shows only what happened in that hour

**Example Timeline:**
```
09:00-10:00: Processed 13,275 trades
10:00 Summary: "Trades: 13,275 processed" ✅
10:00: Counters reset to 0

10:00-11:00: Watcher stopped/crashed
11:00 Summary: "Trades: 0 processed" ❌ (no trades this hour)
```

### Why You See 0

**Scenario 1: Watcher Stopped**
- Watcher crashed/stopped between summaries
- No trades processed in that hour
- Counter shows 0 (correct for that hour)

**Scenario 2: No High-Confidence Whale Trades**
- Trades are being processed
- But none meet ≥65% confidence threshold
- So `whale_trades_detected` = 0
- So `simulations_started` = 0

**Scenario 3: Counter Reset**
- Counters reset each hour
- If watcher restarted, counters start at 0
- Shows 0 until next trade

## What Actually Exists

**Simulations:** 17 files exist in `data/simulations/`
- These are REAL, persisted files
- Counter shows 0 because it reset
- Files are NOT deleted when counter resets

**Trades:** 41,562+ trades in `data/realtime_whale_trades.json`
- These are REAL, persisted trades
- Counter shows 0 because it reset
- Trades are NOT deleted when counter resets

## The Confusion

**Telegram shows:**
- "Trades: 0 processed" (this hour)
- "Simulations: 0" (this hour)

**But files show:**
- 17 simulation files exist
- 41,562+ trades exist

**Why?**
- Counters are **per-hour**, not cumulative
- Files are **persistent**, counters are **temporary**
- If watcher stopped, counter = 0 (correct for that hour)

## How to Verify

**Check actual data:**
```bash
# Count simulation files
Get-ChildItem data/simulations/*.json | Measure-Object | Select-Object Count

# Count trades
(Get-Content data/realtime_whale_trades.json | ConvertFrom-Json).Count
```

**Check watcher status:**
```bash
Get-Process python | Where-Object { $_.CommandLine -like "*realtime_whale_watcher*" }
```

## Solutions

### Option 1: Show Cumulative Totals (Better UX)
Modify hourly summary to show:
- "Trades this hour: X"
- "Total trades: Y" (from file)
- "Simulations this hour: X"
- "Total simulations: Y" (from files)

### Option 2: Keep Per-Hour (Current)
- Shows activity per hour
- Resets each hour
- Need to check files for totals

## Current Status

**Watcher:** Check if running (may have stopped)
**Data:** Exists in files (17 sims, 41k+ trades)
**Counters:** Reset each hour (by design)
**Issue:** Watcher may have stopped, causing 0 trades

## Next Steps

1. **Restart watcher** if not running
2. **Wait for next hour** to see if counters increment
3. **Check files** for actual data (not counters)
4. **Consider** showing cumulative totals in summary
