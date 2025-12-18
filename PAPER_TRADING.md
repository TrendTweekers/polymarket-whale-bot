# Paper Trading Mode - 48 Hour Run

## Setup Complete ✅

- `.env` file created (Telegram credentials empty for now)
- Engine ready to run
- Logs directory created

## Running the Engine

Start the engine in paper-trading mode with fast feedback filters:

**PowerShell:**
```powershell
$env:PAPER_TRADING='1'
$env:PAPER_MAX_DTE_DAYS='2'
$env:PAPER_MIN_CONFIDENCE='60'
$env:PAPER_MIN_DISCOUNT_PCT='0.0001'
$env:PAPER_MIN_TRADE_USD='50'
$env:PAPER_STAKE_EUR='2.0'
$env:FX_EUR_USD='1.10'
$env:RESOLVER_INTERVAL_SECONDS='300'
python .\src\polymarket\engine.py
```

**Environment Variables:**
- `PAPER_TRADING=1` - Enable paper trading
- `PAPER_MAX_DTE_DAYS=2` - Only trade markets expiring within 2 days (for fast feedback)
- `PAPER_MIN_CONFIDENCE=60` - Minimum confidence (0-100) to open paper trade
- `PAPER_MIN_DISCOUNT_PCT=0.0001` - Minimum discount (as fraction, e.g., 0.0001 = 0.01%)
- `PAPER_MIN_TRADE_USD=50` - Minimum trade value USD
- `PAPER_STAKE_EUR=2.0` - Stake per trade in EUR
- `FX_EUR_USD=1.10` - EUR to USD exchange rate
- `RESOLVER_INTERVAL_SECONDS=300` - Resolver check interval (5 minutes)

## What Happens

The engine will:
- ✅ Poll trades every 30 seconds
- ✅ Filter for trades ≥ $10,000
- ✅ Score whales in real-time
- ✅ Generate signals when conditions are met:
  - Whale score ≥ 0.70
  - Discount ≥ 5%
  - Orderbook depth ≥ 3× trade size
  - No conflicting whale trades
- ✅ Log all signals to `logs/signals_YYYY-MM-DD.csv`
- ✅ Print to console (no Telegram alerts yet)
- ✅ Respect daily limits (max 3 signals/day)

## Expected Output

You'll see console logs like:
```
2025-12-14 12:00:00 [info] engine_started poll_interval=30
2025-12-14 12:00:00 [info] fetched recent trades total=100 filtered=5 min_size_usd=10000
2025-12-14 12:00:05 [info] signal_generated wallet=0x... discount=5.2 market=Will Bitcoin...
```

## Signal CSV Format

Signals are logged to `logs/signals_YYYY-MM-DD.csv` with columns:
- timestamp
- wallet
- whale_score
- category
- market
- slug
- condition_id
- whale_entry_price
- current_price
- discount_pct
- size
- trade_value_usd
- orderbook_depth_ratio
- transaction_hash

## Goal

Run for **48 hours** to collect **≥ 30 signals** for back-testing.

## After 48 Hours

Once you have 30+ signals, we'll build `backtest.py` to:
- Simulate entry at signal price
- Exit after 4h OR 50% gain OR whale exit
- Calculate Sharpe ratio, win-rate, max drawdown
- If Sharpe ≥ 1.5 → enable Telegram approval and start $50 paper trades

## Monitoring

**Check paper trading statistics:**
```powershell
python .\scripts\paper_report.py
```

**Check signal statistics:**
```powershell
python .\scripts\signals_report.py
```

**Count signals in today's CSV:**
```powershell
Get-Content logs/signals_$(Get-Date -Format 'yyyy-MM-dd').csv | Measure-Object -Line
```

## Paper Trading Filters

Paper trades are only created when **all** of these conditions are met:

1. ✅ `confidence >= PAPER_MIN_CONFIDENCE` (default: 60)
2. ✅ `days_to_expiry <= PAPER_MAX_DTE_DAYS` (default: 2.0 days)
3. ✅ `discount_pct >= PAPER_MIN_DISCOUNT_PCT` (default: 0.0001)
4. ✅ `trade_value_usd >= PAPER_MIN_TRADE_USD` (default: 50.0)

If any filter fails, the signal is still stored but no paper trade is created. Check logs for `paper_trade_skipped` events to see why trades were filtered out.

## Stopping the Engine

Press `Ctrl+C` to stop gracefully.

