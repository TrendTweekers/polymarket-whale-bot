# Auto-Populate Outcomes Script

## Overview

The `scripts/auto_populate_outcomes.py` script automatically populates `KNOWN_OUTCOMES_BY_CONDITION` in `manual_resolve_trades.py` by searching the web for game results.

## Features

1. **Database Query**: Queries all open trades with market names and condition_ids
2. **Web Search**: Searches for game results using market names
3. **Result Parsing**: Parses scores and determines winners
4. **Outcome Determination**: Calculates `winning_outcome_index` based on market type:
   - **Spread**: 0 = cover, 1 = didn't cover
   - **Total**: 0 = Over, 1 = Under
   - **Moneyline**: 0 = team1 wins, 1 = team2 wins
5. **Batch Processing**: Handles rate limiting (2 second delay between searches)
6. **Error Handling**: Gracefully handles missing results

## Installation

```bash
pip install googlesearch-python requests beautifulsoup4
```

Or install from requirements.txt:
```bash
pip install -r requirements.txt
```

## Usage

### Dry Run (Preview)
```bash
python scripts/auto_populate_outcomes.py --limit 10 --dry-run
```

### Update Script (Python Format)
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

## Options

- `--limit N`: Maximum number of markets to process (default: 50)
- `--dry-run`: Preview changes without updating files
- `--format {python,json}`: Output format (default: python)

## How It Works

1. **Query Database**: Gets open trades grouped by market name
2. **Extract Market Info**: Determines market type (spread/total/moneyline) and teams
3. **Search Web**: Searches for "{Team1} vs {Team2} December 21 2025 score"
4. **Parse Results**: Extracts scores from search results
5. **Calculate Outcome**: Determines winning_outcome_index based on market type
6. **Update Script**: Adds outcomes to `KNOWN_OUTCOMES_BY_CONDITION` dict

## Market Type Detection

- **Spread**: Detects "spread:" pattern, extracts favorite and spread amount
- **Total**: Detects "O/U" or "total:" pattern, extracts total points
- **Moneyline**: Detects "vs" pattern for simple team vs team

## Example Output

```
[1/50] Bulls vs. Hawks...
  Condition ID: 0x986c255d16e062c4c9...
  Market Type: moneyline
  Searching: Bulls vs Hawks December 21 2025 score result
  Found result: 152-150
  Winner: Bulls
  ✅ Added: winning_outcome_index=0
```

## Limitations

- **Rate Limiting**: 2 second delay between searches (adjustable)
- **Search Quality**: Depends on web search results accuracy
- **Parsing**: May miss results if format is unusual
- **Market Types**: Works best for sports (NBA, NFL, etc.)

## Error Handling

- Skips markets where no result is found
- Handles parsing errors gracefully
- Continues processing even if some searches fail
- Reports summary of successes and failures

## Next Steps

After running the script:
1. Review added outcomes in `manual_resolve_trades.py`
2. Verify results look correct
3. Run `python scripts/manual_resolve_trades.py --all-known`
4. Check progress with `python scripts/check_resolved_count.py`

## Tips

- Start with `--limit 10 --dry-run` to test
- Focus on high-stake trades first
- Verify a few results manually before batch processing
- Run in batches (50 at a time) to avoid rate limits

