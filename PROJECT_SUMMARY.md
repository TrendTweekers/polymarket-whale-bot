# Polymarket Whale Signal Engine - Comprehensive Summary

## 🎯 Project Goal

Build an automated trading signal engine that identifies and follows high-performing "whale" traders on Polymarket (a prediction market platform). The engine monitors large trades, scores traders based on historical performance, and generates buy signals when whales enter positions at favorable prices.

**Core Strategy:**
- Track large trades ($1k+) from successful traders
- Score traders (0-1 scale) based on win rate, profit, drawdown, hold time
- Generate signals when high-scoring whales buy at discounts ≥ threshold
- Cluster multiple smaller trades from same whale in same market
- Send Telegram alerts for manual review/approval

---

## 📁 Project Structure

```
polymarket-whale-engine/
├── src/polymarket/          # Main source code
│   ├── engine.py            # Core signal generation engine (1121 lines)
│   ├── scraper.py           # API data fetching (375 lines)
│   ├── profiler.py          # Whale stats fetching (167 lines)
│   ├── score.py             # Whale scoring algorithm (239 lines)
│   ├── telegram.py          # Telegram notifications (53 lines)
│   ├── telegram_notify.py  # Signal stats tracking (56 lines)
│   ├── backtest.py          # Backtesting simulation (327 lines)
│   └── analyze.py           # Signal analysis tools
├── logs/                    # Generated data files
│   ├── signals_YYYY-MM-DD.csv      # Production signals
│   ├── activity_YYYY-MM-DD.csv     # All whale activity (dual logging)
│   ├── scan_stats_YYYY-MM-DD.csv   # Market scan statistics
│   ├── status_YYYY-MM-DD.log       # Cycle-by-cycle status
│   └── quality_audit.txt            # Data quality reports
├── tests/                   # Unit tests
├── venv/                   # Python virtual environment
├── .env                    # Configuration (secrets + thresholds)
├── requirements.txt        # Python dependencies
└── PROJECT_SUMMARY.md      # This file
```

---

## 🏗️ Architecture Overview

### **Data Flow Pipeline**

```
1. Market Discovery
   └─> scraper.py::fetch_top_markets()
       └─> Fetches top-volume markets from gamma-api.polymarket.com
       └─> Extracts conditionId, clobTokenIds, bestBid/bestAsk
       └─> Filters excluded categories (e.g., sports)

2. Trade Scanning
   └─> scraper.py::fetch_trades_scanned()
       └─> Multi-page client-side scanning (25 pages = 2500 trades/market)
       └─> Filters by API_MIN_SIZE_USD ($1k default)
       └─> Returns trades ≥ threshold

3. Trade Processing (per trade)
   └─> engine.py::process_trade()
       ├─> Deduplication check (SEEN_TRADE_KEYS)
       ├─> Category filter (exclude sports, etc.)
       ├─> Side filter (BUY only)
       ├─> Whale scoring
       │   └─> profiler.py::get_whale_stats()
       │       └─> Fetches from data-api.polymarket.com/user-stats/{user_id}
       │       └─> Caches for 1 hour
       │   └─> score.py::whale_score()
       │       └─> Computes 0-1 score based on:
       │           • 40% category-specific win rate
       │           • 30% consistency (profit/drawdown)
       │           • 20% hold time (2-24h optimal)
       │           • 10% overall win rate
       ├─> Price fetching
       │   └─> scraper.py::get_midpoint_price_cached()
       │       └─> Tries CLOB midpoint API first
       │       └─> Falls back to Gamma bestBid/bestAsk
       ├─> Discount calculation
       │   └─> (whale_entry_price - current_price) / whale_entry_price * 100
       ├─> Activity logging (all whale trades ≥ 0.05 score)
       └─> Clustering or direct signal generation

4. Whale Clustering
   └─> engine.py::add_trade_to_cluster()
       └─> Groups trades by: wallet + market + time window (5 min)
       └─> Tracks cumulative USD, trade count, first trade time
       └─> When cluster reaches CLUSTER_MIN_USD ($10k):
           ├─> Check CLUSTER_MIN_TRADES (default: 3)
           ├─> Check CLUSTER_MIN_AVG_HOLD_MINUTES (default: 30, arb bot filter)
           └─> Generate cluster signal

5. Signal Generation
   └─> engine.py::generate_cluster_signal() or direct signal
       ├─> Final filters:
       │   ├─> Discount ≥ MIN_DISCOUNT_PCT (default: 2.0%)
       │   ├─> Orderbook depth ≥ MIN_ORDERBOOK_DEPTH_MULTIPLIER (3x)
       │   └─> No conflicting trades (SELL from same whale in 5 min)
       ├─> Log to CSV (signals_YYYY-MM-DD.csv)
       ├─> Send Telegram notification
       └─> Track in recent_signals list

6. Status Logging
   └─> engine.py::append_status_line()
       └─> Writes gate_breakdown counters to status_YYYY-MM-DD.log
       └─> Tracks: trades_considered, signals_generated, rejection reasons
```

