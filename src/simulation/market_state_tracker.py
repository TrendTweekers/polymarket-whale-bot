"""
Market State Tracker
====================
Tracks market prices at different points in time

Records:
- Price at detection time
- Price at +1min, +3min, +5min delays
- Historical price movements
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from collections import defaultdict
import aiohttp


class MarketStateTracker:
    """
    Track market state at different timestamps
    
    Used to simulate: "What was the price 3 minutes after detection?"
    """
    
    def __init__(self):
        # In-memory cache: market_slug -> list of (timestamp, price) tuples
        self.price_history = defaultdict(list)
        
        # API client for fetching historical prices
        self.api_base = "https://gamma-api.polymarket.com"
    
    async def record_state(
        self,
        market_slug: str,
        timestamp: datetime,
        price: float,
        additional_data: Dict = None
    ):
        """
        Record market state at a specific time
        
        Args:
            market_slug: Market identifier
            timestamp: When this state was recorded
            price: Market price at this time
            additional_data: Additional market data (optional)
        """
        state = {
            'timestamp': timestamp,
            'price': price,
            'data': additional_data or {}
        }
        
        self.price_history[market_slug].append(state)
        
        # Keep only recent history (last 24 hours)
        cutoff = datetime.now() - timedelta(hours=24)
        self.price_history[market_slug] = [
            s for s in self.price_history[market_slug]
            if s['timestamp'] > cutoff
        ]
        
        # Sort by timestamp
        self.price_history[market_slug].sort(key=lambda x: x['timestamp'])
    
    async def get_state_at_time(
        self,
        market_slug: str,
        timestamp: datetime
    ) -> Optional[Dict]:
        """
        Get market state at a specific time
        
        Args:
            market_slug: Market identifier
            timestamp: Target time
        
        Returns:
            Dict: Market state at that time, or None if not found
        """
        history = self.price_history.get(market_slug, [])
        
        if not history:
            # Try to fetch from API
            return await self._fetch_state_from_api(market_slug, timestamp)
        
        # Find closest recorded state
        closest = None
        min_diff = timedelta.max
        
        for state in history:
            diff = abs(state['timestamp'] - timestamp)
            if diff < min_diff:
                min_diff = diff
                closest = state
        
        # If within 30 seconds, return it
        if closest and min_diff < timedelta(seconds=30):
            return {
                'price': closest['price'],
                'timestamp': closest['timestamp'],
                'data': closest.get('data', {})
            }
        
        # Otherwise try API
        return await self._fetch_state_from_api(market_slug, timestamp)
    
    async def get_latest_state(self, market_slug: str) -> Optional[Dict]:
        """Get most recent recorded state for a market"""
        history = self.price_history.get(market_slug, [])
        if history:
            latest = history[-1]
            return {
                'price': latest['price'],
                'timestamp': latest['timestamp'],
                'data': latest.get('data', {})
            }
        return None
    
    async def _fetch_state_from_api(
        self,
        market_slug: str,
        timestamp: datetime
    ) -> Optional[Dict]:
        """
        Fetch market state from API (fallback)
        
        TODO: Implement API call to get historical price
        For now, returns None
        """
        # This will be implemented when we have historical price API
        return None
    
    async def get_price_at_delay(
        self,
        market_slug: str,
        base_time: datetime,
        delay_seconds: int
    ) -> Optional[float]:
        """
        Get price at a specific delay from base time
        
        Args:
            market_slug: Market identifier
            base_time: Starting time
            delay_seconds: Delay in seconds
        
        Returns:
            float: Price at that time, or None
        """
        target_time = base_time + timedelta(seconds=delay_seconds)
        state = await self.get_state_at_time(market_slug, target_time)
        return state.get('price') if state else None
