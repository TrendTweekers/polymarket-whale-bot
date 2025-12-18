"""
Trade Simulator - Phase 2
=========================
Simulates copying a whale trade with realistic delays and slippage

For each detected whale trade:
1. Record market state at detection time
2. Simulate execution at +1, +3, +5 min delays
3. Calculate entry price with slippage
4. Calculate P&L when market resolves
5. Return simulation results
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

from .market_state_tracker import MarketStateTracker
from .slippage_calculator import SlippageCalculator


@dataclass
class SimulationResult:
    """Results for a single delay simulation"""
    delay_seconds: int
    delay_minutes: float
    entry_price: float
    slippage_pct: float
    execution_time: datetime
    market_state_at_entry: Dict
    pnl: Optional[float] = None  # Calculated when market resolves
    pnl_pct: Optional[float] = None
    resolved: bool = False
    resolution_time: Optional[datetime] = None


@dataclass
class TradeSimulation:
    """Complete simulation results for a whale trade"""
    whale_address: str
    market_slug: str
    whale_trade_time: datetime
    whale_entry_price: float
    whale_trade_size: float
    detection_time: datetime
    
    # Results for each delay
    results: List[SimulationResult]
    
    # Summary
    best_delay: Optional[int] = None  # Delay with best P&L
    profitable: Optional[bool] = None  # True if any delay was profitable
    avg_pnl: Optional[float] = None


class TradeSimulator:
    """
    Simulates copying whale trades with realistic delays
    
    Usage:
        simulator = TradeSimulator()
        result = await simulator.simulate_trade(whale_trade_data)
    """
    
    def __init__(self):
        self.market_tracker = MarketStateTracker()
        self.slippage_calc = SlippageCalculator()
        
        # Default delays: 1min, 3min, 5min
        self.default_delays = [60, 180, 300]
    
    async def simulate_trade(
        self, 
        whale_trade: Dict, 
        delays: List[int] = None
    ) -> TradeSimulation:
        """
        Simulate copying this whale trade at different delays
        
        Args:
            whale_trade: Detected trade data with keys:
                - wallet: Whale address
                - market: Market slug
                - price: Entry price
                - size: Trade size
                - timestamp: Detection time
            delays: List of delays in seconds [60, 180, 300]
        
        Returns:
            TradeSimulation: Complete simulation results
        """
        if delays is None:
            delays = self.default_delays
        
        # Extract trade data
        whale_address = whale_trade.get('wallet', '').lower()
        market_slug = whale_trade.get('market', '')
        whale_price = float(whale_trade.get('price', 0))
        whale_size = float(whale_trade.get('size', 0))
        detection_time = self._parse_timestamp(whale_trade.get('timestamp'))
        
        # Record market state at detection
        await self.market_tracker.record_state(
            market_slug=market_slug,
            timestamp=detection_time,
            price=whale_price
        )
        
        # Simulate each delay
        results = []
        for delay_seconds in delays:
            result = await self._simulate_delay(
                market_slug=market_slug,
                detection_time=detection_time,
                delay_seconds=delay_seconds,
                trade_size=whale_size
            )
            results.append(result)
        
        # Create simulation object
        simulation = TradeSimulation(
            whale_address=whale_address,
            market_slug=market_slug,
            whale_trade_time=detection_time,
            whale_entry_price=whale_price,
            whale_trade_size=whale_size,
            detection_time=detection_time,
            results=results
        )
        
        # Calculate summary metrics
        self._calculate_summary(simulation)
        
        return simulation
    
    async def _simulate_delay(
        self,
        market_slug: str,
        detection_time: datetime,
        delay_seconds: int,
        trade_size: float
    ) -> SimulationResult:
        """
        Simulate execution at a specific delay
        
        Args:
            market_slug: Market identifier
            detection_time: When trade was detected
            delay_seconds: Delay in seconds
            trade_size: Size of trade to simulate
        
        Returns:
            SimulationResult: Results for this delay
        """
        execution_time = detection_time + timedelta(seconds=delay_seconds)
        
        # Get market state at execution time
        market_state = await self.market_tracker.get_state_at_time(
            market_slug=market_slug,
            timestamp=execution_time
        )
        
        if not market_state:
            # Fallback: use current state or detection state
            market_state = await self.market_tracker.get_latest_state(market_slug)
        
        entry_price = market_state.get('price', 0)
        
        # Calculate slippage
        slippage_pct = self.slippage_calc.calculate_slippage(
            market_slug=market_slug,
            trade_size=trade_size,
            current_price=entry_price,
            market_state=market_state
        )
        
        # Apply slippage to entry price
        adjusted_entry_price = entry_price * (1 + slippage_pct)
        
        return SimulationResult(
            delay_seconds=delay_seconds,
            delay_minutes=delay_seconds / 60.0,
            entry_price=adjusted_entry_price,
            slippage_pct=slippage_pct,
            execution_time=execution_time,
            market_state_at_entry=market_state
        )
    
    async def resolve_simulation(
        self,
        simulation: TradeSimulation,
        resolution_price: float,
        resolution_time: datetime
    ):
        """
        Calculate P&L when market resolves
        
        Args:
            simulation: TradeSimulation to resolve
            resolution_price: Final market price (0 or 1)
            resolution_time: When market resolved
        """
        for result in simulation.results:
            if result.resolved:
                continue
            
            # Calculate P&L
            # If we bought at result.entry_price, profit = resolution_price - entry_price
            pnl = resolution_price - result.entry_price
            pnl_pct = (pnl / result.entry_price) * 100 if result.entry_price > 0 else 0
            
            result.pnl = pnl
            result.pnl_pct = pnl_pct
            result.resolved = True
            result.resolution_time = resolution_time
        
        # Recalculate summary
        self._calculate_summary(simulation)
    
    def _calculate_summary(self, simulation: TradeSimulation):
        """Calculate summary metrics for simulation"""
        resolved_results = [r for r in simulation.results if r.resolved]
        
        if not resolved_results:
            return
        
        # Find best delay
        best_result = max(resolved_results, key=lambda r: r.pnl or -999)
        simulation.best_delay = best_result.delay_seconds
        
        # Check if profitable
        simulation.profitable = any(r.pnl and r.pnl > 0 for r in resolved_results)
        
        # Average P&L
        pnls = [r.pnl for r in resolved_results if r.pnl is not None]
        if pnls:
            simulation.avg_pnl = sum(pnls) / len(pnls)
    
    def _parse_timestamp(self, timestamp) -> datetime:
        """Parse timestamp from various formats"""
        if isinstance(timestamp, datetime):
            return timestamp
        elif isinstance(timestamp, (int, float)):
            return datetime.fromtimestamp(timestamp)
        elif isinstance(timestamp, str):
            if 'T' in timestamp:
                return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                return datetime.fromtimestamp(float(timestamp))
        else:
            return datetime.now()
