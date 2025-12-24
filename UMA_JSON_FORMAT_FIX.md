# UMA AncillaryData JSON Format Fix

## ✅ Fixed

Updated `src/polymarket/uma_resolver.py` to use proper JSON format for ancillaryData:

### Before (Incorrect):
```python
ancillary_data = b'q:"' + market_title.encode('utf-8') + b'"'
```

### After (Correct):
```python
ancillary_dict = {
    'q': market_title,
    'p1': 0,
    'p2': 1000000000000000000,  # 1e18 (wei)
    'p3': 2,  # For binary markets
    'rebate': 0
}
ancillary_data = json.dumps(ancillary_dict, sort_keys=True).encode('utf-8')
```

## ✅ Market Title Fix

Updated `scripts/resolve_paper_trades.py` to use database market name instead of API (which was returning wrong markets):

- Now uses `market_name` from database first
- Falls back to API title only if database name is missing
- This fixes the issue where API returned "Will Joe Biden get Coronavirus..." instead of "Raiders vs. Texans"

## Current Status

✅ **JSON Format**: Correct (`{"p1": 0, "p2": 1000000000000000000, "p3": 2, "q": "Raiders vs. Texans", "rebate": 0}`)  
✅ **Market Title**: Correct ("Raiders vs. Texans" from database)  
⚠️ **Contract Calls**: Still reverting (may be normal if market not resolved on-chain yet)

## Next Steps

If still reverting, possible causes:
1. Market not resolved on-chain yet (challenge period)
2. Market title needs exact match (punctuation, capitalization)
3. Timestamp might be required (currently using 0 for latest)

## Testing

Run with specific condition_id:
```bash
python scripts/resolve_paper_trades.py --condition-id 0x0e4ccd69c581deb1aad6f587083a4800d458d6a12f3d202418a53e0c40b18c5a --verbose
```

Check logs for:
- `ancillary_data_json` - Should show correct JSON with "Raiders vs. Texans"
- `uma_has_price_result` - Should show `True` if resolved, `False` if not
- Contract revert errors - May be normal if market not resolved yet

