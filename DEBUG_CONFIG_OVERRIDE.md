# DEBUG CONFIGURATION OVERRIDE GUIDE

## Problem
Bot isn't triggering trades because whale trades are in markets resolving in <1 day, but bot filters for 1-5 days (or 1-2 days by default).

## Solution
Temporary config override to test 0-5 day markets while keeping original filter as fallback.

---

## TEMPORARY CONFIG CHANGE (0-5 Days)

### Option 1: Environment Variables (Recommended)

**PowerShell:**
```powershell
# Set override values
$env:MAX_DAYS_TO_EXPIRY_OVERRIDE = "5"
$env:PAPER_MAX_DTE_DAYS_OVERRIDE = "5"
$env:MIN_HOURS_TO_EXPIRY = "0"  # Allow same-day markets

# Run bot
python src\polymarket\engine.py
```

**Linux/Mac:**
```bash
export MAX_DAYS_TO_EXPIRY_OVERRIDE=5
export PAPER_MAX_DTE_DAYS_OVERRIDE=5
export MIN_HOURS_TO_EXPIRY=0
python src/polymarket/engine.py
```

### Option 2: .env File

Add to `.env` file:
```env
# TEMPORARY DEBUG: Allow 0-5 day markets
MAX_DAYS_TO_EXPIRY_OVERRIDE=5
PAPER_MAX_DTE_DAYS_OVERRIDE=5
MIN_HOURS_TO_EXPIRY=0
```

---

## REVERT TO ORIGINAL (1-5 Days)

Simply remove or unset the override variables:

**PowerShell:**
```powershell
Remove-Item Env:MAX_DAYS_TO_EXPIRY_OVERRIDE
Remove-Item Env:PAPER_MAX_DTE_DAYS_OVERRIDE
$env:MIN_HOURS_TO_EXPIRY = "2"  # Back to original
```

**Linux/Mac:**
```bash
unset MAX_DAYS_TO_EXPIRY_OVERRIDE
unset PAPER_MAX_DTE_DAYS_OVERRIDE
export MIN_HOURS_TO_EXPIRY=2
```

---

## LOGGING

With the enhanced logging, you'll see detailed rejection reasons in `logs/engine_YYYY-MM-DD.log`:

### Example Log Entries:

**Signal Rejected - Days to Expiry Too Long:**
```
[WARNING] signal_rejected_expiry_too_long wallet=0x507e52ef684ca2... 
          days_to_expiry=0.5 max_days_to_expiry=2.0 reason=too_long_at_emit
```

**Paper Trade Rejected - Days to Expiry:**
```
[WARNING] paper_trade_rejected_days_to_expiry wallet=0x507e52ef684ca2...
          days_to_expiry=0.5 max_dte_days=2.0 reason=days_to_expiry_exceeds_paper_max
```

**Paper Trade Rejected - Multiple Reasons:**
```
[WARNING] paper_trade_rejected wallet=0x507e52ef684ca2... 
          reasons=days_to_expiry_too_long_0.5d, discount_too_low_0.000050
          days_to_expiry=0.5 discount_pct=0.00005 max_dte_days=2.0
```

---

## WHALE ADDRESSES TO MONITOR

The bot should detect trades from these addresses:
- `0x507e52ef684ca2dd91f90a9d26d149dd3288beae`
- `0x9a6e69c9b012030c668397d8346b4d55dd8335b4`
- `0xfc25f141ed27bb1787338d2c4e7f51e3a15e1f7f`

Check logs for entries like:
```
[DEBUG] whale_trade_detected wallet=0x507e52ef684ca2... market_slug=... trade_value=...
```

---

## VERIFICATION

After applying override, check logs for:
1. ✅ Override confirmation message on startup
2. ✅ Whale trades being detected
3. ✅ Detailed rejection reasons if still filtered
4. ✅ Paper trades being created if filters pass

---

## NOTES

- Override values take precedence over config defaults
- Original values preserved in code (just override env vars)
- Logs will show both original and override values
- Easy to revert by removing override env vars
