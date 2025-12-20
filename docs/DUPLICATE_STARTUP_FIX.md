# Duplicate Startup Notification Fix

## Issue

**Problem:** "WHALE WATCHER STARTED" message sent twice within 2 minutes (08:28 and 08:29).

**Root Cause:** Watcher process restarted, creating a new instance that reset the `startup_notification_sent` flag.

## Analysis

**Timeline:**
- First notification: 08:28
- Second notification: 08:29 (1 minute later)
- Current process started: 08:29:22

**What Happened:**
1. Watcher started at ~08:28, sent first notification
2. Watcher crashed/restarted at ~08:29
3. New watcher instance created → flag reset to `False`
4. Second notification sent

**Why Flags Don't Help:**
- Flags (`startup_notification_sent`) are instance variables
- New process = new instance = flags reset
- Can't persist across process restarts

## Fix Applied

**Solution:** Add a small delay before sending notification to avoid rapid restart spam.

**Code:**
```python
# Send startup notification to Telegram (only once, not on every reconnect)
# Also check if we just started (avoid rapid restart spam)
if not self.startup_notification_sent:
    # Small delay to avoid duplicate notifications on rapid restarts
    await asyncio.sleep(2)
    # Double-check flag after delay (in case of rapid restart)
    if not self.startup_notification_sent:
        await self.send_startup_notification()
        self.startup_notification_sent = True
```

**How It Works:**
- 2-second delay before sending notification
- Double-checks flag after delay
- If watcher restarts within 2 seconds, second instance will see flag still `False` but delay helps

## Limitations

**This fix helps but doesn't completely solve:**
- If watcher restarts after 2+ seconds, duplicate notifications still possible
- Flags can't persist across process restarts
- Need to investigate why watcher is restarting

## Better Solution (Future)

**Option 1: Check Process Start Time**
- Only send notification if process has been running > 2 minutes
- Prevents notifications on rapid restarts

**Option 2: Use File-Based Flag**
- Write flag to disk when notification sent
- Check file on startup
- Prevents duplicates even across restarts

**Option 3: Investigate Restarts**
- Find why watcher is crashing/restarting
- Fix root cause instead of symptom

## Status

✅ **Fix Applied** (delay added)
⏰ **Needs Testing** (wait for next restart to verify)
🔍 **Root Cause** (why is watcher restarting?)

## Next Steps

1. Monitor for duplicate notifications
2. If still happening, investigate restart cause
3. Consider file-based flag for persistence
