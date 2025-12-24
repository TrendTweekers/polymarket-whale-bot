# Backfill Market Questions Script Usage

## Overview

The `scripts/backfill_market_questions.py` script fetches and stores full market question texts for existing paper trades that don't have `market_question` stored.

## Why This Is Needed

- Existing trades were created before `market_question` storage was implemented
- Full question text is required for accurate UMA on-chain resolution
- Abbreviated names like "Raiders vs. Texans" cause UMA contract calls to revert

## Usage

### Dry Run (Preview Changes)
```bash
python scripts/backfill_market_questions.py --limit 10
```

### Actually Update Database
```bash
python scripts/backfill_market_questions.py --update --limit 10
```

### Process All Trades
```bash
python scripts/backfill_market_questions.py --update
```

## How It Works

1. **Queries Database**: Finds open trades without `market_question`
2. **Fetches from API**: Tries to get full question from Polymarket Gamma API
3. **Detects Wrong Markets**: Rejects API responses that return wrong markets (Biden/2020 issue)
4. **Fallback**: Uses database market name if API fails (better than NULL)
5. **Updates Database**: Stores question in `market_question` column

## Current Limitations

⚠️ **API Issue**: Polymarket API consistently returns wrong market data (Biden/2020 market for all condition_ids)

**Impact**:
- Most trades will get fallback question (database name)
- Fallback questions may be too abbreviated for UMA resolution
- Manual entry may be needed for critical markets

## Recommendations

### For Critical Markets
If you have specific markets that need accurate resolution:

1. **Manual Entry**: Update database directly:
   ```sql
   UPDATE paper_trades 
   SET market_question = 'Full exact question text here'
   WHERE id = <trade_id>;
   ```

2. **Web Search**: Find exact question text from Polymarket website or forums

3. **Wait for API Fix**: Once Polymarket fixes their API, re-run backfill script

### For New Trades
- New trades will automatically store full question text when created
- No backfill needed for trades created after the storage implementation

## Output Example

```
================================================================================
🔍 DRY RUN MODE - No database changes will be made
================================================================================

Found 5 open trade(s) without market_question
================================================================================

[1/5] Trade ID 1: Will General Mills (GIS) beat quarterly earnings?...
  Condition ID: 0xdd2db1de97992c0c91941560e0e101537167835f5b0ea67fd6697350b3e76c7a...
  ⚠️  API failed/wrong market - using database name as fallback: Will General Mills...
     Note: This may be too abbreviated for UMA resolution. Manual entry recommended.
  [DRY RUN] Would update trade 1 with fallback question

================================================================================
📊 Summary:
   Total processed: 5
   ✅ Updated: 0
   ❌ Failed: 0

💡 Run with --update to actually update the database
================================================================================
```

## Files Modified

- `scripts/backfill_market_questions.py`: Main backfill script
- Database: Updates `paper_trades.market_question` column

