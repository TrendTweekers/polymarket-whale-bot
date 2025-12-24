# Auto-Populate Outcomes Script - Ready to Use

## ✅ Script Created Successfully

The `scripts/auto_populate_outcomes.py` script is now ready to automatically populate outcomes by searching the web for game results.

## Features Implemented

✅ **Database Query**: Queries open trades with market names and condition_ids  
✅ **Market Type Detection**: Identifies spreads, totals, and moneylines  
✅ **Web Search**: Searches for game results using market names  
✅ **Result Parsing**: Parses scores from search results  
✅ **Outcome Calculation**: Determines winning_outcome_index (0 or 1)  
✅ **Batch Processing**: Handles rate limiting (2 second delays)  
✅ **Error Handling**: Gracefully handles missing results  
✅ **Output Options**: Updates Python script or exports JSON  

## Installation

Dependencies are already in `requirements.txt`. Install with:
```bash
pip install googlesearch-python beautifulsoup4
```

Or:
```bash
pip install -r requirements.txt
```

## Usage Examples

### Test Run (Dry Run)
```bash
python scripts/auto_populate_outcomes.py --limit 10 --dry-run
```

### Process 50 Markets
```bash
python scripts/auto_populate_outcomes.py --limit 50
```

### Export to JSON
```bash
python scripts/auto_populate_outcomes.py --limit 50 --format json
```

### Then Resolve Trades
```bash
python scripts/manual_resolve_trades.py --all-known
```

## How It Works

1. **Queries Database**: Gets open trades grouped by unique market names
2. **Extracts Market Info**: 
   - Detects market type (spread/total/moneyline)
   - Extracts teams and spread/total amounts
3. **Searches Web**: 
   - Builds query: "{Team1} vs {Team2} December 21 2025 score"
   - Uses Google search API
4. **Parses Results**: 
   - Extracts scores from search results
   - Determines winner
5. **Calculates Outcome**: 
   - Spread: 0 = cover, 1 = didn't cover
   - Total: 0 = Over, 1 = Under  
   - Moneyline: 0 = team1 wins, 1 = team2 wins
6. **Updates Script**: Adds to `KNOWN_OUTCOMES_BY_CONDITION` dict

## Market Type Examples

- **Spread**: "Texans vs Raiders spread: Texans -14.5" → Detects spread market
- **Total**: "Jazz vs Nuggets: O/U 248.5" → Detects total market
- **Moneyline**: "Bulls vs Hawks" → Detects moneyline market

## Rate Limiting

- 2 second delay between searches (adjustable in code)
- Processes markets in batches (default limit: 50)
- Handles errors gracefully, continues processing

## Output Format

### Python Format (Default)
Updates `scripts/manual_resolve_trades.py`:
```python
KNOWN_OUTCOMES_BY_CONDITION = {
    "0x1234567890abcdef12": {
        "winning_outcome_index": 0,
        "note": "Bulls won 152-150"
    },
}
```

### JSON Format
Exports to `known_outcomes.json`:
```json
{
  "0x1234567890abcdef12": {
    "winning_outcome_index": 0,
    "note": "Bulls won 152-150"
  }
}
```

## Testing Results

Script tested successfully:
- ✅ Database query working
- ✅ Market type detection working
- ✅ Web search integration working
- ✅ Error handling working
- ✅ Batch processing working

## Next Steps

1. **Run with sports markets** (NBA, NFL, etc.):
   ```bash
   python scripts/auto_populate_outcomes.py --limit 20
   ```

2. **Review added outcomes** in `manual_resolve_trades.py`

3. **Resolve trades**:
   ```bash
   python scripts/manual_resolve_trades.py --all-known
   ```

4. **Check progress**:
   ```bash
   python scripts/check_resolved_count.py
   ```

## Notes

- Works best with standard sports markets (NBA, NFL, etc.)
- May not find results for esports, college sports, or international leagues
- Search quality depends on web search results
- Some markets may need manual verification

## Summary

The auto-populate script is **fully functional** and ready to use. It will automatically:
1. Find open trades
2. Search for game results
3. Parse scores and determine outcomes
4. Add outcomes to the resolution script
5. Enable batch resolution of all matching trades

Run it with `--limit 50` to process 50 markets, then run `manual_resolve_trades.py --all-known` to resolve all matching trades!

