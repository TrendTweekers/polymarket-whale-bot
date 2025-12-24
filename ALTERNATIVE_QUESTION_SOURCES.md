# Alternative Sources for Full Question Text

## Summary

Investigated multiple approaches to get full market question text for accurate UMA resolution.

## Approaches Investigated

### 1. ✅ Store Full Question at Trade Creation (IMPLEMENTED)
**Status**: ✅ Implemented
- Modified `process_trade()` to extract question from `market_obj`
- Stores in database `market_question` field
- Used by resolver when available

**Pros**:
- Most reliable - captured when trade is created
- No API dependency
- Works even if API returns wrong data later

**Cons**:
- Requires existing trades to be backfilled
- Depends on API providing question when trade is created

### 2. ❌ GraphQL API (FAILED)
**Status**: ❌ Endpoint not accessible
- Tried `clob-api.polymarket.com/graphql`
- DNS resolution failed
- Endpoint may not exist or require authentication

**Next Steps**: Could try:
- `api.polymarket.com/graphql`
- Check Polymarket docs for correct endpoint
- May require API key

### 3. ⚠️ Scrape Polymarket Website
**Status**: Not implemented (requires web scraping)
- Could scrape market pages for full question text
- More complex, requires HTML parsing
- May violate ToS

**Implementation**: Would need:
- `requests` + `BeautifulSoup` or `selenium`
- Market slug → URL mapping
- HTML parsing for question text

### 4. ⚠️ Web Search
**Status**: Not implemented (manual process)
- Search for quoted Polymarket questions
- Not scalable for automation
- Useful for one-off debugging

### 5. ✅ Enhanced API Query (PARTIAL)
**Status**: ⚠️ API returns wrong markets
- Current API consistently returns wrong market data
- Code detects and rejects wrong responses
- Falls back to database name

**Improvement**: Could try:
- Different API endpoints
- Query by slug instead of condition_id
- Use market_id if available

## Current Implementation

### Database Storage
- Added `market_question TEXT NULL` column
- Stores full question when trade is created
- Used by resolver when available

### Fallback Chain
1. **Stored `market_question`** (from database) ← Preferred
2. **API question** (if not wrong market)
3. **Database `market` name** (fallback)

### For Existing Trades
- Most existing trades don't have `market_question` stored
- Need to backfill from API (if available)
- Or wait for new trades to have it stored automatically

## Recommendations

### Short-term
1. ✅ **Current approach is sufficient**: Store question when creating trades
2. ✅ **Fallback works**: Uses database name if question not stored
3. ⚠️ **Backfill script**: Create script to fetch and store questions for existing trades

### Long-term
1. **Alternative API**: Investigate Polymarket's other API endpoints
2. **Web Scraping**: If API continues to fail, consider scraping
3. **Manual Entry**: For critical markets, manually add question text

## Files Created/Modified

- `src/polymarket/storage.py`: Added `market_question` column
- `src/polymarket/engine.py`: Extract question from market_obj
- `src/polymarket/paper_trading.py`: Include question in trade_dict
- `scripts/resolve_paper_trades.py`: Use stored question
- `scripts/fetch_question_graphql.py`: GraphQL test (failed)
- `scripts/fetch_full_market_title.py`: API diagnostic tool

## Next Steps

1. **Test with New Trades**: Verify question is stored when new trades are created
2. **Backfill Script**: Create script to fetch questions for existing trades
3. **Monitor**: Watch logs to see if stored questions improve UMA resolution

