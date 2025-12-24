# WARNING Log Analysis - Trade Rejection Found

## Issue Identified

**Time**: 18:44:09  
**Trade**: BUY trade from `0x507e52...`  
**Value**: $754.17  
**Market**: `cbb-vand-wake-2025-12-21`

### Rejection Details:
```
trade_rejected_low_discount
- wallet: 0x507e52
- side: BUY
- calculated_discount: -0.007299270072992544 (-0.73%)
- min_required: 0.0001 (0.01%)
- trade_price: 0.69
- midpoint: 0.685
```

### Root Cause:
1. **BUY trade with negative discount**: Whale bought at 0.69, but midpoint is 0.685
2. **Discount calculation**: `(0.685 - 0.69) / 0.685 = -0.0073` (-0.73%)
3. **Previous fix only handled SELL trades**: The SELL trade discount fix didn't account for BUY trades also having negative discounts
4. **Check failed**: `-0.0073 < 0.0001` → rejected

### Why Negative Discounts Happen:
- **BUY trades**: Whale buys above market (pays more than midpoint) → negative discount
- **SELL trades**: Whale sells below market (sells into bid side) → negative discount
- **Common in paper trading**: Large trades often execute at slightly worse prices due to liquidity

## Fix Applied

### Updated Discount Check Logic:
```python
# For paper trading: accept small negative discounts for BOTH BUY and SELL
# Accept if discount >= -0.01 (1% negative is acceptable)
# This allows whales with slightly suboptimal execution while filtering out terrible trades
if PAPER_TRADING:
    discount_check_passed = discount_pct >= -0.01  # Accept -1% to +infinity
else:
    discount_check_passed = discount_pct >= min_discount  # Require positive discount
```

### Changes:
1. ✅ Extended negative discount acceptance to **BUY trades** (not just SELL)
2. ✅ Accept discounts >= -1% for both BUY and SELL in paper trading mode
3. ✅ Updated rejection log message to indicate "discount too negative"

## Expected Behavior After Fix

### Before Fix:
- BUY trade with -0.73% discount → ❌ **REJECTED**
- SELL trade with -0.5% discount → ✅ **ACCEPTED** (if >= -1%)

### After Fix:
- BUY trade with -0.73% discount → ✅ **ACCEPTED** (>= -1%)
- SELL trade with -0.5% discount → ✅ **ACCEPTED** (>= -1%)
- BUY trade with -1.5% discount → ❌ **REJECTED** (< -1%)
- SELL trade with -2% discount → ❌ **REJECTED** (< -1%)

## Next Steps

1. ✅ **Fix applied** - Engine restarted with updated discount logic
2. ⏳ **Monitor** - Wait for next target whale trade
3. 🔍 **Verify** - Check if signals are now being generated
4. 📊 **Report** - If still blocked, check for other WARNING logs (whale_score, depth, etc.)

---

*Last Updated: 2025-12-21 18:45 UTC*  
*Fix Applied: BUY/SELL negative discount acceptance in paper trading mode*
