# Active Filter Values Analysis Report

## Current Active Filter Values (Runtime)

Based on code analysis and startup logs, here are the CURRENT active filter values:

| Filter | Current Value | Source | Code Location | Notes |
|--------|---------------|--------|---------------|-------|
| **Discount Thresholds** |
| `MIN_LOW_DISCOUNT` | `0.0001` (0.01%) | PAPER_TRADING override | Line 354 | Hardcoded when `PAPER_TRADING=True` |
| `PAPER_MIN_DISCOUNT_PCT` | `0.0001` (0.01%) | Default | Line 384 | Used in paper trading filter check |
| Discount threshold (paper mode) | `-0.01` (-1%) | Hardcoded | Line 1576 | Applied in `process_trade()` for BUY/SELL trades |
| **Expiry/Velocity Filters** |
| `MAX_DAYS_TO_EXPIRY` | `5.0` days | MAX_DAYS_TO_EXPIRY_OVERRIDE | Line 288-291 | Override env var takes precedence |
| `PAPER_MAX_DTE_DAYS` | `5.0` days | PAPER_MAX_DTE_DAYS_OVERRIDE | Line 376-381 | Override env var takes precedence |
| `MIN_HOURS_TO_EXPIRY` | `0` hours | env var | Line 296 | Set via `MIN_HOURS_TO_EXPIRY=0` |
| `STRICT_SHORT_TERM` | `False` | PAPER_TRADING auto-disable | Line 318-326 | Auto-disabled when `PAPER_TRADING=True` |
| **Other Key Filters** |
| `MIN_WHALE_SCORE` | `0.6` (60%) | env var | Line 247 | Default: 0.70, but env shows 0.6 |
| `CLUSTER_MIN_USD` | `0.0` USD | CLUSTER_MIN_USD env | Line 1530 | Runtime check uses `CLUSTER_MIN_USD` or `MIN_CLUSTER_USD` |
| `CLUSTER_MIN_TRADES` | `1` | env var | Line 416 | Default: 1 |
| `CLUSTER_MIN_AVG_HOLD_MINUTES` | `0` minutes | env var | Line 418 | Default: 30, but env shows 0 |
| `MIN_ORDERBOOK_DEPTH_MULTIPLIER` | `3.0` | Hardcoded | Line 248 | Fixed value, not configurable |
| `PAPER_MIN_CONFIDENCE` | `50` | env var | Line 370 | Default: 60, but env shows 50 |
| `PAPER_MIN_TRADE_USD` | `50.0` USD | Default | Line 385 | Minimum trade value for paper trading |
| **Bypass Flags** |
| `BYPASS_CLUSTER_MIN` | `False` | Default | Line 365 | Bypass cluster minimum check |
| `BYPASS_LOW_DISCOUNT` | `False` | Default | Line 366 | Bypass discount check |
| `BYPASS_SCORE_ON_STATS_FAIL` | `False` | Default | Line 359 | Bypass score check on stats API failure |

## Paper Mode Specific Overrides

When `PAPER_TRADING=True` (currently active):

1. **Discount Override** (Line 353-356):
   ```python
   if PAPER_TRADING:
       MIN_LOW_DISCOUNT = 0.0001  # 0.01% for paper mode
       MIN_DISCOUNT_PCT = MIN_LOW_DISCOUNT
   ```

2. **Negative Discount Acceptance** (Line 1573-1576):
   ```python
   if PAPER_TRADING:
       # Accept if discount >= -0.01 (1% negative is acceptable)
       discount_check_passed = discount_pct >= -0.01
   ```

3. **STRICT_SHORT_TERM Auto-Disable** (Line 318-320):
   ```python
   if PAPER_TRADING and STRICT_SHORT_TERM_OVERRIDE == "":
       STRICT_SHORT_TERM = False
   ```

## Environment Variable Overrides (Active)

Current runtime environment:
- `PAPER_TRADING` = `"1"` → `True`
- `MAX_DAYS_TO_EXPIRY_OVERRIDE` = `"5"` → `MAX_DAYS_TO_EXPIRY` = `5.0`
- `PAPER_MAX_DTE_DAYS_OVERRIDE` = `"5"` → `PAPER_MAX_DTE_DAYS` = `5.0`
- `MIN_HOURS_TO_EXPIRY` = `"0"` → `MIN_HOURS_TO_EXPIRY` = `0.0`
- `CLUSTER_MIN_USD` = `"0"` → `CLUSTER_MIN_USD` = `0.0` (effectively bypasses cluster min)
- `CLUSTER_MIN_HOLD` = `"0"` → `CLUSTER_MIN_AVG_HOLD_MINUTES` = `0`
- `MIN_WHALE_SCORE` = `"0.6"` → `MIN_WHALE_SCORE` = `0.6`
- `PAPER_MIN_CONFIDENCE` = `"50"` → `PAPER_MIN_CONFIDENCE` = `50`

## Code Snippet for Startup Filter Logging

The following code has been added to `src/polymarket/engine.py` (lines 4207-4288):

