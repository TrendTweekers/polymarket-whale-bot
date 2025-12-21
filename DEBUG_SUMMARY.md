# DEBUG SUMMARY: Bot Not Triggering Trades

## Problem Analysis

Your bot isn't triggering trades because:

1. **Expiry Filter Too Restrictive**: 
   - Default: `MAX_DAYS_TO_EXPIRY = 2` (only markets expiring in 1-2 days)
   - Paper Trading: `PAPER_MAX_DTE_DAYS = 2.0` (same restriction)
   - Whale trades are in markets resolving in **<1 day** (LoL, NBA, NHL)
   - These get filtered out before signal generation

2. **Multiple Filter Layers**:
   - Signal generation filter (`MAX_DAYS_TO_EXPIRY`)
   - Paper trading filter (`PAPER_MAX_DTE_DAYS`)
   - Both need to pass for trade execution

---

## Code Changes Applied

### ✅ 1. Enhanced Rejection Logging

**Location**: `src/polymarket/engine.py`

**Changes**:
- Upgraded `logger.info()` to `logger.warning()` for visibility
- Added wallet address to all rejection logs
- Added filter type and config value to logs
- Enhanced paper trading rejection logging with detailed reasons

**Example Log Output**:
```
[WARNING] signal_rejected_expiry_too_long wallet=0x507e52ef684ca2... 
          days_to_expiry=0.5 max_days_to_expiry=2.0 reason=too_long_at_emit
          filter_type=MAX_DAYS_TO_EXPIRY config_value=2.0

[WARNING] paper_trade_rejected wallet=0x507e52ef684ca2... 
          reasons=days_to_expiry_too_long_0.5d, discount_too_low_0.000050
          days_to_expiry=0.5 max_dte_days=2.0 min_discount_pct=0.0001
```

### ✅ 2. Temporary Config Override

**Location**: `src/polymarket/engine.py` (lines ~266, ~321)

**Changes**:
- Added `MAX_DAYS_TO_EXPIRY_OVERRIDE` env var support
- Added `PAPER_MAX_DTE_DAYS_OVERRIDE` env var support
- Original values preserved (just override env vars to test)

**Usage**:
```powershell
# Test with 0-5 day markets
$env:MAX_DAYS_TO_EXPIRY_OVERRIDE = "5"
$env:PAPER_MAX_DTE_DAYS_OVERRIDE = "5"
$env:MIN_HOURS_TO_EXPIRY = "0"  # Allow same-day markets
python src\polymarket\engine.py
```

---

## Testing Instructions

### Step 1: Apply Override

```powershell
# Set override to allow 0-5 day markets
$env:MAX_DAYS_TO_EXPIRY_OVERRIDE = "5"
$env:PAPER_MAX_DTE_DAYS_OVERRIDE = "5"
$env:MIN_HOURS_TO_EXPIRY = "0"
$env:PAPER_TRADING = "1"
```

### Step 2: Run Bot

```powershell
python src\polymarket\engine.py
```

### Step 3: Monitor Logs

Check `logs/engine_YYYY-MM-DD.log` for:

1. **Override Confirmation**:
   ```
   [CONFIG_OVERRIDE] MAX_DAYS_TO_EXPIRY: 2 -> 5
   [CONFIG_OVERRIDE] PAPER_MAX_DTE_DAYS: 2.0 -> 5.0
   ```

2. **Whale Trade Detection**:
   ```
   [DEBUG] whale_trade_detected wallet=0x507e52ef684ca2... market_slug=...
   ```

3. **Rejection Reasons** (if still filtered):
   ```
   [WARNING] signal_rejected_expiry_too_long wallet=... days_to_expiry=...
   [WARNING] paper_trade_rejected wallet=... reasons=...
   ```

4. **Successful Trades**:
   ```
   [INFO] paper_trade_opened wallet=... market=... days_to_expiry=...
   ```

---

## Expected Behavior

### Before Override:
- ❌ Markets with <1 day expiry: **REJECTED**
- ✅ Markets with 1-2 day expiry: **ALLOWED**
- ❌ Markets with >2 day expiry: **REJECTED**

### After Override (0-5 days):
- ✅ Markets with <1 day expiry: **ALLOWED** (NEW!)
- ✅ Markets with 1-5 day expiry: **ALLOWED**
- ❌ Markets with >5 day expiry: **REJECTED**

---

## Revert to Original

Simply remove override env vars:

```powershell
Remove-Item Env:MAX_DAYS_TO_EXPIRY_OVERRIDE
Remove-Item Env:PAPER_MAX_DTE_DAYS_OVERRIDE
$env:MIN_HOURS_TO_EXPIRY = "2"  # Back to original
```

---

## Files Modified

1. ✅ `src/polymarket/engine.py` - Enhanced logging + override support
2. ✅ `DEBUG_CONFIG_OVERRIDE.md` - Usage guide
3. ✅ `DEBUG_REJECTION_LOGGING.patch` - Detailed patch notes

---

## Next Steps

1. **Apply override** and run bot
2. **Monitor logs** for detailed rejection reasons
3. **Verify** whale trades are being detected
4. **Check** if trades are now triggering
5. **Analyze** any remaining filter rejections

If trades still don't trigger after override, check logs for:
- Discount too low
- Trade value too low
- Confidence too low
- Other filter rejections

---

**All changes preserve original behavior - just override env vars to test!**
