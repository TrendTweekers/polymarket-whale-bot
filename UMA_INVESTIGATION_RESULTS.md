# UMA AncillaryData Investigation Results

## Issue Identified

The Polymarket API is returning **wrong market data** for condition_id `0x0e4ccd69c581deb1aad6f587083a4800d458d6a12f3d202418a53e0c40b18c5a`:
- **Expected**: "Raiders vs. Texans" (from database)
- **API Returns**: "Will Joe Biden get Coronavirus before the election?" (2020 market)

This is a known API issue, not a resolver bug.

## Current Status

### ✅ Fixed
1. **JSON Format**: Correct format implemented:
   ```json
   {"p1": 0, "p2": 1000000000000000000, "p3": 2, "q": "...", "rebate": 0}
   ```

2. **Market Title Source**: Updated to prefer database name, fallback to API

3. **RPC Connection**: Alchemy Polygon RPC working (Chain ID: 137)

### ⚠️ Remaining Issues

1. **API Returns Wrong Markets**: Polymarket API consistently returns wrong market data
   - Database has correct name: "Raiders vs. Texans"
   - API returns: "Will Joe Biden get Coronavirus before the election?"
   - This prevents getting the full question text from API

2. **Contract Calls Reverting**: Likely because:
   - Market not resolved on-chain yet (challenge period)
   - OR wrong question text (due to API issue)
   - OR market title format doesn't match exactly

## Next Steps

### Option 1: Use Database Market Name
- Current approach: Use "Raiders vs. Texans" from database
- Problem: Too abbreviated - UMA needs full question text
- Solution: Need to find source of full question text

### Option 2: Query Different Endpoint
- Try Polymarket's data-api instead of gamma-api
- Or query by slug instead of condition_id
- Or use market_id if available

### Option 3: Test with Known Resolved Market
- Find a known resolved market (e.g., 2024 Election)
- Test resolver with that market to validate format
- If works, apply same format to current markets

## Recommendations

1. **For Now**: Resolver falls back to API method when UMA reverts
   - Bot continues functioning
   - Will detect resolutions once markets resolve on-chain

2. **Long-term**: Need reliable source for full question text
   - Could store full question in database when trade is created
   - Or query Polymarket website directly (scraping)
   - Or use Polymarket's GraphQL API if available

3. **Testing**: Test with known resolved market to validate format
   - Once format validated, can apply to all markets
   - Will help isolate if issue is format or timing

## Files Modified

- `src/polymarket/uma_resolver.py`: JSON format implementation
- `scripts/resolve_paper_trades.py`: Market title selection logic
- `scripts/fetch_full_market_title.py`: Diagnostic script
- `scripts/test_known_resolved_market.py`: Test script for resolved markets

