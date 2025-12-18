"""
Simulation Module - Phase 2
============================
Realistic trade simulation with delays and slippage

This module simulates copying whale trades with realistic constraints:
- Execution delays (1min, 3min, 5min)
- Slippage calculation based on market depth
- Market state tracking at detection + delays
- Whale performance evaluation and ranking
"""

from .trade_simulator import TradeSimulator
from .slippage_calculator import SlippageCalculator
from .market_state_tracker import MarketStateTracker
from .whale_evaluator import WhaleEvaluator

__all__ = [
    'TradeSimulator',
    'SlippageCalculator',
    'MarketStateTracker',
    'WhaleEvaluator'
]
