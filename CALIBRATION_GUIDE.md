# Calibration Guide

## Quick Start

### Step 1: Drop Threshold Temporarily

For calibration (30-60 minutes):

```powershell
# Option 1: Use calibration script
.\run_calibration.ps1 -Threshold 0.02

# Option 2: Manual
$env:MIN_WHALE_SCORE="0.02"
python .\src\polymarket\engine.py

# Option 3: See all trades (very noisy)
$env:MIN_WHALE_SCORE="0.0"
python .\src\polymarket\engine.py
```

### Step 2: Wait for Histogram Output

You'll start seeing every 10 cycles (~5 minutes):

```
CALIBRATION HISTOGRAM (Cycle X, N samples)
================================================================================
Whale Score Distribution:
  0:                   1234 (45.2%)
  (0-0.01]:            567 (20.8%)
  (0.01-0.05]:         234 (8.6%)
  (0.05-0.1]:          345 (12.6%)
  (0.1-0.2]:           234 (8.6%)
  (0.2-0.5]:           89 (3.3%)
  >0.5:                45 (1.6%)

Current MIN_WHALE_SCORE threshold: 0.02

Top 20 Highest Whale Scores:
   1. Score: 0.8234 | Wallet: 0x1234... | Trade: $138,234.56 | Condition: 0xabc...
   2. Score: 0.7123 | Wallet: 0x5678... | Trade: $45,678.90 | Condition: 0xdef...
   ...
```

### Step 3: Pick a Real Production Threshold

Based on histogram data, choose threshold:

- **0.02** → Noisy but active (good for testing)
- **0.03-0.04** → Realistic "whale" alerts (recommended for production)
- **0.06+** → Rare, very strong wallets only

## What to Look For

### Healthy System Indicators:
- ✅ Histogram shows distribution across buckets (not all 0)
- ✅ Top 20 scores show real values (0.1-0.9 range)
- ✅ Scores reflect actual trade sizes

### Red Flags:
- ❌ All scores = 0 → Scoring broken
- ❌ All scores in one bucket → Threshold needs adjustment
- ❌ No histogram after 10 cycles → No trades being processed

## Current Configuration

Check `.env` for:
- `MIN_WHALE_SCORE=0.1` (production baseline)
- `PRODUCTION_MODE=True`
- `BYPASS_SCORE_ON_STATS_FAIL=False`

## After Calibration

Once you've determined the optimal threshold:

1. Update `.env`:
   ```
   MIN_WHALE_SCORE=0.03  # or your chosen value
   ```

2. Restart engine with production settings

3. Monitor signals and adjust as needed

