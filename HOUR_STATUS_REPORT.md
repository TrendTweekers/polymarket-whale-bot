# Hour Status Report - Paper Trading Engine

**Runtime**: 1 hour 13 minutes  
**Report Time**: 2025-12-21 19:59 UTC  
**Engine PID**: 11276

---

## ✅ Engine Health

- **Status**: Running normally
- **Uptime**: 1h 13m 1s
- **Process**: Single instance (no duplicates)
- **Last Activity**: Continuous polling every 60 seconds

---

## 📊 Trade Detection Status

### Target Whale Trades Detected: **22 trades**

**Latest 3 Trades:**
1. **18:46:32** - `0x507e52...` BUY $312.48 (dota2 market)
2. **18:48:33** - `0x507e52...` BUY $444.19 (cbb market)
3. **18:48:33** - `0x507e52...` BUY $452.64 (cbb market)

**Detection Rate**: ~22 trades/hour (good activity level)

---

## ❌ Signal Generation Status

### Signals Generated: **0**
### Paper Trades Opened: **0**

**Problem**: All 22 detected trades are being rejected before signal generation.

---

## 🔍 Rejection Analysis

### Total Rejections: **12** (6 unique trades, some logged twice)

#### 1. **Low Discount Rejections: 6**
   - **Issue**: Discounts worse than -1% threshold
   - **Examples**:
     - SELL trade: -1.16% (rejected - slightly over threshold)
     - SELL trade: -1.22% (rejected - slightly over threshold)
     - BUY trade: -17.81% (rejected - whale bought way above market)
   - **Status**: ✅ **Working as intended** - filtering out bad executions

#### 2. **Midpoint/Token ID Failures: 6**
   - **Issue**: Cannot fetch midpoint price or resolve token_id
   - **Possible Causes**:
     - Market metadata unavailable
     - CLOB API timeout/failure
     - Token ID resolution failing
   - **Status**: ⚠️ **Needs investigation** - may be blocking valid trades

#### 3. **Whale Score Failures: 0**
   - **Status**: ✅ No issues

#### 4. **Depth Failures: 0**
   - **Status**: ✅ No issues

---

## 💡 Key Findings

### What's Working:
1. ✅ **Trade Detection**: Successfully detecting target whale trades (22/hour)
2. ✅ **Engine Stability**: Running for 1+ hour without crashes
3. ✅ **Discount Filtering**: Correctly rejecting trades with bad execution (> -1% negative discount)
4. ✅ **No Whale Score Issues**: All trades passing whale score checks

### What's Blocking Signals:
1. ⚠️ **Midpoint/Token ID Resolution**: 6 trades failing to get market prices
   - May be API timeouts or missing market data
   - Need to check if these are transient failures or systematic issues

2. ✅ **Discount Threshold**: 6 trades rejected for discounts worse than -1%
   - This is **expected behavior** - filtering out bad executions
   - Some trades are legitimately bad (e.g., -17.8% discount = whale bought way above market)

---

## 📈 Success Rate Analysis

**Trades Detected**: 22  
**Trades Rejected**: 12 (6 discount + 6 midpoint/token_id)  
**Trades Passed Filters**: ~10 (not logged, but implied)  
**Signals Generated**: 0  

**Conclusion**: Even trades that pass discount/score checks are not generating signals. This suggests:
- Additional filters may be blocking (not logged at WARNING level)
- Or midpoint/token_id failures are happening AFTER discount check (unlikely based on code flow)

---

## 🎯 Recommendations

### Immediate Actions:
1. **Check Midpoint/Token ID Failures**:
   - Review logs for specific condition_ids that failed
   - Check if these markets are still active/resolvable
   - May need to add retry logic or fallback mechanisms

2. **Review Silent Rejections**:
   - Check DEBUG logs for trades that pass discount but fail elsewhere
   - May need to elevate more rejection logs to WARNING level

3. **Consider Discount Threshold**:
   - Current: -1% minimum
   - Some trades rejected at -1.16% and -1.22% (very close)
   - Could relax to -1.5% if needed, but current threshold seems reasonable

### Next Steps:
1. Wait for more trades to see if midpoint/token_id failures are consistent
2. Check if any trades pass ALL filters but still don't generate signals
3. Review paper trading filters (expiry, trade value, etc.) to ensure they're not too strict

---

## 📝 Configuration Summary

- **MIN_LOW_DISCOUNT**: 0.0001 (0.01%)
- **Paper Trading Discount Threshold**: -1% (accepts -1% to +infinity)
- **MIN_WHALE_SCORE**: 0.60 (60%)
- **PAPER_MAX_DTE_DAYS**: 5.0
- **STRICT_SHORT_TERM**: False

---

*Report Generated: 2025-12-21 19:59 UTC*
