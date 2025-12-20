# ⚠️ Price Tracking Issue Identified

## Problem

**Current Behavior:**
- Simulation runs immediately when trade is detected (time T)
- Tries to look up prices at T+60s, T+180s, T+300s
- **But those prices don't exist yet!** They'll only be recorded as future trades come in

**Result:**
- All delays use detection price (fallback)
- Price tracking appears not to work

## Root Cause

The simulation design assumes prices are available immediately, but:
1. Trade detected at time T
2. Simulation starts immediately
3. Simulation tries to look up prices at T+60s, T+180s, T+300s
4. **Those prices haven't been recorded yet** (they'll come in over next 5 minutes)

## Current Status

**Files Analyzed:**
- `sim_20251220_001518_0x000d25.json` (created 00:15:39)
- All delays show same price: 0.997
- All timestamps show detection time: 2025-12-20 00:15:18

**Watcher Status:**
- ✅ Running (restarted ~2 minutes ago)
- ✅ Price recording implemented (`_record_market_price`)
- ✅ Price lookup implemented (`get_price_at_time`)
- ⚠️ But simulations run before prices are available

## Solution Options

### Option 1: Schedule Delay Checks (Recommended)
Schedule async tasks to check prices at actual execution times:
- At T+60s: Check price and update simulation
- At T+180s: Check price and update simulation  
- At T+300s: Check price and update simulation

**Pros:** Accurate, real-time
**Cons:** Requires simulation update mechanism

### Option 2: Delay Simulation Start
Wait 5+ minutes before running simulation:
- Trade detected at T
- Wait until T+300s
- Then run simulation with all prices available

**Pros:** Simple
**Cons:** Delayed analysis, misses immediate opportunities

### Option 3: Two-Phase Simulation
1. **Phase 1 (Immediate):** Create simulation with detection price
2. **Phase 2 (Delayed):** Update simulation with actual delay prices as they become available

**Pros:** Best of both worlds
**Cons:** More complex, requires update mechanism

## Next Steps

1. **Wait for new simulation** (created after watcher restart)
2. **Check if prices differ** (if market moved during delays)
3. **If still same prices:** Implement Option 1 or 3

## Debug Logging Added

Added debug logging to:
- `TradeSimulator._simulate_delay()`: Logs price lookup attempts
- `RealtimeWhaleWatcher.get_price_at_time()`: Logs lookup results

This will help identify:
- If lookup is being called
- If prices are found
- Why prices might not differ

## Expected Behavior After Fix

When a trade is detected:
1. Price recorded immediately
2. Simulation created with placeholder prices
3. At T+60s: Check actual price, update simulation
4. At T+180s: Check actual price, update simulation
5. At T+300s: Check actual price, update simulation

Result: Simulation shows actual prices at each delay time.