---

## 🔧 Key Components

### **1. engine.py** (Core Signal Engine)
**Purpose:** Main orchestration loop that polls trades, scores whales, and generates signals.

**Key Functions:**
- `main_loop()`: Async polling loop (runs every 30 seconds)
- `process_trade()`: Process individual trade, apply filters, cluster or signal
- `add_trade_to_cluster()`: Group trades from same whale in same market
- `generate_cluster_signal()`: Create signal from completed cluster
- `get_whale_with_score()`: Fetch stats and compute score (no whitelist gate)
- `ensure_whale_whitelisted()`: Fetch stats, score, and enforce whitelist gate
- `log_signal_to_csv()`: Write signal to daily CSV file
- `log_all_activity()`: Log all whale trades (dual logging)
- `audit_data_quality()`: Analyze signals CSV for quality metrics

**Key Features:**
- **Trade Deduplication:** Global `SEEN_TRADE_KEYS` set prevents re-processing
- **Whale Clustering:** Groups $2k-$8k trades from same wallet+market within 5 min
- **Filter Diagnostics:** Counters for each rejection reason
- **Dual Logging:** All activity + filtered signals
- **Production Mode:** Toggle strict filters via `PRODUCTION_MODE` env var

**Configuration (Environment Variables):**
- `PRODUCTION_MODE`: Enable strict production filters
- `MIN_WHALE_SCORE`: Minimum score threshold (default: 0.70)
- `MIN_DISCOUNT_PCT`: Minimum discount % (default: 2.0%)
- `CLUSTER_MIN_TRADES`: Minimum trades per cluster (default: 3)
- `CLUSTER_MIN_HOLD`: Minimum avg hold time in minutes (default: 30)
- `CLUSTER_MIN_USD`: Cumulative threshold for cluster signal (default: $10k)
- `API_MIN_SIZE_USD`: API filter threshold (default: $1k)
- `SIGNAL_MIN_SIZE_USD`: Signal gate threshold (default: $10k)
- `WHITELIST_ONLY`: Only allow whitelisted whales (default: follows PRODUCTION_MODE)
- `EXCLUDE_CATEGORIES`: Comma-separated categories to exclude (e.g., "sports")
- `LOG_LEVEL`: Logging verbosity (INFO/DEBUG)
- `DAILY_SIGNAL_LIMIT`: Max signals per day (default: 3)

---

### **2. scraper.py** (Data Fetching)
**Purpose:** Fetch trades, markets, and price data from Polymarket APIs.

**Key Functions:**
- `fetch_top_markets()`: Get top-volume markets from gamma-api.polymarket.com
  - Returns conditionId, clobTokenIds, bestBid, bestAsk
  - Filters excluded categories at source
- `fetch_trades_scanned()`: Multi-page client-side trade scanning
  - Scans 25 pages (2500 trades) per market
  - Filters by API_MIN_SIZE_USD
  - Logs scan stats to CSV
- `get_midpoint_price_cached()`: Fetch midpoint from CLOB API
  - Tries `https://clob.polymarket.com/midpoint?token_id={token_id}`
  - 10-second TTL cache
- `get_market_midpoint_cached()`: Fallback midpoint from Gamma API
  - Uses bestBid/bestAsk from market data
  - 10-second TTL cache
- `get_token_id_for_condition()`: Map conditionId → clobTokenId
  - Uses cached market data
  - Considers trade side (BUY/YES vs SELL/NO)
- `log_scan_stats()`: Log scan statistics to CSV

**API Endpoints Used:**
- `https://gamma-api.polymarket.com/markets` - Market data
- `https://data-api.polymarket.com/trades` - Trade history
- `https://clob.polymarket.com/midpoint` - Orderbook midpoint (often 404)
- `https://data-api.polymarket.com/user-stats/{user_id}` - User stats (often 404)

---

### **3. profiler.py** (Whale Statistics)
**Purpose:** Fetch and cache whale trading statistics.

**Key Functions:**
- `get_whale_stats()`: Fetch stats for a user_id
  - Tries multiple endpoint patterns (user-stats, users/{id}/stats, etc.)
  - Returns structured dict with:
    - `total_profit`: Total profit in USD
    - `win_rate`: Overall win rate (0-1)
    - `max_drawdown`: Maximum drawdown (0-1)
    - `avg_hold_time_hours`: Average hold time
    - `trades_count`: Total trades
    - `segmented_win_rate`: Dict by category (elections, sports, crypto, geo)
  - Caches for 1 hour
  - Returns empty stats structure if all endpoints 404 (graceful degradation)

