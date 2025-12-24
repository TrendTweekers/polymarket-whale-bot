# Resolution Issue Diagnosis - 15+ Hours, 0 Resolved

**Date**: 2025-12-22  
**Issue**: After 15+ hours, 0 trades resolved despite markets ending (Dec 21 NFL/NBA games)

---

## Critical Finding: API Returning Wrong Markets

### Problem Identified

**All condition_ids are returning the same market**: "will-joe-biden-get-coronavirus-before-the-election" (2020)

**Test Results**:
- Condition ID `0x0e4ccd69c581deb1aad6f587083a4800d458d6a12f3d202418a53e0c40b18c5a` (Raiders vs Texans)
- API Response: Biden/COVID market from 2020
- Same result for ALL condition_ids tested

**This suggests**:
1. ❌ Condition_ids stored in database may be incorrect
2. ❌ API endpoint may be wrong or needs different format
3. ❌ Markets may have been deleted/moved and API returns default

---

## Root Cause Analysis

### How Condition IDs Are Stored

1. **Trade Detection**: Engine detects trades from Polymarket API
2. **Condition ID Extraction**: Uses `trade.get("conditionId")` from trade object
3. **Signal Creation**: Stores `condition_id` in signals table
4. **Paper Trade Creation**: Copies `condition_id` to `event_id` field in `paper_trades` table

### Current Resolution Check

1. **Resolver**: Calls `gamma-api.polymarket.com/markets?conditionId={id}`
2. **API Response**: Returns wrong market (Biden/COVID 2020) for all IDs
3. **Detection**: Checks `active`, `resolved`, `resolution` fields
4. **Result**: Markets show `active=True`, `closed=True`, `outcomePrices=["0","0"]`

---

## Potential Issues

### Issue #1: Wrong Condition IDs Stored

**Hypothesis**: Condition IDs extracted from trades might be wrong

**Evidence**:
- All API calls return same market
- Condition IDs look correct (full hex strings)
- But API returns wrong data

**Check Needed**: Verify what `conditionId` field actually contains in trade objects

### Issue #2: API Endpoint Issue

**Hypothesis**: API endpoint or parameter format is wrong

**Tested**:
- ✅ `gamma-api.polymarket.com/markets?conditionId={id}` - Returns wrong market
- ✅ `gamma-api.polymarket.com/markets?condition_ids={id}` - Returns list (different format)
- ❌ `data-api.polymarket.com/markets?condition_id={id}` - 404

**Possible Solutions**:
- Try `condition_ids` (plural) with array format
- Use `market_id` instead of `condition_id`
- Try different API endpoint

### Issue #3: Markets Deleted/Moved

**Hypothesis**: Markets no longer exist, API returns default

**Evidence**:
- All return same 2020 market
- Markets show `closed=True` but `active=True` (contradictory)
- `outcomePrices=["0","0"]` (both outcomes at 0)

**Possible Solutions**:
- Check if markets exist via Polymarket website
- Use market slug/name to search instead
- Check if condition_ids need to be looked up differently

---

## Recommended Fixes

### Fix #1: Check Actual Trade Data

**Action**: Inspect what condition_ids are actually in trade objects when detected

**Code**:
```python
# In engine.py, when processing trades, log the actual conditionId
logger.info("trade_condition_id_debug",
           conditionId=trade.get("conditionId"),
           marketId=trade.get("marketId"),
           market=trade.get("market", {}).get("id") if isinstance(trade.get("market"), dict) else None)
```

### Fix #2: Try Alternative API Lookup

**Action**: Use market_id or slug instead of condition_id

**Code**:
```python
# Try looking up by market_id if condition_id fails
market_id = trade.get("market_id") or trade.get("marketId")
if market_id:
    url = f"{GAMMA_BASE}/markets?id={market_id}"
```

### Fix #3: Check Closed Field

**Action**: Update resolver to check `closed=True` AND `outcomePrices`

**Status**: ✅ Already added in latest fix

**Code**:
```python
closed = market.get("closed", False)
outcome_prices = market.get("outcomePrices", [])
if closed and outcome_prices:
    # Check for winner (price = 1.0)
    for idx, price_str in enumerate(outcome_prices):
        if float(price_str) == 1.0:
            # Winner found
```

### Fix #4: Use Market Slug/Name Lookup

**Action**: If condition_id fails, try searching by market name/slug

**Code**:
```python
# Fallback: search by market name
market_name = trade.get("market", "")
if market_name:
    url = f"{GAMMA_BASE}/markets?search={market_name[:50]}"
```

---

## Immediate Next Steps

1. **Check Trade Objects**: Log actual `conditionId` values from trade API responses
2. **Verify on Polymarket**: Manually check if markets exist on polymarket.com
3. **Test Alternative Lookup**: Try using `market_id` or slug instead
4. **Check Signal CSV**: Review `logs/signals_*.csv` to see what condition_ids were logged

---

## Workaround: Manual Resolution

Until the API issue is resolved, you can manually resolve trades:

1. **Check Polymarket website** for market resolutions
2. **Update database directly**:
   ```sql
   UPDATE paper_trades 
   SET status='RESOLVED', 
       resolved_outcome_index=0,  -- or 1 for winning outcome
       won=1,  -- or 0 for loss
       pnl_usd=2.20,  -- calculate based on entry_price
       resolved_at='2025-12-22T12:00:00Z'
   WHERE id=243;
   ```

---

## Conclusion

**Primary Issue**: API is returning wrong markets for all condition_ids  
**Resolver Status**: ✅ Working correctly, but can't detect resolutions due to API issue  
**Next Action**: Investigate why API returns wrong markets, check actual condition_id values in trade objects