```python
# Comprehensive filter values log
logger.info("ACTIVE_FILTER_VALUES",
          # Discount thresholds
          MIN_LOW_DISCOUNT=MIN_LOW_DISCOUNT,
          MIN_LOW_DISCOUNT_SOURCE="PAPER_TRADING override" if (PAPER_TRADING and MIN_LOW_DISCOUNT == 0.0001) else ("env" if "MIN_LOW_DISCOUNT" in os.environ else "default"),
          PAPER_MIN_DISCOUNT_PCT=PAPER_MIN_DISCOUNT_PCT,
          PAPER_MIN_DISCOUNT_PCT_SOURCE="env" if "PAPER_MIN_DISCOUNT_PCT" in os.environ else "default",
          discount_threshold_paper_mode=paper_discount_threshold,
          discount_threshold_paper_mode_source="hardcoded -0.01" if PAPER_TRADING else "MIN_LOW_DISCOUNT",
          # Expiry/Velocity filters
          MAX_DAYS_TO_EXPIRY=MAX_DAYS_TO_EXPIRY,
          MAX_DAYS_TO_EXPIRY_SOURCE="MAX_DAYS_TO_EXPIRY_OVERRIDE" if MAX_DAYS_TO_EXPIRY_OVERRIDE else ("env" if "MAX_DAYS_TO_EXPIRY" in os.environ else "default"),
          PAPER_MAX_DTE_DAYS=PAPER_MAX_DTE_DAYS,
          PAPER_MAX_DTE_DAYS_SOURCE="PAPER_MAX_DTE_DAYS_OVERRIDE" if PAPER_MAX_DTE_DAYS_OVERRIDE else ("env" if "PAPER_MAX_DTE_DAYS" in os.environ else "default"),
          MIN_HOURS_TO_EXPIRY=MIN_HOURS_TO_EXPIRY,
          MIN_HOURS_TO_EXPIRY_SOURCE="env" if "MIN_HOURS_TO_EXPIRY" in os.environ else "default",
          STRICT_SHORT_TERM=STRICT_SHORT_TERM,
          STRICT_SHORT_TERM_SOURCE="PAPER_TRADING auto-disable" if (PAPER_TRADING and STRICT_SHORT_TERM_OVERRIDE == "") else ("STRICT_SHORT_TERM_OVERRIDE" if STRICT_SHORT_TERM_OVERRIDE else ("env" if "STRICT_SHORT_TERM" in os.environ else "default")),
          # Other key filters
          MIN_WHALE_SCORE=MIN_WHALE_SCORE,
          MIN_WHALE_SCORE_SOURCE="env" if "MIN_WHALE_SCORE" in os.environ else "default",
          CLUSTER_MIN_USD=active_cluster_min_usd,
          CLUSTER_MIN_USD_SOURCE="CLUSTER_MIN_USD env" if "CLUSTER_MIN_USD" in os.environ else ("MIN_CLUSTER_USD env" if "MIN_CLUSTER_USD" in os.environ else "default"),
          CLUSTER_MIN_TRADES=CLUSTER_MIN_TRADES,
          CLUSTER_MIN_TRADES_SOURCE="env" if ("CLUSTER_MIN_TRADES" in os.environ or "MIN_CLUSTER_TRADES" in os.environ) else "default",
          CLUSTER_MIN_AVG_HOLD_MINUTES=CLUSTER_MIN_AVG_HOLD_MINUTES,
          CLUSTER_MIN_AVG_HOLD_MINUTES_SOURCE="env" if "CLUSTER_MIN_HOLD" in os.environ else "default",
          MIN_ORDERBOOK_DEPTH_MULTIPLIER=MIN_ORDERBOOK_DEPTH_MULTIPLIER,
          MIN_ORDERBOOK_DEPTH_MULTIPLIER_SOURCE="hardcoded",
          PAPER_MIN_CONFIDENCE=PAPER_MIN_CONFIDENCE,
          PAPER_MIN_CONFIDENCE_SOURCE="env" if "PAPER_MIN_CONFIDENCE" in os.environ else "default",
          PAPER_MIN_TRADE_USD=PAPER_MIN_TRADE_USD,
          PAPER_MIN_TRADE_USD_SOURCE="env" if "PAPER_MIN_TRADE_USD" in os.environ else "default",
          # Bypass flags
          BYPASS_CLUSTER_MIN=BYPASS_CLUSTER_MIN,
          BYPASS_LOW_DISCOUNT=BYPASS_LOW_DISCOUNT,
          BYPASS_SCORE_ON_STATS_FAIL=BYPASS_SCORE_ON_STATS_FAIL,
          # Mode flags
          PAPER_TRADING=PAPER_TRADING,
          PRODUCTION_MODE=PRODUCTION_MODE,
          WHITELIST_ONLY=WHITELIST_ONLY)

# Also prints formatted table to console
print(f"\n{'='*80}")
print(f"ACTIVE FILTER VALUES")
print(f"{'='*80}")
# ... (formatted table output)
```

This logs all active filter values at startup with their sources, making it easy to verify configuration.

## Telegram Notification Status

✅ **Telegram notifications are FIXED and working:**
- Both call sites use keyword arguments: `format_paper_trade_telegram(trade_dict=...)`
- Error handling wraps all Telegram sends in try/except
- No `paper_trade_telegram_failed` entries found in recent logs
- Function signature updated to accept optional parameters for backwards compatibility

## Files Modified

1. **`src/polymarket/engine.py`**:
   - Lines 4207-4288: Added comprehensive `ACTIVE_FILTER_VALUES` log with source tracking
   - Lines 4265-4288: Added formatted console table output
   - Lines 2930-2942: Telegram notification wrapped in try/except (already fixed)
   - Lines 3465-3473: Telegram notification wrapped in try/except (already fixed)

2. **`src/polymarket/paper_trading.py`**:
   - Lines 215-292: Updated `format_paper_trade_telegram()` signature (already fixed)
   - Lines 295-332: Added test suite (already added)

## Verification

- ✅ Code compiles successfully
- ✅ ACTIVE_FILTER_VALUES log appears in startup logs
- ✅ Formatted table prints to console
- ✅ Telegram notifications working (no failures in logs)
- ✅ All filter values logged with source attribution
