# Paper Trading System Diagnosis & Architecture Summary

## Executive Summary

**Status**: Engine running, detecting target whale trades, but **0 paper trades opened** despite multiple trade detections.

**Primary Issue**: Trades are being rejected at the **signal generation stage** due to **low discount threshold** (2% minimum), preventing them from reaching paper trading filters.

**Secondary Issue**: Old code still running with `generate_signal()` error (needs restart with latest code).

---

## System Architecture

### 1. Core Components

```
polymarket-whale-engine/
├── src/polymarket/
│   ├── engine.py              # Main trading engine (3,700+ lines)
│   ├── scraper.py             # API data fetching
│   ├── profiler.py            # Whale statistics/profiling
│   ├── score.py               # Whale scoring algorithm
│   ├── paper_trading.py       # Paper trade management
│   ├── storage.py             # SQLite database (SignalStore)
│   ├── telegram.py            # Telegram notifications
│   └── storage/
│       └── trade_database.py  # Paper trade database
├── scripts/
│   ├── realtime_whale_watcher.py  # Real-time monitoring (Phase 2)
│   └── phase2_brutal_filtering.py # Whale selection analysis
└── data/
    ├── phase2_analysis_results.json  # Top 3-5 whales selected
    └── simulations/           # Trade simulation results
```

### 2. Trading Flow (Paper Trading Mode)

```
1. API Polling (every 60s)
   └─> fetch_recent_trades() → 500 trades/min_size=$150

2. Target Whale Filter (Early Exit)
   └─> Check if wallet in hardcoded list:
       - 0x507e52ef684ca2dd91f90a9d26d149dd3288beae
       - 0x9a6e69c9b012030c668397d8346b4d55dd8335b4
       - 0xfc25f141ed27bb1787338d2c4e7f51e3a15e1f7f
   └─> Skip if not target whale (optimization)

3. Market Metadata Fetch
   └─> fetch_market_metadata_by_condition()
   └─> Expiry filter (if metadata available)

4. Signal Generation (process_trade())
   ├─> Whale scoring (get_user_stats → whale_score)
   ├─> Discount calculation (entry_price vs midpoint)
   ├─> Cluster minimum check ($100 USD)
   ├─> Discount threshold check (MIN_LOW_DISCOUNT = 2%) ⚠️ REJECTION POINT
   ├─> Orderbook depth check (3x multiplier)
   └─> STRICT_SHORT_TERM expiry check (disabled in paper mode)

5. Signal Storage
   └─> signal_store.insert_signal() → SQLite
   └─> log_signal_to_csv()

6. Paper Trading Filters (if signal created)
   ├─> Confidence check (should_paper_trade ≥60%)
   ├─> Expiry filter (≤5 days, unknown allowed)
   ├─> Discount filter (PAPER_MIN_DISCOUNT_PCT = 0.01%)
   ├─> Trade value filter (≥$50 USD)
   ├─> Stake calculation (stake_eur_from_confidence)
   └─> Duplicate check (no open trade on condition)

7. Paper Trade Creation
   └─> open_paper_trade() → signal_store.insert_paper_trade()
   └─> Telegram notification
```

---

## Current Configuration

### Environment Variables (from .env)

```bash
PAPER_TRADING=1                    # ✅ Enabled
MIN_LOW_DISCOUNT=0.02             # ⚠️ 2% minimum (HIGH threshold)
MIN_WHALE_SCORE=0.75              # 75% minimum whale score
STRICT_SHORT_TERM=1               # ⚠️ Set in .env, but auto-disabled in code
MAX_DAYS_TO_EXPIRY_OVERRIDE=5    # ✅ Allow 0-5 day markets
PAPER_MAX_DTE_DAYS_OVERRIDE=5     # ✅ Allow 0-5 day markets
MIN_HOURS_TO_EXPIRY=0             # ✅ Allow same-day markets
```

### Code-Level Configuration

```python
# Signal Generation Thresholds (process_trade)
MIN_LOW_DISCOUNT = 0.02           # 2% minimum discount (from env)
MIN_WHALE_SCORE = 0.75            # 75% whale score
CLUSTER_MIN_USD = 100.0           # $100 minimum trade size
MIN_ORDERBOOK_DEPTH_MULTIPLIER = 3.0

# Paper Trading Thresholds (after signal created)
PAPER_MIN_CONFIDENCE = 60         # 60% minimum confidence
PAPER_MIN_DISCOUNT_PCT = 0.0001  # 0.01% minimum (VERY LOW)
PAPER_MIN_TRADE_USD = 50.0        # $50 minimum trade value
PAPER_MAX_DTE_DAYS = 5.0          # 5 days maximum expiry

# STRICT_SHORT_TERM (auto-disabled in paper mode)
if PAPER_TRADING:
    STRICT_SHORT_TERM = False      # ✅ Allows unknown expiry
```

