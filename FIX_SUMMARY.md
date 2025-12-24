# Paper Trading Discount Threshold Fix - Complete

## Summary

Fixed the discount threshold mismatch that was preventing paper trades from being created.

## Changes Applied

### 1. Lower Discount Threshold in Paper Trading Mode (Line 330-335)

```python
# Paper trading mode: Lower discount threshold to match paper trading filters
# This allows signals to be generated for low-discount trades that would pass paper filters
if PAPER_TRADING:
    MIN_LOW_DISCOUNT = 0.0001  # 0.01% for paper mode, matching PAPER_MIN_DISCOUNT_PCT
    MIN_DISCOUNT_PCT = MIN_LOW_DISCOUNT
    print(f"[PAPER_TRADING] MIN_LOW_DISCOUNT lowered to 0.01% (0.0001) for signal generation")
```

### 2. Use Module Variable Instead of os.getenv() (Line 1435, 1862)

**Before**:
```python
min_discount_pct = float(os.getenv("MIN_LOW_DISCOUNT", "0.0"))
```

**After**:
```python
min_discount_pct = MIN_LOW_DISCOUNT  # Use module variable (overridden in paper trading mode)
```

**Why**: `os.getenv()` reads from environment variables, not module variables. Since we override `MIN_LOW_DISCOUNT` in code (not env), we need to use the module variable directly.

### 3. Fixed Indentation Error (Line 2582-2583)

Fixed incorrect indentation in paper trading logic block.

---

## Impact

### Before Fix
- **Signal Generation**: Required 2% discount (`MIN_LOW_DISCOUNT=0.02`)
- **Paper Trading Filters**: Required only 0.01% discount (`PAPER_MIN_DISCOUNT_PCT=0.0001`)
- **Result**: Trades rejected at signal generation stage, never reaching paper filters
- **Telegram**: "Signals generated: 0", "Top reject: low_discount (2)"

### After Fix
- **Signal Generation**: Requires 0.01% discount in paper mode (`MIN_LOW_DISCOUNT=0.0001`)
- **Paper Trading Filters**: Requires 0.01% discount (`PAPER_MIN_DISCOUNT_PCT=0.0001`)
- **Result**: Trades pass signal generation, reach paper filters, paper trades can open
- **Expected**: Signals generated > 0, paper trades opened

---

## Testing Instructions

1. **Restart Engine**:
   ```powershell
   $env:PAPER_TRADING = "1"
   $env:MIN_HOURS_TO_EXPIRY = "0"
   $env:PAPER_MAX_DTE_DAYS_OVERRIDE = "5"
   $env:MAX_DAYS_TO_EXPIRY_OVERRIDE = "5"
   python src\polymarket\engine.py
   ```

2. **Verify Startup Message**:
   Look for: `[PAPER_TRADING] MIN_LOW_DISCOUNT lowered to 0.01% (0.0001) for signal generation`

3. **Monitor Logs** (after 10-30 minutes):
   ```powershell
   Get-Content logs\engine_2025-12-21.log -Tail 50 | Select-String -Pattern "signal_generated|paper_trade_opened|target_whale"
   ```

4. **Expected Results**:
   - `target_whale_trade_detected` ✅ (already working)
   - `signal_generated` or signals in processing_complete ✅ (should appear now)
   - `paper_trade_opened` ✅ (should appear if other filters pass)
   - Telegram notifications for opened paper trades ✅

---

## Configuration Reference

### Current Settings (Paper Trading Mode)

| Setting | Value | Location |
|---------|-------|----------|
| `MIN_LOW_DISCOUNT` | 0.0001 (0.01%) | Code override (line 333) |
| `PAPER_MIN_DISCOUNT_PCT` | 0.0001 (0.01%) | Default (line 356) |
| `MIN_WHALE_SCORE` | 0.75 (75%) | Env/config |
| `PAPER_MIN_CONFIDENCE` | 60 (60%) | Default (line 342) |
| `PAPER_MAX_DTE_DAYS` | 5.0 | Override (line 351) |
| `STRICT_SHORT_TERM` | False | Auto-disabled (line 299) |

---

## Files Modified

- `src/polymarket/engine.py`:
  - Line 330-335: Paper trading discount override
  - Line 1435: Use module variable for discount check
  - Line 1862: Use module variable for discount check (cluster path)
  - Line 2582-2583: Fixed indentation

---

## Next Steps

1. ✅ **Fix Applied** - Code changes complete
2. ⏳ **Restart Required** - Engine needs restart to load changes
3. ⏳ **Monitor** - Watch logs for signal generation and paper trades
4. ⏳ **Verify** - Confirm paper trades are opening

---

*Fix completed: 2025-12-21*
*Status: Ready for testing*
