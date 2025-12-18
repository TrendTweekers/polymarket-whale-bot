"""
Velocity Filter - Enforces 1-5 day resolution constraint
"""

from datetime import datetime, timedelta
from typing import Dict, Tuple
import structlog

log = structlog.get_logger()


class VelocityFilter:
    """
    Hard filter: only allow markets that resolve in 1-5 days
    Ensures high capital turnover
    """
    
    def __init__(self, min_days: int = 1, max_days: int = 5, preferred_days: int = 3):
        self.min_days = min_days
        self.max_days = max_days
        self.preferred_days = preferred_days
        
        log.info("velocity_filter_initialized",
                min_days=min_days,
                max_days=max_days,
                preferred_days=preferred_days)
    
    def check_market(self, market_data: Dict) -> Tuple[bool, float, str]:
        """
        Check if market meets velocity requirements
        Returns: (passes, score, reason)
        """
        
        # Calculate days to resolution
        if 'end_date' in market_data:
            if isinstance(market_data['end_date'], str):
                end_date = datetime.fromisoformat(market_data['end_date'].replace('Z', '+00:00'))
            else:
                end_date = market_data['end_date']
            
            days_to_resolution = (end_date - datetime.now()).days
        elif 'days_until_resolution' in market_data:
            days_to_resolution = market_data['days_until_resolution']
        else:
            return False, 0.0, "Missing resolution date"
        
        # Check bounds
        if days_to_resolution < self.min_days:
            return False, 0.0, f"Resolves too soon: {days_to_resolution} days (min {self.min_days})"
        
        if days_to_resolution > self.max_days:
            return False, 0.0, f"Resolves too late: {days_to_resolution} days (max {self.max_days})"
        
        # Calculate score based on proximity to preferred duration
        if days_to_resolution <= self.preferred_days:
            # Perfect range: 1-3 days
            score = 1.0
            reason = f"Optimal: {days_to_resolution} days"
        else:
            # 3-5 days: linear decay
            score = 0.8 - ((days_to_resolution - self.preferred_days) / (self.max_days - self.preferred_days)) * 0.3
            reason = f"Acceptable: {days_to_resolution} days"
        
        log.debug("velocity_filter_check",
                 market_id=market_data.get('market_id'),
                 days=days_to_resolution,
                 score=f"{score:.2f}",
                 passed=True)
        
        return True, score, reason
    
    def get_ideal_markets(self, markets: list) -> list:
        """
        Filter and rank markets by velocity score
        """
        scored_markets = []
        
        for market in markets:
            passes, score, reason = self.check_market(market)
            if passes:
                scored_markets.append({
                    'market': market,
                    'velocity_score': score,
                    'reason': reason
                })
        
        # Sort by score (highest first)
        scored_markets.sort(key=lambda x: x['velocity_score'], reverse=True)
        
        log.info("velocity_filter_results",
                total_markets=len(markets),
                passed=len(scored_markets),
                rejected=len(markets) - len(scored_markets))
        
        return scored_markets
