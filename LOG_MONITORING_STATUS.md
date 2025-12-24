# Log Monitoring Status - Paper Trading

## Current Status (as of 18:18 UTC)

### ✅ **Step 1: target_whale_trade_detected** 
**Status**: ✅ **WORKING**
- **Count**: 1 trade detected since restart
- **Latest**: `0x507e52...` SELL trade ($774 value) at 18:18:27
- **Market**: `es2-gra-alb-2025-12-21-gra`
- **Conclusion**: Scraper is working correctly ✅

### ⏳ **Step 2: signal_generated**
**Status**: ❌ **NOT APPEARING**
- **Count**: 0 signals generated
- **Issue**: `process_trade()` is returning `None`
- **Possible Reasons**:
  1. Discount check failing (even with 0.01% threshold)
  2. Whale score unavailable or < 60%
  3. Orderbook depth insufficient
  4. Token ID resolution failing
  5. Midpoint price fetch failing
  6. Other filters blocking (cluster min, etc.)

### ⏳ **Step 3: paper_trade_opened**
**Status**: ❌ **NOT REACHED**
- **Count**: 0 paper trades opened
- **Reason**: No signals generated, so paper filters never run

---

## Configuration Summary

### Active Settings (from logs):
```
✅ PAPER_TRADING: Enabled
✅ MIN_LOW_DISCOUNT: 0.0001 (0.01%)
✅ MIN_WHALE_SCORE: 0.60 (60%)
✅ STRICT_SHORT_TERM: False (disabled)
✅ MIN_DISCOUNT_PCT: 0.0001
✅ INCLUDE_SELL_TRADES: True
✅ MAX_DAYS_TO_EXPIRY: 5.0
✅ PAPER_MAX_DTE_DAYS: 5.0
```

### Target Whales (Hardcoded):
```
1. 0x507e52ef684ca2dd91f90a9d26d149dd3288beae ✅ (detected)
2. 0x9a6e69c9b012030c668397d8346b4d55dd8335b4
3. 0xfc25f141ed27bb1787338d2c4e7f51e3a15e1f7f
```

---

## Why Signals Aren't Being Generated

### Possible Blockers (in order of likelihood):

1. **Whale Score Unavailable** (Line 1272-1276)
   - `get_whale_with_score()` returns `None` if stats can't be fetched
   - Logged as: `trade_rejected` with reason `whale_score_unavailable` (DEBUG level)
   - **Fix**: Check if API is returning stats for target whales

2. **Midpoint Price Fetch Failing** (Line 1319-1330)
   - If `current_price` is `None`, discount can't be calculated
   - Logged as: `trade_rejected` with reason `rejected_discount_missing` (DEBUG level)
   - **Fix**: Check CLOB/Gamma API availability

3. **Discount Check Failing** (Line 1446-1456)
   - Even with 0.01% threshold, discount might be negative or zero
   - For SELL trades: discount = `(entry - midpoint) / entry`
   - If whale sold at 0.49 and midpoint is 0.49 or lower → negative/zero discount
   - **Fix**: Check actual discount values in logs

4. **Orderbook Depth Insufficient** (Line 1459-1464)
   - Requires 3x multiplier
   - Logged as: `trade_rejected` with reason `insufficient_depth` (DEBUG level)

5. **Token ID Resolution Failing** (Line 1308-1316)
   - If token_id can't be resolved, trade is rejected
   - Logged as: `trade_rejected` with reason `token_id_resolve_failed` (DEBUG level)

---

## Enhanced Logging Added

### New Log Events:
1. **`signal_generated`** (INFO level) - When signal is successfully created
2. **`process_trade_returned_none`** (DEBUG level) - When process_trade returns None
3. **`trade_rejected_low_discount`** (WARNING level) - When discount check fails
4. **`signal_rejected_score_missing`** (WARNING level) - When whale_score is None
5. **`signal_rejected_discount_missing`** (WARNING level) - When discount_pct is None

---

## Next Steps to Diagnose

### Option 1: Enable DEBUG Logging Temporarily
```powershell
$env:LOG_LEVEL = "DEBUG"
# Restart engine
```

### Option 2: Check Specific Trade Processing
Wait for next target whale trade, then immediately check logs:
```powershell
Get-Content logs\engine_2025-12-21.log -Tail 200 | Select-String -Pattern "0x507e52|process_trade|whale_score|discount|token_id|midpoint"
```

### Option 3: Add More Detailed Logging
Add INFO-level logs at each rejection point in `process_trade()` to see exactly where trades are being rejected.

---

## Expected Flow (When Working)

```
1. target_whale_trade_detected ✅
   └─> Trade detected: 0x507e52... SELL $774

2. process_trade() called
   ├─> get_whale_with_score() → whale dict or None
   ├─> get_token_id() → token_id or None
   ├─> get_midpoint_price() → current_price or None
   ├─> calculate_discount() → discount_pct
   ├─> Check discount >= 0.0001
   ├─> Check orderbook depth >= 3x
   └─> Return signal dict or None

3. if signal:
   └─> signal_generated ✅ (should log here)
       ├─> Check whale_score not None
       ├─> Check discount_pct not None
       ├─> Check cluster minimum
       └─> Proceed to paper trading filters

4. Paper Trading Filters
   ├─> should_paper_trade(confidence >= 50%)
   ├─> Expiry check (≤5 days, unknown OK)
   ├─> Discount check (≥0.01%)
   ├─> Trade value check (≥$50)
   └─> Duplicate check

5. paper_trade_opened ✅ (final success)
```

---

## Current Bottleneck

**Most Likely**: `process_trade()` is returning `None` at one of these points:
- Whale score unavailable (API fetch failing)
- Midpoint price unavailable (CLOB/Gamma API issue)
- Discount calculation failing (negative discount for SELL)
- Token ID resolution failing

**Action**: Need DEBUG-level logs or add INFO-level logging at each rejection point to identify exact blocker.

---

*Last Updated: 2025-12-21 18:18 UTC*
*Engine PID: 20616*
*Status: Monitoring for next target whale trade*
