# Environment Variable Updates

## New Variables to Add to .env

Add these lines to your `.env` file:

```bash
# Include SELL trades (temporary for testing)
INCLUDE_SELL_TRADES=True

# Bypass flags for testing (temporary)
BYPASS_CLUSTER_MIN=True
BYPASS_LOW_DISCOUNT=True

# Minimum discount percentage (lower for testing)
MIN_LOW_DISCOUNT=0.0

# Minimum cluster USD threshold (lower for more clusters)
MIN_CLUSTER_USD=100.0

# Minimum cluster trades (default 1 for single trades)
MIN_CLUSTER_TRADES=1

# Lower whale score threshold for calibration
MIN_WHALE_SCORE=0.005
```

## Updated Variables

These variables are already in use but documented here for reference:

```bash
# Bypass score on stats fail
BYPASS_SCORE_ON_STATS_FAIL=True

# Production mode
PRODUCTION_MODE=False

# Minimum discount percentage (MIN_LOW_DISCOUNT takes precedence if set)
MIN_DISCOUNT_PCT=0.5

# Minimum whale score
MIN_WHALE_SCORE=0.1

# Exclude categories
EXCLUDE_CATEGORIES=sports

# Cluster configuration
CLUSTER_MIN_TRADES=1
MIN_CLUSTER_TRADES=1
CLUSTER_MIN_HOLD=30
```

## Testing Configuration

For testing/calibration mode, use:

```bash
INCLUDE_SELL_TRADES=True
BYPASS_CLUSTER_MIN=True
BYPASS_LOW_DISCOUNT=True
MIN_LOW_DISCOUNT=0.0
MIN_CLUSTER_USD=100.0
MIN_CLUSTER_TRADES=1
MIN_WHALE_SCORE=0.005
BYPASS_SCORE_ON_STATS_FAIL=True
PRODUCTION_MODE=False
```

## Changes Summary

1. **Token ID Resolution**: 
   - Now uses proper Gamma API endpoint with `condition_ids` parameter
   - Handles JSON array strings in `clobTokenIds` field
   - Matches trade outcome to market outcomes list with normalization
   - Better error handling and logging
   - Logs successful resolutions: `token_id_resolved`, `token_id_resolved_from_gamma`

2. **SELL Trades**: Can be included with `INCLUDE_SELL_TRADES=True`

3. **Discount Threshold**: 
   - Added `MIN_LOW_DISCOUNT` env var (default 0.0 for testing)
   - Takes precedence over `MIN_DISCOUNT_PCT` if set
   - Added `BYPASS_LOW_DISCOUNT` flag for testing
   - Better logging: `trade_rejected_low_discount` with calculated_discount, min_required, trade_price, midpoint

4. **Cluster Threshold**: 
   - Uses `MIN_CLUSTER_USD` (default lowered to 100.0)
   - Added `BYPASS_CLUSTER_MIN` flag for testing
   - Better rejection logging with sub-reasons

5. **Better Logging**: 
   - `ENV_SETTINGS` at startup shows all key environment variables
   - `discount_calc_debug` - shows discount calculation details
   - `trade_rejected_other` - granular logging with specific_reason and details
   - `cluster_rejected` - with detailed reasons (below_min_usd, below_min_trades)
   - `outcome_index_not_found` - with normalized and raw outcomes for debugging

6. **Token IDs**: Valid token_id should be plain bigints like `531350...` without quotes
