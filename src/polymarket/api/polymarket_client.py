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
    
    async def get_wallet_positions(self, wallet_address: str) -> Dict:
        """
        Get current positions for a wallet using Polymarket's Subgraph
        """
        try:
            # Use the official Polymarket subgraph
            subgraph_url = "https://api.thegraph.com/subgraphs/name/polymarket/matic-markets-5"
            
            # GraphQL query to get user positions
            query = """
            query UserPositions($user: String!) {
                user(id: $user) {
                    userPositions {
                        id
                        market {
                            id
                            question
                            endDate
                            liquidityParameter
                        }
                        outcome
                        quantityBought
                        quantitySold
                        netQuantity
                        avgBuyPrice
                        avgSellPrice
                        totalBuyVolume
                        totalSellVolume
                    }
                }
            }
            """
            
            variables = {
                "user": wallet_address.lower()
            }
            
            async with self.session.post(
                subgraph_url,
                json={'query': query, 'variables': variables}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if 'data' not in data or data['data']['user'] is None:
                        log.debug("wallet_has_no_positions", wallet=wallet_address[:10])
                        return {'wallet': wallet_address, 'positions': []}
                    
                    positions = data['data']['user']['userPositions']
                    
                    # Filter for open positions only (netQuantity > 0)
                    open_positions = [
                        p for p in positions 
                        if float(p.get('netQuantity', 0)) > 0
                    ]
                    
                    log.debug("wallet_positions_fetched",
                            wallet=wallet_address[:10],
                            total_positions=len(positions),
                            open_positions=len(open_positions))
                    
                    return {
                        'wallet': wallet_address,
                        'positions': open_positions,
                        'timestamp': datetime.now().isoformat()
                    }
                else:
                    log.error("positions_fetch_failed",
                            wallet=wallet_address,
                            status=response.status)
                    return {'wallet': wallet_address, 'positions': []}
        
        except Exception as e:
            log.error("positions_fetch_error", wallet=wallet_address, error=str(e))
            return {'wallet': wallet_address, 'positions': []}
    
    async def detect_whale_trades(self, wallet_address: str, 
                                 previous_positions: Dict) -> List[Dict]:
        """
        Compare current vs previous positions to detect new trades
        """
        current = await self.get_wallet_positions(wallet_address)
        new_trades = []
        
        # Build current positions dict
        current_pos_dict = {
            pos['market']['id']: pos for pos in current['positions']
        }
        
        previous_pos_dict = previous_positions.get('positions_dict', {})
        
        # Check for new or increased positions
        for market_id, pos in current_pos_dict.items():
            old_pos = previous_pos_dict.get(market_id, {})
            old_qty = float(old_pos.get('netQuantity', 0))
            new_qty = float(pos.get('netQuantity', 0))
            
            # New trade or position increase
            if new_qty > old_qty:
                trade_size_qty = new_qty - old_qty
                avg_price = float(pos.get('avgBuyPrice', 0.5))
                trade_size_usd = trade_size_qty * avg_price
                
                # Only track significant trades (>$1000)
                if trade_size_usd > 1000:
                    new_trades.append({
                        'whale_address': wallet_address,
                        'market_id': market_id,
                        'direction': pos['outcome'],
                        'size': trade_size_usd,
                        'quantity': trade_size_qty,
                        'price': avg_price,
                        'timestamp': datetime.now().isoformat(),
                        'market_data': {
                            'market_id': market_id,
                            'question': pos['market'].get('question', 'Unknown'),
                            'end_date': pos['market'].get('endDate', None),
                            'liquidity': float(pos['market'].get('liquidityParameter', 0))
                        }
                    })
                    
                    log.info("new_whale_trade_detected",
                            wallet=wallet_address[:10],
                            market=market_id[:10],
                            size_usd=trade_size_usd,
                            outcome=pos['outcome'])
        
        return new_trades
    
    async def monitor_whale_wallets(self, whale_addresses: List[str]) -> List[Dict]:
        """
        Monitor specific wallet addresses for new positions
        Uses real Polymarket Gamma API
        """
        whale_activities = []
        for address in whale_addresses:
            try:
                positions_data = await self.get_wallet_positions(address)
                if positions_data.get('positions'):
                    whale_activities.append({
                        'address': address,
                        'positions': positions_data['positions'],
                        'timestamp': positions_data['timestamp']
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
