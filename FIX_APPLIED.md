# Paper Trading Discount Threshold Fix - Applied

## Changes Made

### 1. Lowered Discount Threshold for Paper Trading Mode

**File**: `src/polymarket/engine.py` (Lines 330-335)

**Change**:
```python
# Paper trading mode: Lower discount threshold to match paper trading filters
# This allows signals to be generated for low-discount trades that would pass paper filters
if PAPER_TRADING:
    MIN_LOW_DISCOUNT = 0.0001  # 0.01% for paper mode, matching PAPER_MIN_DISCOUNT_PCT
    MIN_DISCOUNT_PCT = MIN_LOW_DISCOUNT
    print(f"[PAPER_TRADING] MIN_LOW_DISCOUNT lowered to 0.01% (0.0001) for signal generation")
```

**Impact**:
- **Before**: Signal generation required 2% discount (`MIN_LOW_DISCOUNT=0.02`)
- **After**: In paper trading mode, signal generation requires only 0.01% discount (`MIN_LOW_DISCOUNT=0.0001`)
- This matches the `PAPER_MIN_DISCOUNT_PCT` threshold, allowing trades to pass signal generation and reach paper trading filters

### 2. Fixed Indentation Error

**File**: `src/polymarket/engine.py` (Line 2582-2583)

**Change**: Fixed incorrect indentation in paper trading logic block.

---

## How It Works

### Signal Generation Flow (Updated)

1. **Configuration Load** (Line 330-335):
   - If `PAPER_TRADING=True`, override `MIN_LOW_DISCOUNT` to `0.0001` (0.01%)
   - This happens at module load time, before any trades are processed

2. **Discount Check** (Line 1428-1449):
   - `min_discount_pct = float(os.getenv("MIN_LOW_DISCOUNT", "0.0"))`
   - Since `MIN_LOW_DISCOUNT` is set in code (not env), it reads from the module variable
   - Converts to fraction: `min_discount = min_discount_pct / 100.0`
   - For paper mode: `min_discount = 0.0001 / 100.0 = 0.000001` (0.0001%)
   - **Wait, this seems wrong...**

### Correction Needed

Looking at line 1428-1429:
```python
min_discount_pct = float(os.getenv("MIN_LOW_DISCOUNT", "0.0"))
min_discount = min_discount_pct / 100.0  # Convert percentage to fraction
```

**Issue**: The code reads from `os.getenv()` which won't see the module variable. We need to use the module variable directly.

**Fix Required**: Change line 1428 to use the module variable instead of `os.getenv()`.

---

## Next Steps

1. **Update discount check to use module variable** (Line 1428)
2. **Restart engine** with `PAPER_TRADING=1`
3. **Monitor logs** for:
   - `[PAPER_TRADING] MIN_LOW_DISCOUNT lowered to 0.01%` message on startup
   - `signal_generated` events (should increase)
   - `paper_trade_opened` events (should start appearing)

---

## Expected Behavior After Fix

- **Signal Generation**: Trades with discount ≥ 0.01% will generate signals
- **Paper Trading Filters**: Signals will reach paper trading filters
- **Paper Trades**: Trades passing all filters will open paper trades
- **Telegram**: Notifications will be sent for opened paper trades

---

*Fix applied: 2025-12-21*
*Status: Partial - needs discount check update to use module variable*
