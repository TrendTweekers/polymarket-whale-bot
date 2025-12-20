# 🔍 Watcher "Restarting" Explanation

## What's Actually Happening

**The watcher is NOT restarting** - it's been running continuously for 2+ hours.

**What you're seeing:** WebSocket reconnections triggering startup notifications.

## Why This Happens

### WebSocket Reconnections (Normal Behavior)
- WebSocket connections can drop due to:
  - Network hiccups
  - Server-side timeouts
  - Temporary connectivity issues
- The watcher **automatically reconnects** (this is good!)
- Each reconnection was sending a startup notification (this was the problem)

### The Issue
- **Line 279:** `await self.send_startup_notification()` was called **inside the reconnection loop**
- Every WebSocket reconnect = new startup notification
- Made it look like the watcher was restarting repeatedly

## Evidence It's NOT Restarting

✅ **Process Runtime:** 2 hours 46 minutes (continuous)
✅ **No Crashes:** Process ID hasn't changed
✅ **Data Collection:** Trades accumulating continuously
✅ **Normal Behavior:** WebSocket reconnections are expected

## Fix Applied

**Changed:** Only send startup notification **once** (on first connection)

**Before:**
```python
# Send startup notification to Telegram
await self.send_startup_notification()  # Called on EVERY reconnect ❌
```

**After:**
```python
# Send startup notification to Telegram (only once, not on every reconnect)
if not self.startup_notification_sent:
    await self.send_startup_notification()
    self.startup_notification_sent = True  # ✅ Only once
```

## Should You Be Worried?

**NO - This is normal behavior:**

1. ✅ **Watcher is stable** - running continuously
2. ✅ **Reconnections are normal** - WebSocket connections drop occasionally
3. ✅ **Auto-reconnect works** - system handles disconnections gracefully
4. ✅ **Data collection continues** - no data loss during reconnections

## What Changed

- **Before:** Startup notification sent on every WebSocket reconnect
- **After:** Startup notification sent only once (on first connection)
- **Result:** No more duplicate startup messages

## Next Steps

The fix is applied. After restarting the watcher, you'll only see:
- ✅ **One** startup notification (when watcher first starts)
- ✅ **Hourly summaries** (every hour)
- ✅ **No duplicate startup messages** on WebSocket reconnects

The watcher will continue to reconnect automatically when needed, but won't spam startup notifications.