### Target Whales (Hardcoded in engine.py:2497-2501)

```python
target_whales = [
    "0x507e52ef684ca2dd91f90a9d26d149dd3288beae",  # Most active
    "0x9a6e69c9b012030c668397d8346b4d55dd8335b4",
    "0xfc25f141ed27bb1787338d2c4e7f51e3a15e1f7f"
]
```

---

## Log Analysis: Why No Paper Trades

### Recent Activity (from logs/engine_2025-12-21.log)

```
17:18:20 - target_whale_trade_detected: 0x507e52... ($1,692.90 trade)
17:18:29 - processing_complete: trades_processed=1
         ⚠️ No signal generated → No paper trade

17:22:26 - target_whale_trade_detected: 0x507e52... ($166.90 trade)
17:22:26 - ERROR: name 'generate_signal' is not defined
         ⚠️ Old code still running (needs restart)

17:26:27 - target_whale_trade_detected: 0x507e52... ($236.74 trade)
17:26:33 - processing_complete: trades_processed=1
         ⚠️ No signal generated → No paper trade

17:28:19 - target_whale_trade_detected: 0x507e52... ($4,891.17 trade)
17:28:19 - ERROR: name 'generate_signal' is not defined
         ⚠️ Old code still running
```

### Telegram Status (from user's screenshot)

```
Last cycle:
- Trades processed: 3
- Signals generated: 0          ⚠️ CRITICAL: No signals created
- Top reject: low_discount (2)  ⚠️ 2 trades rejected for low discount
```

### Rejection Analysis

**Stage 1: Signal Generation (process_trade)**
- **Discount Check** (Line 1439): `if discount_pct < min_discount: return None`
  - `min_discount = MIN_LOW_DISCOUNT / 100.0 = 0.02 / 100 = 0.0002` (0.02%)
  - **Problem**: Trades with discount < 0.02% are rejected BEFORE signal creation
  - **Impact**: No signal → No paper trade opportunity

**Stage 2: Paper Trading Filters** (Never reached if Stage 1 fails)
- `PAPER_MIN_DISCOUNT_PCT = 0.0001` (0.01%) - Much lower threshold
- But trades never reach this stage due to Stage 1 rejection

---

## Root Causes

### 1. **Discount Threshold Mismatch** (PRIMARY ISSUE)

**Signal Generation**: Requires **2% discount** (`MIN_LOW_DISCOUNT=0.02`)
**Paper Trading**: Only requires **0.01% discount** (`PAPER_MIN_DISCOUNT_PCT=0.0001`)

**Impact**: Trades that would pass paper trading filters are rejected at signal generation stage.

**Evidence**: Telegram shows "low_discount (2)" rejections, meaning trades are being filtered out before paper trading logic runs.

### 2. **Old Code Still Running** (SECONDARY ISSUE)

**Error**: `name 'generate_signal' is not defined`
**Location**: Line 2553 in old code (fixed in latest commit)
**Status**: Engine needs restart with latest code

**Fix Applied**: Removed `generate_signal()` call, signal creation now proceeds directly after `process_trade()`.

### 3. **Missing Detailed Logging**

**Issue**: No `paper_trade_skipped` logs found, suggesting trades aren't reaching paper trading filters.
**Reason**: Trades rejected at signal generation stage (low discount).

---

## System Structure Details

### Data Flow

```
Polymarket API
    ↓
fetch_recent_trades() [scraper.py]
    ↓ (500 trades, min $150)
Early Filter: Target Whale Check [engine.py:2495-2504]
    ↓ (3 hardcoded addresses)
fetch_market_metadata_by_condition() [scraper.py]
    ↓ (market expiry, category)
process_trade() [engine.py:1200+]
    ├─> get_user_stats() [profiler.py]
    ├─> whale_score() [score.py]
    ├─> Discount calculation
    ├─> ⚠️ MIN_LOW_DISCOUNT check (2%) → REJECTION POINT
    └─> Return signal dict or None
    ↓ (if signal created)
signal_store.insert_signal() [storage.py]
    ↓
Paper Trading Filters [engine.py:2574-2621]
    ├─> should_paper_trade(confidence ≥60%)
    ├─> Expiry check (≤5 days, unknown OK)
    ├─> Discount check (≥0.01%) ← Never reached
    ├─> Trade value check (≥$50)
    └─> Duplicate check
    ↓ (if all pass)
open_paper_trade() [paper_trading.py]
    ↓
signal_store.insert_paper_trade() [storage.py]
    ↓
Telegram notification [telegram.py]
```