**Note:** User stats endpoints often return 404, so the engine gracefully handles missing stats.

---

### **4. score.py** (Whale Scoring)
**Purpose:** Compute 0-1 score for whales based on performance metrics.

**Key Functions:**
- `whale_score()`: Compute composite score
  - **40%** Category-specific win rate (must be ≥ 55% to contribute)
  - **30%** Consistency = total_profit / (max_drawdown + 1)
  - **20%** Hold time score (1.0 if 2-24h, else 0.5)
  - **10%** Overall win rate
  - Returns score clamped to [0, 1]
- `whitelist_whales()`: Filter and return top 5 whales per category
  - Filters by min_score threshold
  - Returns top 5 per category, sorted by score

---

### **5. telegram.py** (Notifications)
**Purpose:** Send Telegram alerts for engine lifecycle and signals.

**Key Functions:**
- `send_telegram()`: Sync HTTP POST to Telegram API
- `notify_engine_start()`: Send "🟢 Polymarket engine started"
- `notify_engine_stop()`: Send "🔴 Polymarket engine stopped"
- `notify_engine_crash()`: Send crash notification with error
- `notify_signal()`: Send formatted signal notification

**Configuration:**
- `TELEGRAM_BOT_TOKEN`: Bot token from @BotFather
- `TELEGRAM_CHAT_ID`: Chat ID to send messages to

---

### **6. backtest.py** (Backtesting)
**Purpose:** Simulate trades from historical signals and compute performance metrics.

**Key Functions:**
- `load_signals()`: Load signals CSV with encoding handling
- `load_activity()`: Load activity CSV with encoding handling
- `filter_production_signals()`: Filter to production thresholds
- `run_backtest()`: Simulate trades
  - Entry: current_price from signal
  - Exit: 50% profit OR 4-hour hold OR -15% stop
  - Position size: $25 per trade
  - Gas fee: $0.10 per trade
- `compute_metrics()`: Calculate performance metrics
  - Win rate
  - Average ROI
  - Sharpe ratio (risk-free rate = 0)
  - Max drawdown
  - Expectancy
- Generates plots: ROI histogram, equity curve

---

## 📊 Data Structures

### **Signal Dictionary**
```python
{
    "timestamp": "2025-12-15T20:30:00Z",
    "wallet": "0x...",
    "whale_score": 0.75,
    "category": "crypto",
    "market": "Will BTC reach $100k?",
    "slug": "will-btc-reach-100k",
    "condition_id": "0x...",
    "whale_entry_price": 0.65,
    "current_price": 0.63,
    "discount_pct": 3.08,
    "size": 100.0,
    "trade_value_usd": 6500.0,
    "orderbook_depth_ratio": 5.0,
    "transaction_hash": "0x...",
    "cluster_trades_count": 3,
    "cluster_window_minutes": 4
}
```

### **Cluster Dictionary**
```python
{
    "trades": [trade1, trade2, trade3],
    "total_usd": 12777.0,
    "first_trade_time": datetime(...),
    "whale": {
        "wallet": "0x...",
        "stats": {...},
        "score": 0.75,
        "category": "crypto"
    },
    "category": "crypto",
    "wallet": "0x...",
    "market_id": "0x...",
    "market_title": "Will BTC reach $100k?",
    "slug": "will-btc-reach-100k",
    "trade_keys": {"key1", "key2", "key3"},  # Deduplication
    "triggered": False  # Prevents re-firing
}
```

---

## 🔄 Main Loop Flow

```python
async def main_loop():
    while True:
        # 1. Fetch top markets (limit: 10 in production, 20 otherwise)
        markets = await fetch_top_markets(session, limit=10 if PRODUCTION_MODE else 20)
        
        # 2. For each market, scan trades
        for market in markets:
            condition_id = market["conditionId"]
            trades = await fetch_trades_scanned(session, condition_id, API_MIN_SIZE_USD, pages=25)
            
            # 3. Process each trade
            for trade in trades:
                # Deduplication check
                trade_k = trade_key(trade)
                if trade_k in SEEN_TRADE_KEYS:
                    continue
                SEEN_TRADE_KEYS.add(trade_k)
                
                # Process trade (clustering or direct signal)
                signal = await process_trade(session, trade)
                
                if signal:
                    # Log signal to CSV
                    log_signal_to_csv(signal)
                    
                    # Send Telegram notification
                    notify_signal(signal)
                    
                    # Track in recent_signals
                    recent_signals.append(signal)
        
        # 4. Cleanup expired clusters
        cleanup_expired_clusters()
        
        # 5. Log status breakdown
        append_status_line(gate_breakdown)
        
        # 6. Wait for next poll
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
```

