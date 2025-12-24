# Manual Resolution Guide

## Overview

The `scripts/manual_resolve_trades.py` script allows you to force-resolve trades with known outcomes, bypassing UMA/API checks. This is useful when:
- Markets haven't resolved on-chain yet (challenge period)
- You have verified outcomes from external sources
- You want immediate PnL calculations

## Current Status

- **Resolved**: 2 trades (241, 243)
- **Open**: 298 trades
- **Total PnL**: $38.72

## How to Add Known Outcomes

### Method 1: By Condition ID (Recommended)

Edit `scripts/manual_resolve_trades.py` and add to `KNOWN_OUTCOMES_BY_CONDITION`:

```python
KNOWN_OUTCOMES_BY_CONDITION = {
    "0x802a414d66f82720b3": {  # First ~20 chars of condition_id
        "winning_outcome_index": 1,  # 0 = YES/First outcome, 1 = NO/Second outcome
        "note": "Description of outcome"
    },
    # Add more...
}
```

**To find condition_ids:**
```bash
python scripts/find_recent_trades.py  # Lists trades with event_ids
python scripts/check_trade_details.py  # Shows detailed trade info
```

### Method 2: By Trade ID (Legacy)

For specific trades, add to `KNOWN_OUTCOMES`:

```python
KNOWN_OUTCOMES = {
    241: {
        "resolved": True,
        "winning_outcome_index": 1,
        "won": False,  # Optional: override win/loss determination
        "resolved_price": 1.0,
        "note": "Description"
    },
}
```

## Determining Winning Outcome Index

- **Index 0**: YES / First outcome / Team A wins
- **Index 1**: NO / Second outcome / Team B wins

**Examples:**
- Spread market: "Will Team A cover -14.5?"
  - Index 0 = YES (Team A covers)
  - Index 1 = NO (Team A doesn't cover)
- Moneyline: "Will Team A win?"
  - Index 0 = YES (Team A wins)
  - Index 1 = NO (Team A loses)

## Running Manual Resolution

### List Known Outcomes
```bash
python scripts/manual_resolve_trades.py --list-known
```

### Resolve All Matching Trades
```bash
python scripts/manual_resolve_trades.py --all-known
```

### Dry Run (Preview)
```bash
python scripts/manual_resolve_trades.py --all-known --dry-run
```

### Resolve Specific Trade
```bash
python scripts/manual_resolve_trades.py --trade-id 241
```

## Finding Game Results

For sports markets, search for results:
- "Team A vs Team B December 21 2025 score"
- "Team A vs Team B December 22 2025 final score"
- Check official league websites, ESPN, etc.

## Example: Adding a New Outcome

1. **Find the trade:**
   ```bash
   python scripts/find_recent_trades.py
   ```

2. **Get condition_id:**
   - Look for `Event ID: 0x...` in output
   - Copy first ~20 characters

3. **Find the result:**
   - Search web for game result
   - Determine winning outcome index

4. **Add to script:**
   ```python
   "0x1234567890abcdef12": {
       "winning_outcome_index": 0,  # or 1
       "note": "Team A won 120-115"
   }
   ```

5. **Run resolution:**
   ```bash
   python scripts/manual_resolve_trades.py --all-known
   ```

6. **Verify:**
   ```bash
   python scripts/check_resolved_count.py
   python scripts/analyze_paper_trading.py
   ```

## Current Known Outcomes

### Condition ID Based
- `0x802a414d66f82720b3`: Texans spread -14.5 (didn't cover) → Index 1
- `0x0e4ccd69c581deb1aa`: Raiders vs Texans (Raiders won) → Index 0

### Trade ID Based (Legacy)
- Trade 241: Texans spread -14.5 → LOSS
- Trade 243: Raiders vs Texans → WIN

## Notes

- The script automatically determines win/loss based on your position
- PnL is calculated automatically
- Trades are marked as RESOLVED in database
- Can be run multiple times safely (skips already resolved trades)