### Database Schema

**Signals Table** (`SignalStore`):
- Stores all generated signals (even if not paper traded)
- Fields: wallet, market, condition_id, whale_score, discount_pct, etc.

**Paper Trades Table** (`TradeDatabase`):
- Stores opened paper trades
- Fields: trade_id, wallet, market, condition_id, stake_eur, confidence, status
- Status: 'open', 'pending', 'completed'

### Key Functions

**process_trade()** (`engine.py:1200+`):
- Main signal generation function
- Returns `signal` dict or `None` if rejected
- Rejection reasons: low discount, low score, insufficient depth, etc.

**should_paper_trade()** (`paper_trading.py`):
- Checks if confidence ≥ PAPER_MIN_CONFIDENCE (60%)
- Returns boolean

**open_paper_trade()** (`paper_trading.py`):
- Creates paper trade dict
- Calculates stake based on confidence
- Returns trade dict for database insertion

---

## Recommendations

### Immediate Fixes

1. **Lower Signal Generation Discount Threshold**
   ```python
   # Option A: Use paper trading threshold for signal generation in paper mode
   if PAPER_TRADING:
       MIN_LOW_DISCOUNT = 0.0001  # 0.01% instead of 2%
   
   # Option B: Bypass discount check in paper mode
   if PAPER_TRADING:
       BYPASS_LOW_DISCOUNT = True
   ```

2. **Restart Engine with Latest Code**
   - Current code has `generate_signal()` error fixed
   - Need clean restart to load latest changes

3. **Add Detailed Logging**
   ```python
   # In process_trade(), before discount rejection:
   logger.warning("signal_rejected_low_discount",
                 wallet=trade_wallet[:16],
                 discount_pct=discount_pct,
                 min_required=min_discount,
                 trade_value_usd=trade_usd)
   ```

### Long-term Improvements

1. **Separate Thresholds for Paper Trading**
   - Use `PAPER_MIN_DISCOUNT_PCT` for signal generation when `PAPER_TRADING=True`
   - Keep `MIN_LOW_DISCOUNT` for production mode only

2. **Configuration File**
   - Move hardcoded target whales to config file
   - Allow per-whale threshold overrides

3. **Enhanced Monitoring**
   - Track rejection reasons per whale
   - Alert when target whales trade but no signals generated

---

## Current Status Summary

| Component | Status | Notes |
|-----------|--------|-------|
| Engine Running | ✅ Yes | PID varies, needs restart |
| Target Whale Detection | ✅ Working | 3+ trades detected recently |
| Signal Generation | ❌ Failing | 0 signals (low discount rejection) |
| Paper Trading Filters | ⏸️ Not Reached | Trades rejected before this stage |
| Code Version | ⚠️ Mixed | Old code still running (generate_signal error) |
| STRICT_SHORT_TERM | ✅ Disabled | Auto-disabled in paper mode |
| Expiry Filter | ✅ Working | 0-5 days allowed |

---

## Next Steps

1. **Restart engine** with latest code (fixes `generate_signal` error)
2. **Lower discount threshold** for paper trading mode (2% → 0.01%)
3. **Monitor logs** for `paper_trade_skipped` messages (will appear if trades reach paper filters)
4. **Verify paper trades** start opening after threshold adjustment

---

## Code References

- **Main Engine**: `src/polymarket/engine.py`
- **Signal Generation**: `process_trade()` (line ~1200)
- **Discount Check**: Line 1439 (`if discount_pct < min_discount`)
- **Paper Trading Logic**: Line 2574-2646
- **Target Whales**: Line 2497-2501 (hardcoded)
- **Configuration**: Lines 290-360

---

*Generated: 2025-12-21*
*Log File: logs/engine_2025-12-21.log*
*Git Commit: 3e34d60 (Fix paper trading: disable STRICT_SHORT_TERM and fix generate_signal error)*
