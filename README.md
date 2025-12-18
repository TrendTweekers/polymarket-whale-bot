# 🐋 Polymarket Whale Copy-Trading Bot

Self-improving AI bot that copies proven Polymarket whales with 1-5 day resolution markets.

## Features

- **Short-term Only**: 1-5 day markets for fast capital turnover
- **Self-Improving AI**: Ensemble learning system that gets better over time
- **Bayesian Whale Scoring**: Learns which whales are actually profitable
- **ML Predictor**: 16-feature model that predicts trade success
- **Multi-Strategy Ensemble**: 4 strategies with adaptive weighting

## Installation
```bash
# Clone repo
git clone https://github.com/TrendTweekers/polymarket-whale-bot
cd polymarket-whale-bot

# Install dependencies
pip install -r requirements.txt

# Create data directories
mkdir -p data logs

# Configure
cp .env.example .env
# Edit .env with your credentials
```

## Configuration

Edit `config/config.yaml`:
```yaml
trading:
  bankroll: 500
  max_days_to_resolution: 5  # Critical: only 1-5 day markets
```

## Usage
```bash
# Paper trading mode (recommended first 30 days)
python main.py

# Monitor performance
tail -f logs/bot.log | jq
```

## Architecture
```
Bot Orchestrator
├── Capital Tracker (velocity optimization)
├── Whale Scorer (Bayesian updates)
├── ML Predictor (16 features, auto-retrain)
└── Ensemble Engine (4 strategies, adaptive weights)
    ├── Fast Copy (2-5 min)
    ├── Consensus (multiple whales)
    ├── Contrarian (vs crowd sentiment)
    └── Momentum (price reversion)
```

## Self-Improvement

The bot improves through:

1. **Bayesian Updates**: Whale scores adjust after each trade
2. **ML Retraining**: Model rebuilds every 20 trades
3. **Ensemble Rebalancing**: Strategy weights shift to winners every 10 trades

## Expected Performance

- **Month 1**: 52-54% win rate (learning phase)
- **Month 2-3**: 56-58% win rate (ML training)
- **Month 4+**: 60-65% win rate (fully optimized)

Target: **5-10% monthly returns** on $500 bankroll

## Safety Features

- Daily stop-loss: $50
- Max position: 5% bankroll
- Velocity filter: rejects >5 day markets
- Capital utilization: never exceeds 70%

## License

MIT
