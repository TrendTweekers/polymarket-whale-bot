# ✅ HEARTBEAT FREQUENCY REDUCED

## **CHANGE APPLIED:**

**Before:**
- Heartbeat interval: **600 seconds (10 minutes)**
- Notifications every 10 minutes showing "Alive" status

**After:**
- Heartbeat interval: **1800 seconds (30 minutes)**
- Notifications every 30 minutes (3x less frequent)

---

## **HOW TO CUSTOMIZE:**

You can override this with an environment variable:

```powershell
# Set to 1 hour (3600 seconds)
$env:HEARTBEAT_INTERVAL_SECONDS = "3600"

# Set to 2 hours (7200 seconds)
$env:HEARTBEAT_INTERVAL_SECONDS = "7200"

# Or disable heartbeats entirely (set to 0 or very high number)
$env:HEARTBEAT_INTERVAL_SECONDS = "0"
```

---

## **WHAT YOU'LL SEE:**

- ✅ Heartbeat notifications every **30 minutes** instead of 10 minutes
- ✅ Still shows "Alive" status with trade/signal counts
- ✅ Less notification spam
- ✅ Still know the bot is running

---

**Restart the engine to apply the change!**
