# Active Filter Values Analysis

## Current Active Filter Values (from code analysis)

| Filter | Value | Source | Notes |
|--------|-------|--------|-------|
| **Discount Thresholds** |
| `MIN_LOW_DISCOUNT` | `0.0001` (0.01%) | PAPER_TRADING override | Hardcoded override when `PAPER_TRADING=True` (line 354) |
| `PAPER_MIN_DISCOUNT_PCT` | `0.0001` (0.01%) | env var or default | Default: 0.0001 (line 384) |
| Discount threshold (paper mode) | `-0.01` (-1%) | Hardcoded | Applied in `process_trade()` for BUY/SELL (line 1576) |
| **Expiry/Velocity Filters** |
| `MAX_DAYS_TO_EXPIRY` | `5.0` days | MAX_DAYS_TO_EXPIRY_OVERRIDE | Override env var takes precedence (line 288-291) |
| `PAPER_MAX_DTE_DAYS` | `5.0` days | PAPER_MAX_DTE_DAYS_OVERRIDE | Override env var takes precedence (line 376-381) |
| `MIN_HOURS_TO_EXPIRY` | `0` hours | env var | Set via `MIN_HOURS_TO_EXPIRY=0` env var |
| `STRICT_SHORT_TERM` | `False` | PAPER_TRADING auto-disable | Auto-disabled when `PAPER_TRADING=True` unless overridden (line 318-326) |
| **Other Key Filters** |
| `MIN_WHALE_SCORE` | `0.70` (70%) | env var or default | Default: 0.70 (line 247) |
| `CLUSTER_MIN_USD` | `100.0` USD | env var or default | Uses `CLUSTER_MIN_USD` or `MIN_CLUSTER_USD` (line 1530) |
| `CLUSTER_MIN_TRADES` | `1` | env var or default | Default: 1 (line 416) |
| `CLUSTER_MIN_AVG_HOLD_MINUTES` | `30` minutes | env var or default | Default: 30 (line 418) |
| `MIN_ORDERBOOK_DEPTH_MULTIPLIER` | `3.0` | Hardcoded | Fixed value (line 248) |
| `PAPER_MIN_CONFIDENCE` | `50` | env var or default | Default: 60, but logs show 50 (line 370) |
| `PAPER_MIN_TRADE_USD` | `50.0` USD | env var or default | Default: 50.0 (line 385) |
| **Bypass Flags** |
| `BYPASS_CLUSTER_MIN` | `False` | env var or default | Default: False (line 365) |
| `BYPASS_LOW_DISCOUNT` | `False` | env var or default | Default: False (line 366) |
| `BYPASS_SCORE_ON_STATS_FAIL` | `False` | env var or default | Default: False (line 359) |

## Paper Mode Specific Overrides

When `PAPER_TRADING=True`:
- `MIN_LOW_DISCOUNT` = `0.0001` (hardcoded override, line 354)
- `MIN_DISCOUNT_PCT` = `0.0001` (synced with MIN_LOW_DISCOUNT, line 355)
- Discount check threshold = `-0.01` (-1%) for both BUY and SELL (line 1576)
- `STRICT_SHORT_TERM` = `False` (auto-disabled unless explicitly overridden, line 318-320)

## Environment Variable Overrides (Active)

Based on current runtime:
- `MAX_DAYS_TO_EXPIRY_OVERRIDE` = `"5"` → `MAX_DAYS_TO_EXPIRY` = `5.0`
- `PAPER_MAX_DTE_DAYS_OVERRIDE` = `"5"` → `PAPER_MAX_DTE_DAYS` = `5.0`
- `MIN_HOURS_TO_EXPIRY` = `"0"` → `MIN_HOURS_TO_EXPIRY` = `0.0`
- `PAPER_TRADING` = `"1"` → `PAPER_TRADING` = `True`

## Code Locations

- **Discount thresholds**: Lines 346-356, 1573-1590
- **Expiry filters**: Lines 286-296, 376-385, 318-326
- **Cluster filters**: Lines 401, 416-418, 1528-1549
- **Paper trading filters**: Lines 369-385, 2819-2887
