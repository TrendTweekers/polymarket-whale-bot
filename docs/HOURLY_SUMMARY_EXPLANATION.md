# Hourly Summary Explanation

## Why Whale Count Stays the Same (2385 → 2385)

**This is CORRECT behavior.**

The whale count comes from `dynamic_whale_manager.get_whale_stats()` which reads from a **persisted JSON file** (`data/dynamic_whale_state.json`).

- **Whale list is cumulative** - it persists between restarts
- **Whale count only increases** when new whales are discovered
- If no new whales were discovered in that hour, the count stays the same
- This is expected and correct

**Example:**
- Hour 1: Discover 2,385 whales
- Hour 2: No new whales discovered → Still 2,385 whales ✅

---

## Why Trades Reset (63,972 → 0)

**This is a DESIGN ISSUE - per-hour counter, not cumulative.**

Looking at the code in `realtime_whale_watcher.py`:

```python
# Line 118: Show trades processed THIS HOUR
f"📈 <b>Trades:</b> {self.trades_processed} processed\n"

# Line 125: Send summary
await self.send_telegram(summary)

# Line 128: RESET counter for next hour
self.trades_processed = 0
```

**What happens:**
1. **21:26 Summary**: Shows 63,972 trades processed in that hour
2. **After summary**: Counter resets to 0
3. **22:26 Summary**: Shows 0 trades (because no trades processed in that hour)

**Possible reasons for 0 trades:**
- Markets went quiet (low activity period)
- WebSocket disconnected/reconnected
- Watcher stopped processing trades temporarily
- Filtering changed (trades below threshold)

**The counter is PER-HOUR, not cumulative.**

---

## Fix Options

### Option 1: Show Cumulative Total (Recommended)
Track total trades since watcher started, not per-hour.

### Option 2: Show Both
Show "This hour: X" and "Total: Y"

### Option 3: Keep Per-Hour (Current)
But add explanation in message that it's per-hour.

---

## Current Behavior Summary

| Metric | Type | Behavior |
|--------|------|----------|
| **Whale Count** | Cumulative | Persists, only increases |
| **Trades Processed** | Per-Hour | Resets after each summary |
| **Whale Trades** | Per-Hour | Resets after each summary |
| **Simulations** | Per-Hour | Resets after each summary |

---

## Recommendation

Change to show **cumulative totals** instead of per-hour counters, OR show both:
- "This hour: X trades"
- "Total since start: Y trades"

This would make the summaries more meaningful and less confusing.
