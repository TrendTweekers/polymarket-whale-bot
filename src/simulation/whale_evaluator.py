"""
Whale Performance Evaluator
============================
Evaluates and ranks whales based on simulation results

Tracks:
- Win rate after delays
- Average P&L per trade
- Best delay for each whale
- Overall profitability score
"""

from typing import Dict, List, Optional
from collections import defaultdict
from datetime import datetime
from dataclasses import dataclass

from .trade_simulator import TradeSimulation


@dataclass
class WhalePerformance:
    """Performance metrics for a whale"""
    whale_address: str
    total_trades: int
    profitable_trades: int
    win_rate: float
    avg_pnl: float
    total_pnl: float
    best_delay: Optional[int]  # Most profitable delay
    avg_delay_pnl: Dict[int, float]  # P&L by delay
    last_trade_time: datetime


class WhaleEvaluator:
    """
    Evaluate whale performance from simulation results
    
    Tracks which whales are profitable after delays
    Ranks whales by profitability
    """
    
    def __init__(self):
        # Store simulation results: whale_address -> list of TradeSimulation
        self.simulations = defaultdict(list)
        
        # Performance cache: whale_address -> WhalePerformance
        self.performance_cache = {}
    
    def add_simulation(self, simulation: TradeSimulation):
        """
        Add a simulation result
        
        Args:
            simulation: TradeSimulation result
        """
        self.simulations[simulation.whale_address].append(simulation)
        
        # Invalidate cache for this whale
        if simulation.whale_address in self.performance_cache:
            del self.performance_cache[simulation.whale_address]
    
    def get_performance(self, whale_address: str) -> Optional[WhalePerformance]:
        """
        Get performance metrics for a whale
        
        Args:
            whale_address: Whale address
        
        Returns:
            WhalePerformance: Performance metrics
        """
        # Check cache
        if whale_address in self.performance_cache:
            return self.performance_cache[whale_address]
        
        # Calculate performance
        simulations = self.simulations.get(whale_address.lower(), [])
        if not simulations:
            return None
        
        performance = self._calculate_performance(whale_address, simulations)
        self.performance_cache[whale_address.lower()] = performance
        
        return performance
    
    def _calculate_performance(
        self,
        whale_address: str,
        simulations: List[TradeSimulation]
    ) -> WhalePerformance:
        """Calculate performance metrics from simulations"""
        
        total_trades = len(simulations)
        profitable_trades = 0
        total_pnl = 0.0
        pnl_by_delay = defaultdict(list)
        last_trade_time = datetime.min
        
        for sim in simulations:
            # Check if any delay was profitable
            if sim.profitable:
                profitable_trades += 1
            
            # Track P&L by delay
            for result in sim.results:
                if result.resolved and result.pnl is not None:
                    pnl_by_delay[result.delay_seconds].append(result.pnl)
                    total_pnl += result.pnl
            
            # Track last trade time
            if sim.detection_time > last_trade_time:
                last_trade_time = sim.detection_time
        
        # Calculate metrics
        win_rate = profitable_trades / total_trades if total_trades > 0 else 0.0
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0.0
        
        # Average P&L by delay
        avg_delay_pnl = {
            delay: sum(pnls) / len(pnls) if pnls else 0.0
            for delay, pnls in pnl_by_delay.items()
        }
        
        # Best delay (highest avg P&L)
        best_delay = None
        if avg_delay_pnl:
            best_delay = max(avg_delay_pnl.items(), key=lambda x: x[1])[0]
        
        return WhalePerformance(
            whale_address=whale_address,
            total_trades=total_trades,
            profitable_trades=profitable_trades,
            win_rate=win_rate,
            avg_pnl=avg_pnl,
            total_pnl=total_pnl,
            best_delay=best_delay,
            avg_delay_pnl=avg_delay_pnl,
            last_trade_time=last_trade_time
        )
    
    def get_top_whales(
        self,
        min_trades: int = 5,
        min_win_rate: float = 0.6,
        sort_by: str = 'win_rate'
    ) -> List[WhalePerformance]:
        """
        Get top performing whales
        
        Args:
            min_trades: Minimum number of trades required
            min_win_rate: Minimum win rate
            sort_by: Sort by 'win_rate', 'avg_pnl', or 'total_pnl'
        
        Returns:
            List[WhalePerformance]: Top whales sorted by criteria
        """
        performances = []
        
        for whale_address in self.simulations.keys():
            perf = self.get_performance(whale_address)
            if perf and perf.total_trades >= min_trades and perf.win_rate >= min_win_rate:
                performances.append(perf)
        
        # Sort
        if sort_by == 'win_rate':
            performances.sort(key=lambda x: x.win_rate, reverse=True)
        elif sort_by == 'avg_pnl':
            performances.sort(key=lambda x: x.avg_pnl, reverse=True)
        elif sort_by == 'total_pnl':
            performances.sort(key=lambda x: x.total_pnl, reverse=True)
        
        return performances
    
    def get_whale_rankings(self) -> Dict[str, int]:
        """
        Get rankings for all whales
        
        Returns:
            Dict: whale_address -> rank (1 = best)
        """
        top_whales = self.get_top_whales(min_trades=1, min_win_rate=0.0)
        
        rankings = {}
        for rank, perf in enumerate(top_whales, 1):
            rankings[perf.whale_address] = rank
        
        return rankings
