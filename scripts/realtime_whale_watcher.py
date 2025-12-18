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
                await self.process_trade(data.get('payload', {}))
                
        except json.JSONDecodeError:
            # Not JSON, skip
            pass
        except Exception as e:
            print(f"⚠️ Error processing message: {e}")
    
    async def process_trade(self, trade: dict):
        """Process a single trade"""
        
        # Extract trade details
        wallet = trade.get('proxyWallet', '').lower()
        size = float(trade.get('size', 0))
        price = float(trade.get('price', 0))
        market_slug = trade.get('slug', 'Unknown')
        timestamp = trade.get('timestamp', datetime.now().isoformat())
        tx_hash = trade.get('transactionHash', '')
        
        trade_value = size * price
        
        # Check if it's a whale trade
        is_whale = wallet in self.whale_addresses
        is_large = trade_value >= self.min_trade_size
        
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
            
            # Send Telegram notification for whale trades
            if is_whale:
                telegram_msg = (
                    f"🐋 <b>WHALE TRADE DETECTED!</b>\n\n"
                    f"<b>Wallet:</b> <code>{wallet[:16]}...</code>\n"
                    f"<b>Market:</b> {market_slug[:80]}\n"
                    f"<b>Size:</b> ${trade_value:,.2f}\n"
                    f"<b>Price:</b> {price:.2%}\n"
                    f"<b>Time:</b> {timestamp[:19]}\n\n"
                    f"✅ This is one of your monitored whales!\n\n"
                    f"<i>[Real-Time Detection - Testing Mode]</i>"
                )
                await self.send_telegram(telegram_msg)
            
            # Save trade
            trade_record = {
                'timestamp': timestamp,
                'wallet': wallet,
                'market': market_slug,
                'size': size,
                'price': price,
                'value': trade_value,
                'is_monitored_whale': is_whale,
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
