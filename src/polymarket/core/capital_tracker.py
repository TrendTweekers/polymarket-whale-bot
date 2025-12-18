"""
Capital Velocity Tracker - Ensures fast capital turnover
Only trades that resolve in 1-5 days
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import structlog

log = structlog.get_logger()


class Position:
    def __init__(self, market_id: str, amount: float, entry_time: datetime, 
                 resolution_date: datetime, whale_id: str):
        self.market_id = market_id
        self.amount = amount
        self.entry_time = entry_time
        self.resolution_date = resolution_date
        self.whale_id = whale_id
        self.duration_days = (resolution_date - entry_time).days
        self.status = "active"
        self.exit_time = None
        self.pnl = None
    
    def close(self, pnl: float):
        self.status = "closed"
        self.exit_time = datetime.now()
        self.pnl = pnl
        self.actual_duration = (self.exit_time - self.entry_time).days


class CapitalEfficiencyTracker:
    """
    Tracks capital efficiency and enforces velocity constraints
    """
    
    def __init__(self, bankroll: float = 500, max_days: int = 5):
        self.bankroll = bankroll
        self.max_days_to_resolution = max_days
        self.active_positions: List[Position] = []
        self.completed_trades: List[Position] = []
        
        log.info("capital_tracker_initialized", 
                bankroll=bankroll, 
                max_days=max_days)
    
    def calculate_velocity_score(self, days_to_resolution: int) -> float:
        """
        Score market based on resolution speed
        1-3 days = perfect (1.0)
        3-5 days = good (0.5-0.8)
        >5 days = reject (0.0)
        """
        if days_to_resolution <= 0:
            return 0.0
        
        if days_to_resolution <= 3:
            return 1.0  # PERFECT - fast turnover
        
        elif days_to_resolution <= 5:
            # Linear decay from 0.8 to 0.5
            return 0.8 - (days_to_resolution - 3) * 0.15
        
        else:
            return 0.0  # REJECT - too slow
    
    def get_locked_capital(self) -> float:
        """How much capital is in active positions"""
        return sum([pos.amount for pos in self.active_positions])
    
    def get_free_capital(self) -> float:
        """How much capital available for new trades"""
        return self.bankroll - self.get_locked_capital()
    
    def get_average_duration(self) -> float:
        """Average position duration in days"""
        if not self.completed_trades:
            return 3.0  # Default assumption
        
        durations = [t.actual_duration for t in self.completed_trades 
                    if hasattr(t, 'actual_duration')]
        
        return sum(durations) / len(durations) if durations else 3.0
    
    def get_capital_utilization(self) -> float:
        """What % of capital is deployed"""
        return self.get_locked_capital() / self.bankroll
    
    def calculate_monthly_trade_capacity(self) -> int:
        """
        Estimate how many trades we can do per month
        Based on current velocity
        """
        avg_duration = self.get_average_duration()
        avg_position_size = self.bankroll * 0.04  # 4% average
        
        # Trades per month = (days in month / avg duration) * (bankroll / avg size)
        capacity = (30 / avg_duration) * (self.bankroll / avg_position_size)
        
        return int(capacity)
    
    def should_take_position(self, amount: float, days_to_resolve: int, 
                           whale_id: str) -> Tuple[bool, str]:
        """
        Comprehensive check: can we take this position?
        """
        
        # Check 1: Resolution time
        if days_to_resolve > self.max_days_to_resolution:
            return False, f"Resolution too far: {days_to_resolve} days (max {self.max_days_to_resolution})"
        
        if days_to_resolve < 1:
            return False, "Market resolves too soon (< 1 day)"
        
        # Check 2: Available capital
        free_capital = self.get_free_capital()
        if amount > free_capital:
            return False, f"Insufficient capital: need ${amount}, have ${free_capital:.2f}"
        
        # Check 3: Velocity impact
        current_avg = self.get_average_duration()
        if days_to_resolve > current_avg * 2.0 and len(self.active_positions) > 2:
            return False, f"Would slow velocity: {days_to_resolve}d vs {current_avg:.1f}d avg"
        
        # Check 4: Position concentration
        whale_exposure = sum([p.amount for p in self.active_positions 
                             if p.whale_id == whale_id])
        if whale_exposure + amount > self.bankroll * 0.15:  # Max 15% per whale
            return False, f"Too much exposure to whale {whale_id}"
        
        # Check 5: Total position count
        if len(self.active_positions) >= 5:
            return False, "Maximum concurrent positions reached (5)"
        
        return True, "OK"
    
    def add_position(self, market_id: str, amount: float, 
                    resolution_date: datetime, whale_id: str) -> Position:
        """Add new position to tracker"""
        pos = Position(
            market_id=market_id,
            amount=amount,
            entry_time=datetime.now(),
            resolution_date=resolution_date,
            whale_id=whale_id
        )
        
        self.active_positions.append(pos)
        
        log.info("position_added",
                market_id=market_id,
                amount=amount,
                days_to_resolve=pos.duration_days,
                free_capital=self.get_free_capital(),
                utilization=self.get_capital_utilization())
        
        return pos
    
    def close_position(self, market_id: str, pnl: float):
        """Mark position as closed"""
        for pos in self.active_positions:
            if pos.market_id == market_id:
                pos.close(pnl)
                self.active_positions.remove(pos)
                self.completed_trades.append(pos)
                
                # Update bankroll
                self.bankroll += pnl
                
                log.info("position_closed",
                        market_id=market_id,
                        pnl=pnl,
                        duration_days=pos.actual_duration,
                        new_bankroll=self.bankroll)
                
                return
        
        log.warning("position_not_found", market_id=market_id)
    
    def get_velocity_metrics(self) -> Dict:
        """Get current velocity statistics"""
        return {
            'avg_duration_days': self.get_average_duration(),
            'capital_utilization': self.get_capital_utilization(),
            'active_positions': len(self.active_positions),
            'locked_capital': self.get_locked_capital(),
            'free_capital': self.get_free_capital(),
            'monthly_capacity': self.calculate_monthly_trade_capacity(),
            'completed_trades': len(self.completed_trades)
        }