---

## 🎛️ Configuration Modes

### **Production Mode** (`PRODUCTION_MODE=True`)
- Strict filters: score ≥ 0.70, discount ≥ 2.0%
- Whitelist-only (unless `WHITELIST_ONLY=False` explicitly set)
- No bypasses on stats failures
- Limited market scanning (top 10 markets)
- Daily signal limit enforced

### **Data Collection Mode** (`PRODUCTION_MODE=False`)
- Relaxed thresholds for calibration
- Whitelist disabled (unless explicitly enabled)
- Bypass score on stats failures
- Wider market scanning (top 20 markets)
- Higher daily signal limit

### **Phase 1b Calibration** (Current)
- `MIN_WHALE_SCORE=0.1` (very low for testing)
- `MIN_DISCOUNT_PCT=0.5` (moderate quality gate)
- `CLUSTER_MIN_TRADES=1` (allows single-trade signals)
- `CLUSTER_MIN_HOLD=0` (no hold-time filter)
- `EXCLUDE_CATEGORIES=sports` (exclude sports markets)

---

## 📈 Current Status

**Statistics (as of latest check):**
- Total trades scanned: 18,327,500
- Total trades kept (≥ $1k): 153,244
- Whale activities logged: 4,971
- Signals generated: 0 (Phase 1b calibration in progress)

**Main Blockers:**
- `rejected_low_score`: Even with MIN_WHALE_SCORE=0.1, many trades score below threshold
- `rejected_discount_missing`: Price fetching sometimes fails (CLOB 404s, fallback issues)
- Clustering: Trades may not be clustering (need to verify cluster logic)

**Next Steps:**
1. Verify discount calculation is working (check activity log)
2. Verify clustering is triggering (check cluster logs)
3. Collect 50-100 signals with relaxed thresholds
4. Analyze signal quality (win rate, discount distribution, etc.)
5. Tighten thresholds for production

---

## 🛠️ Dependencies

**Core Libraries:**
- `aiohttp`: Async HTTP client for API calls
- `asyncio`: Async event loop
- `structlog`: Structured logging
- `pandas`: Data manipulation (CSV, analysis)
- `numpy`: Numerical operations
- `matplotlib`: Plotting (backtesting)
- `python-dotenv`: Environment variable loading
- `requests`: Sync HTTP (Telegram)

**Python Version:** 3.11+

---

## 📝 Key Design Decisions

1. **Client-Side Multi-Page Scanning:** Instead of server-side filtering (unreliable), scan 25 pages client-side and filter locally
2. **Whale Clustering:** Groups smaller trades ($2k-$8k) from same whale in same market to form $10k+ signals
3. **Dual Logging:** Log all whale activity (for analysis) + filtered signals (for trading)
4. **Trade Deduplication:** Global cache prevents re-processing same trades across polls
5. **Graceful Degradation:** Handles missing stats/endpoints without crashing
6. **Sync Telegram:** Simple `requests` library instead of async to avoid event loop issues
7. **Environment-Driven Config:** All thresholds configurable via `.env` for easy calibration
8. **Filter Diagnostics:** Counters track rejection reasons for debugging

---

## 🚀 Usage

**Start Engine:**
```bash
python src/polymarket/engine.py
```

**Check Status:**
```powershell
Get-Content .\logs\status_$(Get-Date -Format "yyyy-MM-dd").log -Tail 10
```

**Check Signals:**
```powershell
Import-Csv "logs\signals_$(Get-Date -Format 'yyyy-MM-dd').csv" | Select-Object -Last 20
```

**Run Backtest:**
```bash
python src/polymarket/backtest.py
```

---

## 🔍 Troubleshooting

**No Signals Generated:**
1. Check `rejected_low_score` count (score threshold too high)
2. Check `rejected_discount_missing` (price fetching failing)
3. Check `rejected_below_cluster_min` (clustering threshold)
4. Verify `.env` settings are loaded correctly

**Telegram Not Working:**
1. Verify token is valid: `python -c "from src.polymarket.telegram import notify_engine_start; notify_engine_start()"`
2. Check `.env` file formatting (no BOM, each var on separate line)
3. Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set

**Price Fetching Failing:**
1. CLOB midpoint endpoint often returns 404 (expected)
2. Fallback to Gamma bestBid/bestAsk should work
3. Check `rejected_discount_missing` counter in status log

---

## 📚 Additional Files

- `PAPER_TRADING.md`: Paper trading guidelines
- `analyze.py`: Signal analysis tools (5 key questions)
- `quality_audit.txt`: Data quality reports (generated by engine)

---

**Last Updated:** 2025-12-15
**Version:** Phase 1b (Calibration)

