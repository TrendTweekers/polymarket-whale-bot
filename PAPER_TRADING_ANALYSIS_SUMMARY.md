# Paper Trading Analysis Summary
**Date:** December 22, 2025  
**Analysis Period:** 11.2 hours (Dec 21 22:23 - Dec 22 09:35)  
**Report Generated:** `scripts/analyze_paper_trading.py`

## Executive Summary

✅ **System Status:** OPERATIONAL  
✅ **Paper Trading:** ACTIVE (279 trades opened)  
⏳ **EV Assessment:** PENDING (no resolved trades yet)

---

## Key Metrics

### Signal Generation
- **Total signals generated:** 62
- **Paper trades opened:** 35 (from logs) / 279 (from database)
- **Unique whales detected:** 2
- **Unique markets:** 38
- **Average discount:** 5.62%
- **Min/Max discount:** -0.98% / 24.19%
- **Average trade value:** $762.25
- **Total trade value tracked:** $47,259.38

### Paper Trades Database
- **Total trades:** 279
- **Open trades:** 279 (100%)
- **Resolved trades:** 0 (0%)
- **Total stake invested:** $794.53
- **Average confidence:** 89.7
- **Trades per hour:** 24.9

### Signal → Trade Conversion
- **Conversion rate:** 450% (279 trades / 62 signals)
  - *Note: This high rate suggests multiple trades per signal or historical data accumulation*

---

## Top Rejection Reasons

| Reason | Count |
|--------|-------|
| deduped | 82 |
| low_discount_paper | 60 |
| low_discount | 60 |
| open_trade_exists | 48 |
| discount_too_low_-0.01% | 6 |
| discount_too_low_-0.00% | 4 |
| discount_too_low_0.00% | 4 |

**Analysis:**
- **Deduplication working:** 82 duplicate signals prevented (expected behavior)
- **Low discount rejections:** 60+ trades rejected due to discount thresholds
  - Current threshold: `PAPER_MIN_DISCOUNT_PCT = 0.01%` (0.0001)
  - Paper mode accepts discounts >= -1% (-0.01)
  - Many rejections likely from negative discounts (whales buying above market)
- **Duplicate prevention:** 48 trades skipped (already have open position in same market)

---

## Per-Whale Performance (Top 10)

| Whale Address | Trades | Wins | Losses | Win% | PnL | ROI% |
|---------------|--------|------|--------|------|-----|------|
| 0x507e52ef684ca2dd91f90a9d26d149dd3288beae | 32 | 0 | 0 | 0.0% | $0.00 | 0.00% |
| 0xfc25f141ed27bb1787338d2c4e7f51e3a15e1f7f | 15 | 0 | 0 | 0.0% | $0.00 | 0.00% |
| 0x6f2628a8ac6e3f7bd857657d5316c33822ced136 | 12 | 0 | 0 | 0.0% | $0.00 | 0.00% |
| *(7 more whales with 10 trades each)* | | | | | | |

**Note:** All trades are still OPEN, so no win/loss data available yet.

---

## Analysis & Recommendations

### ✅ What's Working
1. **Signal Generation:** 62 signals in 11.2 hours (~5.5 signals/hour)
2. **High Confidence:** Average 89.7% confidence on opened trades
3. **Good Discounts:** Average 5.62% discount (well above threshold)
4. **Deduplication:** Preventing spam (82 duplicates blocked)
5. **Risk Management:** Preventing over-exposure (48 duplicate trades blocked)

### ⚠️ Areas of Concern
1. **No Resolved Trades:** All 279 trades still OPEN
   - Markets may not have resolved yet (many are same-day/next-day)
   - Resolver runs every 5 minutes
   - **Action:** Wait for markets to resolve to calculate EV

2. **High Discount Rejections:** 60+ trades rejected
   - Many may be from negative discounts (whales buying above market)
   - Current threshold is appropriate for testing
   - **Action:** Monitor if this becomes a bottleneck

3. **Conversion Rate Anomaly:** 450% (279 trades / 62 signals)
   - Suggests multiple trades per signal or historical accumulation
   - **Action:** Investigate if this is expected behavior

### 📊 EV Assessment (Pending)
**Cannot calculate EV until trades resolve:**
- Win rate: N/A (0 resolved trades)
- ROI: N/A (0 resolved trades)
- Average trade duration: N/A

**Once trades resolve, check:**
- ✅ Win rate >= 52% (positive EV threshold)
- ✅ ROI > 0% (profitable)
- ✅ Average delay cost < 2% (manageable slippage)

---

## Suggested Next Steps

1. **Wait for Resolutions:**
   - Monitor resolver logs for market resolutions
   - Check `logs/paper_trading.sqlite` periodically
   - Once 20+ trades resolve, re-run analysis

2. **Monitor Rejection Patterns:**
   - If low_discount rejections increase, consider adjusting threshold
   - Track if open_trade_exists is preventing profitable opportunities

3. **Verify Conversion Rate:**
   - Investigate why 279 trades from 62 signals
   - Check if historical data is included
   - Verify signal deduplication logic

4. **Run Analysis Again:**
   ```powershell
   python scripts/analyze_paper_trading.py
   ```
   - Run after 24-48 hours for more data
   - Run after first batch of resolutions

---

## Files Generated

- **Full Report:** `PAPER_TRADING_REPORT.txt`
- **Analysis Script:** `scripts/analyze_paper_trading.py`
- **Database:** `logs/paper_trading.sqlite` (2.9 MB)
- **Logs:** `logs/engine_2025-12-21.log` (693 KB)

---

## Manual Analysis Commands

### Check Database Stats
```python
import sqlite3
conn = sqlite3.connect('logs/paper_trading.sqlite')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM paper_trades WHERE status="RESOLVED"')
print(f"Resolved: {cursor.fetchone()[0]}")
```

### Count Signals in Logs
```powershell
Select-String -Path "logs\engine_2025-12-21.log" -Pattern "signal_generated" | Measure-Object
```

### Check Recent Trades
```python
import sqlite3
conn = sqlite3.connect('logs/paper_trading.sqlite')
cursor = conn.cursor()
cursor.execute('SELECT opened_at, market, confidence FROM paper_trades ORDER BY opened_at DESC LIMIT 10')
for row in cursor.fetchall():
    print(row)
```

---

**Report Generated:** `scripts/analyze_paper_trading.py`  
**Last Updated:** December 22, 2025
