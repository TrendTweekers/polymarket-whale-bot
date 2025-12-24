# Full Question Text Storage Implementation

## Summary

Implemented storage and retrieval of full market question text to enable accurate UMA on-chain resolution.

## Changes Made

### 1. Database Schema Update (`src/polymarket/storage.py`)
- Added `market_question TEXT NULL` column to `paper_trades` table
- Added migration to add column to existing databases
- Updated `insert_paper_trade()` to store `market_question` field

### 2. Trade Creation (`src/polymarket/engine.py`)
- Updated `process_trade()` to extract full question from `market_obj`
- Tries multiple fields: `question`, `description`, `title`
- Stores in signal dict as `market_question` field

### 3. Paper Trade Creation (`src/polymarket/paper_trading.py`)
- Updated `open_paper_trade()` to include `market_question` in trade_dict
- Falls back to market name if question not available

### 4. Resolution Script (`scripts/resolve_paper_trades.py`)
- Updated to prefer stored `market_question` from database
- Falls back to API or database name if not stored

## How It Works

1. **When Trade is Created**:
   - `process_trade()` extracts full question from `market_obj` (fetched from API)
   - Stores in signal dict as `market_question`
   - `open_paper_trade()` includes it in trade_dict
   - `insert_paper_trade()` saves it to database

2. **When Resolving**:
   - Resolver checks `trade.get("market_question")` first
   - Falls back to API if not stored
   - Falls back to database name if API fails

## Benefits

- **Accurate UMA Resolution**: Full question text matches what was used when market was created
- **No API Dependency**: Stored question available even if API returns wrong data
- **Backward Compatible**: Existing trades without question still work (fallback to API/name)

## Next Steps

1. **For Existing Trades**: Run script to backfill question text from API (if available)
2. **For New Trades**: Question will be automatically stored when trades are created
3. **Testing**: Test UMA resolution with stored question text

## Files Modified

- `src/polymarket/storage.py`: Database schema and insert logic
- `src/polymarket/engine.py`: Extract question from market_obj
- `src/polymarket/paper_trading.py`: Include question in trade_dict
- `scripts/resolve_paper_trades.py`: Use stored question in resolver

