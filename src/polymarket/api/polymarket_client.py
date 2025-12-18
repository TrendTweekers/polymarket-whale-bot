"""
Polymarket API Client - Handles all API interactions
"""

import aiohttp
import asyncio
from typing import Dict, List, Optional
from datetime import datetime
import structlog

log = structlog.get_logger()


class PolymarketClient:
    """
    Async client for Polymarket API
    """
    
    def __init__(self, config: Dict):
        self.clob_endpoint = config.get('clob_endpoint', 'https://clob.polymarket.com')
        self.gamma_endpoint = config.get('gamma_endpoint', 'https://gamma-api.polymarket.com')
        self.chain_id = config.get('chain_id', 137)
        self.session: Optional[aiohttp.ClientSession] = None
        
        log.info("polymarket_client_initialized",
                clob=self.clob_endpoint,
                gamma=self.gamma_endpoint)
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_markets(self, limit: int = 100) -> List[Dict]:
        """
        Fetch active markets from Gamma API
        """
        try:
            url = f"{self.gamma_endpoint}/markets"
            params = {'limit': limit, 'active': True}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    markets = data if isinstance(data, list) else data.get('markets', [])
                    
                    log.info("markets_fetched", count=len(markets))
                    return markets
                else:
                    log.error("markets_fetch_failed", status=response.status)
                    return []
        
        except Exception as e:
            log.error("markets_fetch_error", error=str(e))
            return []
    
    async def get_market_details(self, market_id: str) -> Optional[Dict]:
        """
        Get detailed info for specific market
        """
        try:
            url = f"{self.gamma_endpoint}/markets/{market_id}"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    log.error("market_details_failed", market_id=market_id, status=response.status)
                    return None
        
        except Exception as e:
            log.error("market_details_error", market_id=market_id, error=str(e))
            return None
    
    async def get_orderbook(self, token_id: str) -> Optional[Dict]:
        """
        Get order book for a specific token
        """
        try:
            url = f"{self.clob_endpoint}/book"
            params = {'token_id': token_id}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    log.error("orderbook_fetch_failed", token_id=token_id, status=response.status)
                    return None
        
        except Exception as e:
            log.error("orderbook_fetch_error", token_id=token_id, error=str(e))
            return None
    
    async def get_recent_trades(self, market_id: str, limit: int = 50) -> List[Dict]:
        """
        Get recent trades for a market
        """
        try:
            url = f"{self.gamma_endpoint}/markets/{market_id}/trades"
            params = {'limit': limit}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data if isinstance(data, list) else data.get('trades', [])
                else:
                    log.error("trades_fetch_failed", market_id=market_id, status=response.status)
                    return []
        
        except Exception as e:
            log.error("trades_fetch_error", market_id=market_id, error=str(e))
            return []
    
    async def monitor_whale_wallets(self, whale_addresses: List[str]) -> List[Dict]:
        """
        Monitor specific wallet addresses for new positions
        This is a simplified version - in production you'd use WebSocket or Polygon blockchain monitoring
        """
        whale_activities = []
        
        for address in whale_addresses:
            try:
                # In production, use Polygon blockchain API or subgraph
                # This is placeholder logic
                url = f"{self.gamma_endpoint}/positions"
                params = {'address': address, 'limit': 10}
                
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        positions = await response.json()
                        if positions:
                            whale_activities.append({
                                'address': address,
                                'positions': positions,
                                'timestamp': datetime.now().isoformat()
                            })
            
            except Exception as e:
                log.error("whale_monitor_error", address=address, error=str(e))
                continue
        
        return whale_activities
    
    async def get_market_price(self, token_id: str) -> Optional[float]:
        """
        Get current market price for a token
        """
        try:
            url = f"{self.clob_endpoint}/price"
            params = {'token_id': token_id, 'side': 'BUY'}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return float(data.get('price', 0))
                else:
                    return None
        
        except Exception as e:
            log.error("price_fetch_error", token_id=token_id, error=str(e))
            return None
    
    async def simulate_order(self, token_id: str, side: str, amount: float) -> Dict:
        """
        Simulate an order to check expected fill
        """
        try:
            # Get order book
            orderbook = await self.get_orderbook(token_id)
            
            if not orderbook:
                return {'success': False, 'reason': 'No orderbook data'}
            
            # Calculate expected price and slippage
            orders = orderbook.get('asks' if side == 'BUY' else 'bids', [])
            
            total_cost = 0
            filled_amount = 0
            
            for order in orders:
                price = float(order['price'])
                size = float(order['size'])
                
                fill = min(size, amount - filled_amount)
                total_cost += fill * price
                filled_amount += fill
                
                if filled_amount >= amount:
                    break
            
            avg_price = total_cost / filled_amount if filled_amount > 0 else 0
            
            return {
                'success': True,
                'avg_price': avg_price,
                'filled_amount': filled_amount,
                'total_cost': total_cost,
                'slippage': (avg_price - float(orders[0]['price'])) / float(orders[0]['price']) if orders else 0
            }
        
        except Exception as e:
            log.error("order_simulation_error", error=str(e))
            return {'success': False, 'reason': str(e)}
