"""
Risk Manager - Hard Risk Limits
================================
Prevents catastrophic losses with strict limits

Kimi's Requirements:
- Daily loss limit: 2% hard stop
- Max positions: 5 concurrent
- Max position size: 5% of bankroll
- Kill switch: Halt trading on limit breach
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class Position:
    """Represents an active trading position"""
    market_slug: str
    entry_price: float
    size: float
    entry_time: datetime
    side: str  # 'YES' or 'NO'
    whale_address: Optional[str] = None


class RiskManager:
    """
    Hard risk limits to prevent catastrophic losses
    
    Implements Kimi's safety requirements:
    - Daily loss limit (2% hard stop)
    - Position count limit (max 5)
    - Position size limit (max 5% per trade)
    - Kill switch functionality
    """
    
    def __init__(self, bankroll: float = 1000.0):
        """
        Initialize risk manager
        
        Args:
            bankroll: Starting capital in USD
        """
        self.initial_bankroll = bankroll
        self.bankroll = bankroll
        
        # Risk limits (Kimi's requirements)
        self.daily_loss_limit = 0.02  # 2% max daily loss
        self.max_positions = 5  # Max concurrent positions
        self.max_position_size = 0.05  # 5% max per position
        
        # Tracking
        self.daily_pnl = 0.0
        self.active_positions: List[Position] = []
        self.trade_history: List[Dict] = []
        self.daily_reset_time = datetime.now().replace(hour=0, minute=0, second=0)
        
        # Kill switch
        self.kill_switch_active = False
        self.kill_switch_reason = ""
    
    def can_trade(self, proposed_size: float) -> Tuple[bool, str]:
        """
        Check if trade is allowed under risk limits
        
        Args:
            proposed_size: Size of proposed trade in USD
        
        Returns:
            Tuple[bool, str]: (allowed, reason)
        """
        # Check kill switch first
        if self.kill_switch_active:
            return False, f"KILL SWITCH ACTIVE: {self.kill_switch_reason}"
        
        # Reset daily P&L if new day
        self._check_daily_reset()
        
        # Check 1: Daily loss limit (Kimi's requirement)
        daily_loss_threshold = self.initial_bankroll * self.daily_loss_limit
        if self.daily_pnl <= -daily_loss_threshold:
            self._activate_kill_switch(f"Daily loss limit (-2%) hit: ${self.daily_pnl:.2f}")
            return False, f"KILL SWITCH: Daily loss limit (-2%) hit: ${self.daily_pnl:.2f}"
        
        # Check 2: Max positions (Kimi's requirement)
        if len(self.active_positions) >= self.max_positions:
            return False, f"Max positions ({self.max_positions}) reached"
        
        # Check 3: Position size limit (Kimi's requirement)
        max_size = self.bankroll * self.max_position_size
        if proposed_size > max_size:
            return False, f"Position too large (max ${max_size:.0f}, proposed ${proposed_size:.0f})"
        
        # Check 4: Sufficient bankroll
        if proposed_size > self.bankroll:
            return False, f"Insufficient bankroll (${self.bankroll:.2f} available, ${proposed_size:.2f} required)"
        
        # Check 5: Minimum position size (prevent dust trades)
        if proposed_size < 10.0:
            return False, "Position too small (minimum $10)"
        
        return True, "OK"
    
    def add_position(
        self,
        market_slug: str,
        entry_price: float,
        size: float,
        side: str = 'YES',
        whale_address: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Add a new position (if allowed by risk limits)
        
        Args:
            market_slug: Market identifier
            entry_price: Entry price (0-1)
            size: Position size in USD
            side: 'YES' or 'NO'
            whale_address: Optional whale address
        
        Returns:
            Tuple[bool, str]: (success, reason)
        """
        # Check if allowed
        allowed, reason = self.can_trade(size)
        if not allowed:
            return False, reason
        
        # Deduct from bankroll
        self.bankroll -= size
        
        # Create position
        position = Position(
            market_slug=market_slug,
            entry_price=entry_price,
            size=size,
            entry_time=datetime.now(),
            side=side,
            whale_address=whale_address
        )
        
        self.active_positions.append(position)
        
        return True, "Position added"
    
    def close_position(
        self,
        market_slug: str,
        exit_price: float,
        exit_time: Optional[datetime] = None
    ) -> Tuple[bool, float]:
        """
        Close a position and calculate P&L
        
        Args:
            market_slug: Market identifier
            exit_price: Exit price (0-1)
            exit_time: Exit time (default: now)
        
        Returns:
            Tuple[bool, float]: (success, pnl)
        """
        if exit_time is None:
            exit_time = datetime.now()
        
        # Find position
        position = None
        for pos in self.active_positions:
            if pos.market_slug == market_slug:
                position = pos
                break
        
        if not position:
            return False, 0.0
        
        # Calculate P&L
        if position.side == 'YES':
            # Bought YES, profit = (exit_price - entry_price) * size
            pnl = (exit_price - position.entry_price) * position.size
        else:
            # Bought NO, profit = (entry_price - exit_price) * size
            pnl = (position.entry_price - exit_price) * position.size
        
        # Record trade
        self.record_trade(
            size=position.size,
            pnl=pnl,
            market_slug=market_slug,
            entry_price=position.entry_price,
            exit_price=exit_price
        )
        
        # Remove from active positions
        self.active_positions.remove(position)
        
        # Add back to bankroll (with P&L)
        self.bankroll += position.size + pnl
        
        return True, pnl
    
    def record_trade(
        self,
        size: float,
        pnl: float,
        market_slug: Optional[str] = None,
        entry_price: Optional[float] = None,
        exit_price: Optional[float] = None
    ):
        """
        Record trade outcome and update daily P&L
        
        Args:
            size: Trade size in USD
            pnl: Profit/loss in USD
            market_slug: Market identifier (optional)
            entry_price: Entry price (optional)
            exit_price: Exit price (optional)
        """
        self.daily_pnl += pnl
        
        trade_record = {
            'size': size,
            'pnl': pnl,
            'market_slug': market_slug,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'timestamp': datetime.now().isoformat(),
            'daily_pnl': self.daily_pnl,
            'bankroll': self.bankroll
        }
        
        self.trade_history.append(trade_record)
        
        # Check if kill switch should activate
        daily_loss_threshold = self.initial_bankroll * self.daily_loss_limit
        if self.daily_pnl <= -daily_loss_threshold:
            self._activate_kill_switch(f"Daily loss limit breached: ${self.daily_pnl:.2f}")
    
    def _check_daily_reset(self):
        """Reset daily P&L if new day"""
        now = datetime.now()
        if now.date() > self.daily_reset_time.date():
            self.daily_pnl = 0.0
            self.daily_reset_time = now.replace(hour=0, minute=0, second=0)
            self.kill_switch_active = False
            self.kill_switch_reason = ""
            print(f"📅 Daily reset: P&L reset to $0.00")
    
    def _activate_kill_switch(self, reason: str):
        """Activate kill switch to halt trading"""
        if not self.kill_switch_active:
            self.kill_switch_active = True
            self.kill_switch_reason = reason
            print(f"🚨 KILL SWITCH ACTIVATED: {reason}")
    
    def get_risk_status(self) -> Dict:
        """
        Get current risk status
        
        Returns:
            Dict: Risk metrics and status
        """
        self._check_daily_reset()
        
        daily_loss_threshold = self.initial_bankroll * self.daily_loss_limit
        remaining_loss_capacity = daily_loss_threshold + self.daily_pnl
        
        return {
            'bankroll': self.bankroll,
            'initial_bankroll': self.initial_bankroll,
            'daily_pnl': self.daily_pnl,
            'daily_loss_limit': daily_loss_threshold,
            'remaining_loss_capacity': remaining_loss_capacity,
            'active_positions': len(self.active_positions),
            'max_positions': self.max_positions,
            'max_position_size': self.bankroll * self.max_position_size,
            'kill_switch_active': self.kill_switch_active,
            'kill_switch_reason': self.kill_switch_reason,
            'total_trades': len(self.trade_history)
        }
    
    def get_position_summary(self) -> List[Dict]:
        """Get summary of active positions"""
        return [
            {
                'market': pos.market_slug,
                'entry_price': pos.entry_price,
                'size': pos.size,
                'side': pos.side,
                'whale': pos.whale_address[:16] + '...' if pos.whale_address else None,
                'entry_time': pos.entry_time.isoformat()
            }
            for pos in self.active_positions
        ]
    
    def reset_kill_switch(self):
        """Manually reset kill switch (use with caution)"""
        self.kill_switch_active = False
        self.kill_switch_reason = ""
        print("⚠️ Kill switch manually reset - use with caution!")
