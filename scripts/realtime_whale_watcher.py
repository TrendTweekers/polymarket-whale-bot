"""
REAL-TIME WHALE WATCHER
=======================
Uses Polymarket's WebSocket feed to detect whale trades INSTANTLY
No more polling - see trades as they happen!

Based on: https://github.com/Polymarket/real-time-data-client
"""

import asyncio
import json
import websockets
import os
import httpx
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from market_anomaly_detector import MarketAnomalyDetector
from dynamic_whale_manager import DynamicWhaleManager

# Load environment variables
load_dotenv()


class RealtimeWhaleWatcher:
    """Watch for whale trades in real-time via WebSocket"""
    
    def __init__(self, whale_addresses: set, min_trade_size: float = 100, enable_telegram: bool = True):
        self.whale_addresses = {addr.lower() for addr in whale_addresses}
        self.min_trade_size = min_trade_size
        self.ws_url = "wss://ws-live-data.polymarket.com"
        self.detected_trades = []
        self.enable_telegram = enable_telegram
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        # Initialize market-first detection and dynamic whale management
        self.anomaly_detector = MarketAnomalyDetector()
        self.whale_manager = DynamicWhaleManager()
        
        # Initialize simulation for Phase 2 data collection
        try:
            import sys
            from pathlib import Path
            # Add project root to path
            project_root = Path(__file__).parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            
            from src.simulation import TradeSimulator
            self.trade_simulator = TradeSimulator()
            self.simulation_enabled = True
            print("✅ Simulation module loaded - Phase 2 data collection ENABLED")
        except ImportError as e:
            self.trade_simulator = None
            self.simulation_enabled = False
            print(f"⚠️ Simulation module not available - data collection disabled: {e}")
        
        # Track stats for hourly summary
        self.trades_processed = 0
        self.whale_trades_detected = 0
        self.simulations_started = 0
        
        if self.enable_telegram and (not self.telegram_bot_token or not self.telegram_chat_id):
            print("⚠️ Telegram credentials not found in .env file")
            print("   Telegram notifications will be DISABLED")
            print("   Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env to enable")
            print()
            self.enable_telegram = False
    
    async def send_telegram(self, message: str):
        """Send Telegram notification"""
        if not self.enable_telegram:
            return
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            
            async with httpx.AsyncClient() as client:
                await client.post(url, json=payload, timeout=5.0)
        except Exception as e:
            print(f"⚠️ Telegram notification failed: {e}")
    
    async def send_hourly_summary(self):
        """Send hourly summary to Telegram (reduces noise)"""
        if not self.enable_telegram:
            return
        
        while True:
            try:
                await asyncio.sleep(3600)  # Wait 1 hour
                
                # Get stats
                whale_stats = self.whale_manager.get_whale_stats()
                
                # Get simulation count
                sim_count = 0
                if self.simulation_enabled and self.trade_simulator:
                    # Count simulations from evaluator if available
                    try:
                        from src.simulation import WhaleEvaluator
                        evaluator = WhaleEvaluator()
                        # This would need to be stored somewhere, for now use counter
                        sim_count = self.simulations_started
                    except:
                        sim_count = self.simulations_started
                
                summary = (
                    f"📊 <b>Hourly Summary</b>\n\n"
                    f"🐋 <b>Whales:</b> {whale_stats['total_whales']} total\n"
                    f"   • High-conf: {whale_stats['high_confidence']}\n"
                    f"   • Active: {whale_stats['active_whales']}\n\n"
                    f"📈 <b>Trades:</b> {self.trades_processed} processed\n"
                    f"   • Whale trades: {self.whale_trades_detected}\n"
                    f"   • Simulations: {sim_count}\n\n"
                    f"🔥 <b>System:</b> Operational\n"
                    f"   • Avg confidence: {whale_stats['avg_confidence']:.1%}"
                )
                
                await self.send_telegram(summary)
                
                # Reset counters for next hour
                self.trades_processed = 0
                self.whale_trades_detected = 0
                
            except Exception as e:
                # Don't let summary errors break the watcher
                print(f"⚠️ Hourly summary error: {e}")
                await asyncio.sleep(60)  # Wait 1 min before retrying
    
    async def connect_and_watch(self):
        """Connect to WebSocket and watch for whale trades"""
        
        print("\n" + "="*80)
        print("🔴 LIVE WHALE WATCHER - Real-Time Feed")
        print("="*80)
        print()
        print(f"Monitoring: {len(self.whale_addresses)} whale addresses")
        print(f"Minimum trade size: ${self.min_trade_size:,.0f}")
        print()
        print("Connecting to Polymarket WebSocket...", flush=True)
        print(flush=True)
        
        reconnect_delay = 5
        max_reconnect_delay = 60
        
        while True:
            try:
                print(f"Connecting to {self.ws_url}...", flush=True)
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=10
                ) as websocket:
                    print("✅ WebSocket connected!")
                    
                    # Subscribe to all trades
                    subscribe_msg = {
                        "action": "subscribe",
                        "subscriptions": [
                            {
                                "topic": "activity",
                                "type": "trades"
                            }
                        ]
                    }
                    
                    await websocket.send(json.dumps(subscribe_msg))
                    print("✅ Subscribed to trade activity!")
                    print("="*80)
                    print("Watching for trades...")
                    print()
                    
                    reconnect_delay = 5  # Reset on successful connection
                    
                    # Start hourly summary task
                    asyncio.create_task(self.send_hourly_summary())
                    
                    # Listen for messages
                    async for message in websocket:
                        await self.handle_message(message)
                        
            except websockets.exceptions.ConnectionClosed as e:
                print(f"\n⚠️ Connection closed: {e}")
                print(f"Reconnecting in {reconnect_delay} seconds...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                
            except websockets.exceptions.WebSocketException as e:
                print(f"\n❌ WebSocket error: {e}")
                print(f"Reconnecting in {reconnect_delay} seconds...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                
            except Exception as e:
                print(f"\n❌ Unexpected error: {e}")
                import traceback
                traceback.print_exc()
                print(f"Reconnecting in {reconnect_delay} seconds...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
    
    async def handle_message(self, message: str):
        """Process incoming trade messages"""
        
        try:
            data = json.loads(message)
            
            # Check if it's a trade message
            if data.get('topic') == 'activity' and data.get('type') == 'trades':
                payload = data.get('payload', {})
                if payload:
                    await self.process_trade(payload)
                
        except json.JSONDecodeError:
            # Not JSON, skip
            pass
        except Exception as e:
            # Only print first few errors to avoid spam
            import traceback
            if not hasattr(self, '_error_count'):
                self._error_count = 0
            self._error_count += 1
            if self._error_count <= 3:
                print(f"⚠️ Error processing message: {e}")
                if self._error_count == 3:
                    print("   (Suppressing further error messages)")
    
    async def process_trade(self, trade: dict):
        """Process a single trade"""
        
        # Extract trade details first (needed for anomaly detector)
        wallet = trade.get('proxyWallet', '').lower()
        size = float(trade.get('size', 0))
        price = float(trade.get('price', 0))
        market_slug = trade.get('slug', 'Unknown')
        timestamp_raw = trade.get('timestamp')
        
        # Fix: Convert Unix timestamp to ISO format if needed
        if isinstance(timestamp_raw, (int, float)):
            # Unix timestamp - convert to ISO format
            timestamp = datetime.fromtimestamp(timestamp_raw).isoformat() + 'Z'
            timestamp_str = timestamp
        elif isinstance(timestamp_raw, str):
            # String timestamp - ensure it has Z suffix
            timestamp = timestamp_raw if timestamp_raw.endswith('Z') else timestamp_raw + 'Z'
            timestamp_str = timestamp
        else:
            # Fallback to current time
            timestamp = datetime.now().isoformat() + 'Z'
            timestamp_str = timestamp
        
        tx_hash = trade.get('transactionHash', '')
        
        # Market-first detection: detect anomalies BEFORE checking whales
        # Pass trade dict with normalized timestamp
        try:
            trade_for_anomaly = trade.copy()
            trade_for_anomaly['timestamp'] = timestamp  # ISO format string
            
            # Update market state with telegram callback for anomaly notifications
            telegram_cb = self.send_telegram if self.enable_telegram else None
            self.anomaly_detector.update_market_state(trade_for_anomaly, telegram_callback=telegram_cb)
        except Exception as e:
            # Log first few errors for debugging, then suppress
            if not hasattr(self, '_anomaly_error_count'):
                self._anomaly_error_count = 0
            self._anomaly_error_count += 1
            if self._anomaly_error_count <= 3:
                print(f"⚠️ Anomaly detector error: {e}")
        
        trade_value = size * price
        
        # Check if it's a whale trade
        is_whale = wallet in self.whale_addresses
        
        # Get whale confidence if it's a monitored whale
        whale_confidence = None
        if is_whale:
            whale_data = self.whale_manager.whales.get(wallet)
            if whale_data:
                whale_confidence = whale_data.get('confidence', 0.0)
            else:
                # Not in dynamic manager yet, check if in static list
                whale_confidence = 0.5  # Default for static list whales
        
        is_large = trade_value >= self.min_trade_size
        self.trades_processed += 1
        
        if is_whale or is_large:
            # Format output
            whale_indicator = "🐋 WHALE" if is_whale else "📊 LARGE"
            
            print(f"{whale_indicator} TRADE DETECTED!")
            print(f"  Wallet: {wallet[:12]}...")
            print(f"  Market: {market_slug[:50]}")
            print(f"  Size: ${trade_value:,.2f} ({size} @ {price})")
            print(f"  Time: {timestamp}")
            if is_whale:
                print(f"  ✅ This is one of your monitored whales!")
            print()
            
            # Send Telegram notification for high-confidence whales (≥65%)
            # Lowered from 70% to 65% to catch more monitored whale trades
            if is_whale and whale_confidence and whale_confidence >= 0.65:
                self.whale_trades_detected += 1
                
                telegram_msg = (
                    f"🐋 <b>HIGH-CONFIDENCE WHALE TRADE</b>\n\n"
                    f"<b>Wallet:</b> <code>{wallet[:16]}...</code>\n"
                    f"<b>Confidence:</b> {whale_confidence:.0%}\n"
                    f"<b>Market:</b> {market_slug[:80]}\n"
                    f"<b>Size:</b> ${trade_value:,.2f}\n"
                    f"<b>Price:</b> {price:.2%}\n"
                    f"<b>Time:</b> {timestamp[:19]}\n\n"
                    f"✅ High-confidence whale (≥65%)\n\n"
                    f"<i>[Real-Time Detection]</i>"
                )
                await self.send_telegram(telegram_msg)
                
                # Start simulation for high-confidence whales (Phase 2 data collection)
                if self.simulation_enabled and self.trade_simulator:
                    try:
                        # Parse timestamp to datetime for simulator
                        if isinstance(timestamp_raw, (int, float)):
                            trade_datetime = datetime.fromtimestamp(timestamp_raw)
                        elif isinstance(timestamp_raw, str):
                            if 'T' in timestamp_raw:
                                trade_datetime = datetime.fromisoformat(timestamp_raw.replace('Z', '+00:00'))
                            else:
                                trade_datetime = datetime.fromtimestamp(float(timestamp_raw))
                        else:
                            trade_datetime = datetime.now()
                        
                        # Start simulation in background (non-blocking)
                        asyncio.create_task(
                            self.trade_simulator.simulate_trade({
                                'wallet': wallet,
                                'market': market_slug,
                                'price': price,
                                'size': size,
                                'timestamp': trade_datetime
                            })
                        )
                        self.simulations_started += 1
                    except Exception as e:
                        # Don't let simulation errors break trade processing
                        if not hasattr(self, '_sim_error_count'):
                            self._sim_error_count = 0
                        self._sim_error_count += 1
                        if self._sim_error_count <= 3:
                            print(f"⚠️ Simulation error: {e}")
            
            # REMOVED: Large trade notifications (>$1000) - was causing spam
            # Now only high-confidence whales trigger notifications
            
            # Update dynamic whale manager for large trades
            if is_large:
                self.whale_manager.add_or_update_whale(
                    wallet=wallet,
                    market=market_slug,
                    trade_value=trade_value,
                    source='large_trade'
                )
            
            # Save trade
            trade_record = {
                'timestamp': timestamp,
                'wallet': wallet,
                'market': market_slug,
                'size': size,
                'price': price,
                'value': trade_value,
                'is_monitored_whale': is_whale,
                'whale_confidence': whale_confidence if is_whale else None,  # Save confidence for analysis
                'tx_hash': tx_hash
            }
            self.detected_trades.append(trade_record)
            
            # Save to file
            self.save_trades()
    
    def save_trades(self):
        """Save detected trades to file"""
        output_file = Path("data/realtime_whale_trades.json")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(self.detected_trades, f, indent=2)


async def load_whale_addresses():
    """Load whale addresses from config"""
    
    config_file = Path("config/whale_list.json")
    
    if not config_file.exists():
        print("❌ No whale config found at config/whale_list.json")
        return set()
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    addresses = {whale.get('address') for whale in config.get('whales', []) 
                 if whale.get('address')}
    
    return addresses


async def main():
    """Main entry point"""
    
    import sys
    sys.stdout.flush()
    
    print("\n🐋 REAL-TIME WHALE WATCHER", flush=True)
    print(flush=True)
    print("This connects to Polymarket's WebSocket feed to see:", flush=True)
    print("  • ALL trades in real-time", flush=True)
    print("  • When your whales trade (instant notification)", flush=True)
    print("  • Large trades from anyone (>$100)", flush=True)
    print(flush=True)
    print("Based on Polymarket's real-time-data-client repository", flush=True)
    print(flush=True)
    
    # Load whale addresses
    print("Loading your whale addresses...", flush=True)
    whale_addresses = await load_whale_addresses()
    
    if not whale_addresses:
        print("⚠️ No whale addresses loaded. Will only show large trades.")
        whale_addresses = set()
    else:
        print(f"✅ Loaded {len(whale_addresses)} whale addresses")
    
    print()
    
    # Check Telegram config
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    if bot_token and chat_id:
        print("✅ Telegram notifications ENABLED")
        print("   You'll receive notifications on Telegram for whale trades!")
    else:
        print("⚠️ Telegram notifications DISABLED")
        print("   Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env to enable")
    
    print()
    print("Starting watcher...")
    print()
    
    # Create watcher
    watcher = RealtimeWhaleWatcher(whale_addresses, min_trade_size=100)
    
    # Start watching
    try:
        await watcher.connect_and_watch()
    except KeyboardInterrupt:
        print()
        print("="*80)
        print("⏹️ STOPPED")
        print("="*80)
        print()
        print(f"Total trades detected: {len(watcher.detected_trades)}")
        print(f"Saved to: data/realtime_whale_trades.json")


if __name__ == "__main__":
    asyncio.run(main())
