"""
Trade Database - Persistent storage for all trades and stats
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import structlog

log = structlog.get_logger()


class TradeDatabase:
    """
    Stores all trades, evaluations, and performance data
    """
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.trades_file = self.data_dir / "trades.json"
        self.stats_file = self.data_dir / "statistics.json"
        self.daily_log_file = self.data_dir / "daily_logs.json"
        
        self.trades = self.load_trades()
        self.stats = self.load_stats()
        
        log.info("trade_database_initialized",
                total_trades=len(self.trades),
                data_dir=str(self.data_dir))
    
    def load_trades(self) -> List[Dict]:
        """Load all historical trades"""
        try:
            if self.trades_file.exists():
                with open(self.trades_file, 'r') as f:
                    return json.load(f)
            return []
        except Exception as e:
            log.error("trades_load_error", error=str(e))
            return []
    
    def save_trades(self):
        """Persist trades to disk"""
        try:
            with open(self.trades_file, 'w') as f:
                json.dump(self.trades, f, indent=2, default=str)
            log.debug("trades_saved", count=len(self.trades))
        except Exception as e:
            log.error("trades_save_error", error=str(e))
    
    def load_stats(self) -> Dict:
        """Load statistics"""
        try:
            if self.stats_file.exists():
                with open(self.stats_file, 'r') as f:
                    return json.load(f)
            return self.init_stats()
        except Exception as e:
            log.error("stats_load_error", error=str(e))
            return self.init_stats()
    
    def init_stats(self) -> Dict:
        """Initialize empty stats"""
        return {
            'total_trades': 0,
            'completed_trades': 0,
            'active_trades': 0,
            'wins': 0,
            'losses': 0,
            'total_pnl': 0.0,
            'total_volume': 0.0,
            'win_rate': 0.0,
            'avg_pnl': 0.0,
            'best_trade': 0.0,
            'worst_trade': 0.0,
            'total_duration_days': 0,
            'avg_duration_days': 0.0,
            'last_updated': datetime.now().isoformat(),
            'whales_tracked': {},
            'strategies_performance': {},
            'daily_stats': []
        }
    
    def save_stats(self):
        """Persist stats to disk"""
        try:
            self.stats['last_updated'] = datetime.now().isoformat()
            with open(self.stats_file, 'w') as f:
                json.dump(self.stats, f, indent=2, default=str)
            log.debug("stats_saved")
        except Exception as e:
            log.error("stats_save_error", error=str(e))
    
    def add_trade(self, trade_record: Dict):
        """Add new trade to database"""
        self.trades.append(trade_record)
        self.stats['total_trades'] += 1
        self.stats['active_trades'] += 1
        self.stats['total_volume'] += trade_record.get('position_size', 0)
        
        # Track by whale
        whale_id = trade_record.get('whale_id', 'unknown')
        if whale_id not in self.stats['whales_tracked']:
            self.stats['whales_tracked'][whale_id] = {
                'trades': 0,
                'wins': 0,
                'pnl': 0.0
            }
        self.stats['whales_tracked'][whale_id]['trades'] += 1
        
        self.save_trades()
        self.save_stats()
        
        log.info("trade_added_to_database",
                trade_id=trade_record['trade_id'],
                total_trades=self.stats['total_trades'])
    
    def update_trade_outcome(self, trade_id: str, outcome: bool, pnl: float):
        """Update trade with result"""
        # Find and update trade
        for trade in self.trades:
            if trade['trade_id'] == trade_id:
                trade['status'] = 'completed'
                trade['outcome'] = 'win' if outcome else 'loss'
                trade['pnl'] = pnl
                trade['closed_at'] = datetime.now().isoformat()
                
                # Calculate duration
                opened = datetime.fromisoformat(trade['timestamp'])
                closed = datetime.fromisoformat(trade['closed_at'])
                duration_days = (closed - opened).days
                trade['duration_days'] = duration_days
                
                # Update stats
                self.stats['completed_trades'] += 1
                self.stats['active_trades'] -= 1
                self.stats['total_pnl'] += pnl
                self.stats['total_duration_days'] += duration_days
                
                if outcome:
                    self.stats['wins'] += 1
                else:
                    self.stats['losses'] += 1
                
                # Update best/worst
                if pnl > self.stats.get('best_trade', 0):
                    self.stats['best_trade'] = pnl
                if pnl < self.stats.get('worst_trade', 0):
                    self.stats['worst_trade'] = pnl
                
                # Calculate averages
                if self.stats['completed_trades'] > 0:
                    self.stats['win_rate'] = self.stats['wins'] / self.stats['completed_trades']
                    self.stats['avg_pnl'] = self.stats['total_pnl'] / self.stats['completed_trades']
                    self.stats['avg_duration_days'] = self.stats['total_duration_days'] / self.stats['completed_trades']
                
                # Update whale stats
                whale_id = trade.get('whale_id', 'unknown')
                if whale_id in self.stats['whales_tracked']:
                    if outcome:
                        self.stats['whales_tracked'][whale_id]['wins'] += 1
                    self.stats['whales_tracked'][whale_id]['pnl'] += pnl
                
                self.save_trades()
                self.save_stats()
                
                log.info("trade_outcome_recorded",
                        trade_id=trade_id,
                        outcome='WIN' if outcome else 'LOSS',
                        pnl=pnl,
                        win_rate=self.stats['win_rate'])
                
                return
        
        log.warning("trade_not_found_in_database", trade_id=trade_id)
    
    def get_recent_trades(self, n: int = 20) -> List[Dict]:
        """Get N most recent trades"""
        return sorted(self.trades, key=lambda x: x['timestamp'], reverse=True)[:n]
    
    def get_active_trades(self) -> List[Dict]:
        """Get all active trades"""
        return [t for t in self.trades if t.get('status') == 'active']
    
    def get_completed_trades(self) -> List[Dict]:
        """Get all completed trades"""
        return [t for t in self.trades if t.get('status') == 'completed']
    
    def get_stats_summary(self) -> Dict:
        """Get comprehensive stats summary"""
        active = self.get_active_trades()
        completed = self.get_completed_trades()
        
        return {
            'overview': {
                'total_trades': len(self.trades),
                'active_trades': len(active),
                'completed_trades': len(completed),
                'win_rate': f"{self.stats.get('win_rate', 0):.1%}",
                'total_pnl': f"${self.stats.get('total_pnl', 0):+,.2f}",
                'avg_pnl': f"${self.stats.get('avg_pnl', 0):+,.2f}",
            },
            'performance': {
                'wins': self.stats.get('wins', 0),
                'losses': self.stats.get('losses', 0),
                'best_trade': f"${self.stats.get('best_trade', 0):+,.2f}",
                'worst_trade': f"${self.stats.get('worst_trade', 0):+,.2f}",
                'avg_duration': f"{self.stats.get('avg_duration_days', 0):.1f} days",
            },
            'volume': {
                'total_volume': f"${self.stats.get('total_volume', 0):,.2f}",
                'avg_position_size': f"${self.stats.get('total_volume', 0) / max(len(self.trades), 1):,.2f}",
            },
            'whales': self.stats.get('whales_tracked', {}),
            'recent_trades': self.get_recent_trades(5),
            'last_updated': self.stats.get('last_updated', 'Never')
        }
    
    def log_daily_summary(self):
        """Save daily summary snapshot"""
        try:
            daily_logs = []
            if self.daily_log_file.exists():
                with open(self.daily_log_file, 'r') as f:
                    daily_logs = json.load(f)
            
            # Add today's snapshot
            daily_logs.append({
                'date': datetime.now().date().isoformat(),
                'stats': self.stats.copy()
            })
            
            # Keep last 90 days
            daily_logs = daily_logs[-90:]
            
            with open(self.daily_log_file, 'w') as f:
                json.dump(daily_logs, f, indent=2, default=str)
            
            log.info("daily_summary_logged")
        
        except Exception as e:
            log.error("daily_summary_error", error=str(e))
