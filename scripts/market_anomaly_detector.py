"""
MARKET-FIRST ANOMALY DETECTOR
==============================
Tutte's recommended approach: Detect market anomalies FIRST, then find whales

Core Principle:
"Market events reveal informed behavior before wallet identities do."

Strategy:
1. Monitor ALL markets for abnormal behavior
2. Detect rapid price moves, volume spikes
3. THEN query who caused the anomaly
4. Evaluate if worth copying

This REPLACES whale-polling with market-watching.
"""

import asyncio
import json
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
import aiohttp


class MarketAnomalyDetector:
    """
    Detect market anomalies FIRST, then find traders
    
    Monitors:
    • Rapid price movements (>2-5% in 30-120s)
    • Volume spikes
    • Large one-sided liquidity removal
    
    When anomaly detected:
    • Query subgraph for recent trades
    • Extract wallet addresses
    • Match against known whales OR discover new ones
    """
    
    def __init__(self):
        self.market_states = {}  # market_id → {price, volume, timestamp}
        self.recent_trades = defaultdict(deque)  # market_id → deque of trades
        self.anomalies_detected = []
        
        # Thresholds (Tutte's recommendations)
        self.price_move_threshold = 0.03  # 3% move in short time
        self.price_move_window = 120  # 2 minutes
        self.volume_spike_multiplier = 3.0  # 3x normal volume
        
    def update_market_state(self, trade: dict):
        """Update market state from incoming trade"""
        
        market_slug = trade.get('slug')
        if not market_slug:
            return
        
        price = float(trade.get('price', 0))
        size = float(trade.get('size', 0))
        timestamp = trade.get('timestamp')
        
        if not market_slug in self.market_states:
            self.market_states[market_slug] = {
                'initial_price': price,
                'current_price': price,
                'last_update': timestamp,
                'recent_volume': 0,
                'trade_count': 0,
                'first_seen': timestamp
            }
        
        state = self.market_states[market_slug]
        
        # Update state
        old_price = state['current_price']
        state['current_price'] = price
        state['last_update'] = timestamp
        state['recent_volume'] += size * price
        state['trade_count'] += 1
        
        # Store recent trade
        self.recent_trades[market_slug].append({
            'price': price,
            'size': size,
            'timestamp': timestamp,
            'wallet': trade.get('proxyWallet'),
            'full_trade': trade
        })
        
        # Keep only recent trades (2 minutes window)
        cutoff = datetime.fromisoformat(timestamp.replace('Z', '+00:00')) - timedelta(seconds=120)
        while self.recent_trades[market_slug]:
            oldest = self.recent_trades[market_slug][0]
            oldest_time = datetime.fromisoformat(oldest['timestamp'].replace('Z', '+00:00'))
            if oldest_time < cutoff:
                self.recent_trades[market_slug].popleft()
            else:
                break
        
        # Detect anomalies
        self.detect_anomalies(market_slug, old_price, price, size, trade)
    
    def detect_anomalies(self, market_slug: str, old_price: float, new_price: float, 
                        trade_size: float, trade: dict):
        """Detect if this trade triggered an anomaly"""
        
        state = self.market_states[market_slug]
        recent = list(self.recent_trades[market_slug])
        
        if len(recent) < 2:
            return  # Need history to detect anomalies
        
        # ANOMALY 1: Rapid Price Move
        price_change = abs(new_price - old_price) / old_price if old_price > 0 else 0
        
        if price_change >= self.price_move_threshold:
            self.handle_anomaly(
                anomaly_type='rapid_price_move',
                market_slug=market_slug,
                details={
                    'old_price': old_price,
                    'new_price': new_price,
                    'change_pct': price_change * 100,
                    'trigger_trade': trade,
                    'recent_trades': recent[-10:]  # Last 10 trades
                }
            )
        
        # ANOMALY 2: Volume Spike
        avg_trade_size = state['recent_volume'] / max(state['trade_count'], 1)
        if trade_size * new_price >= avg_trade_size * self.volume_spike_multiplier:
            self.handle_anomaly(
                anomaly_type='volume_spike',
                market_slug=market_slug,
                details={
                    'trade_value': trade_size * new_price,
                    'avg_trade_value': avg_trade_size,
                    'multiplier': (trade_size * new_price) / max(avg_trade_size, 1),
                    'trigger_trade': trade,
                    'recent_trades': recent[-10:]
                }
            )
        
        # ANOMALY 3: One-Sided Pressure (all trades same direction)
        if len(recent) >= 5:
            last_5 = recent[-5:]
            prices = [t['price'] for t in last_5]
            
            # All increasing or all decreasing
            all_up = all(prices[i] >= prices[i-1] for i in range(1, len(prices)))
            all_down = all(prices[i] <= prices[i-1] for i in range(1, len(prices)))
            
            if all_up or all_down:
                direction = 'UP' if all_up else 'DOWN'
                price_range = (max(prices) - min(prices)) / min(prices) if min(prices) > 0 else 0
                
                if price_range >= 0.02:  # 2% directional move
                    self.handle_anomaly(
                        anomaly_type='one_sided_pressure',
                        market_slug=market_slug,
                        details={
                            'direction': direction,
                            'price_range_pct': price_range * 100,
                            'trade_count': len(last_5),
                            'trigger_trade': trade,
                            'recent_trades': recent[-10:]
                        }
                    )
    
    def handle_anomaly(self, anomaly_type: str, market_slug: str, details: dict):
        """Handle detected anomaly"""
        
        print("\n" + "="*80)
        print(f"🚨 ANOMALY DETECTED: {anomaly_type.upper()}")
        print("="*80)
        print(f"Market: {market_slug[:60]}")
        
        if anomaly_type == 'rapid_price_move':
            print(f"Price Change: {details['old_price']:.4f} → {details['new_price']:.4f}")
            print(f"Change: {details['change_pct']:.2f}%")
        
        elif anomaly_type == 'volume_spike':
            print(f"Trade Value: ${details['trade_value']:,.2f}")
            print(f"Average: ${details['avg_trade_value']:,.2f}")
            print(f"Multiplier: {details['multiplier']:.1f}x")
        
        elif anomaly_type == 'one_sided_pressure':
            print(f"Direction: {details['direction']}")
            print(f"Price Range: {details['price_range_pct']:.2f}%")
            print(f"Trade Count: {details['trade_count']}")
        
        # Extract unique wallets from recent trades
        wallets = set()
        for trade in details['recent_trades']:
            wallet = trade.get('wallet')
            if wallet:
                wallets.add(wallet)
        
        print(f"\nUnique Wallets Involved: {len(wallets)}")
        for wallet in list(wallets)[:5]:
            print(f"  • {wallet[:12]}...")
        
        print()
        print("Next Step: Query these wallets' history to evaluate if worth copying")
        print("="*80)
        print()
        
        # Save anomaly
        anomaly_record = {
            'timestamp': datetime.now().isoformat(),
            'type': anomaly_type,
            'market': market_slug,
            'details': details,
            'wallets_involved': list(wallets)
        }
        self.anomalies_detected.append(anomaly_record)
        self.save_anomalies()
    
    def save_anomalies(self):
        """Save detected anomalies to file"""
        output_file = Path("data/market_anomalies.json")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(self.anomalies_detected, f, indent=2)


# Integration with existing WebSocket watcher
def integrate_anomaly_detector():
    """
    How to integrate with your existing realtime_whale_watcher.py:
    
    1. Add this to your RealtimeWhaleWatcher class:
       
       self.anomaly_detector = MarketAnomalyDetector()
    
    2. In process_trade method, add:
       
       # Before checking if whale/large trade
       self.anomaly_detector.update_market_state(trade)
    
    3. Now you'll detect:
       - Rapid price moves
       - Volume spikes
       - One-sided pressure
       
       BEFORE caring about whale identity!
    
    4. The detector will:
       - Alert on anomalies
       - Show wallets involved
       - Save to data/market_anomalies.json
    
    5. Then you can:
       - Query those wallets' history
       - Decide if worth adding to watchlist
       - Copy their trades (if they pass filters)
    """
    pass


if __name__ == "__main__":
    print(__doc__)
    print(integrate_anomaly_detector.__doc__)
