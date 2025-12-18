"""
Market Context Filter - Ensures whale is competent in this market type
"""

from typing import Dict, Tuple
import structlog

log = structlog.get_logger()


class MarketContextFilter:
    """
    Filter markets based on whale specialty and market characteristics
    """
    
    def __init__(self, config: Dict):
        self.min_liquidity = config.get('min_liquidity', 10000)
        self.max_spread = config.get('max_spread', 0.05)
        self.min_volume_24h = config.get('min_volume_24h', 5000)
        
        log.info("market_context_filter_initialized",
                min_liquidity=self.min_liquidity,
                max_spread=self.max_spread,
                min_volume_24h=self.min_volume_24h)
    
    def check_market_quality(self, market_data: Dict) -> Tuple[bool, str]:
        """
        Check if market has sufficient liquidity and quality
        """
        
        # Check liquidity
        liquidity = market_data.get('liquidity', 0)
        if liquidity < self.min_liquidity:
            return False, f"Insufficient liquidity: ${liquidity} (min ${self.min_liquidity})"
        
        # Check spread
        bid = market_data.get('best_bid', 0)
        ask = market_data.get('best_ask', 1)
        spread = ask - bid
        
        if spread > self.max_spread:
            return False, f"Spread too wide: {spread:.2%} (max {self.max_spread:.2%})"
        
        # Check volume
        volume_24h = market_data.get('volume_24h', 0)
        if volume_24h < self.min_volume_24h:
            return False, f"Volume too low: ${volume_24h} (min ${self.min_volume_24h})"
        
        return True, "Market quality sufficient"
    
    def check_whale_specialty(self, whale_data: Dict, market_category: str) -> Tuple[bool, float, str]:
        """
        Check if whale has proven competency in this market category
        """
        
        # Get whale's specialty scores
        specialty_scores = whale_data.get('specialty_scores', {})
        category_score = specialty_scores.get(market_category, 0.5)
        
        # Require >55% win rate in category
        if category_score < 0.55:
            return False, category_score, f"Weak in {market_category}: {category_score:.2%}"
        
        # Good specialty
        if category_score >= 0.65:
            return True, category_score, f"Strong in {market_category}: {category_score:.2%}"
        
        # Acceptable
        return True, category_score, f"Acceptable in {market_category}: {category_score:.2%}"
    
    def check_whale_market_fit(self, whale_data: Dict, market_data: Dict) -> Tuple[bool, str]:
        """
        Comprehensive check: does this whale + market combination make sense?
        """
        
        market_category = market_data.get('category', 'unknown')
        
        # Check 1: Market quality
        quality_ok, quality_reason = self.check_market_quality(market_data)
        if not quality_ok:
            return False, quality_reason
        
        # Check 2: Whale specialty
        specialty_ok, specialty_score, specialty_reason = self.check_whale_specialty(
            whale_data, market_category
        )
        if not specialty_ok:
            return False, specialty_reason
        
        # Check 3: Whale's typical position size vs market size
        avg_whale_size = whale_data.get('avg_bet_size', 0)
        market_liquidity = market_data.get('liquidity', 0)
        
        # Whale shouldn't be too big for market (would move it too much)
        if avg_whale_size > market_liquidity * 0.2:
            return False, f"Whale too big for market (${avg_whale_size} vs ${market_liquidity} liquidity)"
        
        return True, f"Good fit: {specialty_reason}"
