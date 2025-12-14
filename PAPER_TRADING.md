# Paper Trading Mode - 48 Hour Run

## Setup Complete ✅

- `.env` file created (Telegram credentials empty for now)
- Engine ready to run
- Logs directory created

## Running the Engine

Start the engine in paper-trading mode:

```bash
python src/polymarket/engine.py
```

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

Check signal count:
```bash
# Count signals in today's log
Get-Content logs/signals_$(Get-Date -Format 'yyyy-MM-dd').csv | Measure-Object -Line
```

## Stopping the Engine

Press `Ctrl+C` to stop gracefully.

