#!/usr/bin/env python3
"""
Paper Trading System for Top 3 Elite Whales
Real-time validation of Phase 2 analysis (no real money)
"""
import json
import asyncio
import websockets
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
import httpx
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

class PaperTrader:
    def __init__(self, delay_seconds=60, telegram_notifications=True):
        """Initialize paper trading system"""
        
        # Configure Telegram mode
        self.telegram_notifications = telegram_notifications
        
        # Load top 3 whales from Phase 2 analysis (only >50% win rate)
        try:
            with open('data/phase2_analysis_results.json', 'r') as f:
                results = json.load(f)
            
            # Only monitor whales with >50% win rate
            profitable_whales = [
                w for w in results['top_5_whales']
                if w.get('win_rate_1min', 0) > 50
            ]
            
            # Take top 3 profitable whales
            self.target_whales = {
                w['address'].lower() 
                for w in profitable_whales[:3]
            }
            
            # Store whale metadata
            self.whale_metadata = {
                w['address'].lower(): w
                for w in profitable_whales[:3]
            }
            
            print("=" * 80)
            print("📊 PAPER TRADING SYSTEM")
            print("=" * 80)
            print(f"\n✅ Monitoring {len(self.target_whales)} elite whales:")
            for i, whale in enumerate(self.target_whales, 1):
                meta = self.whale_metadata.get(whale, {})
                print(f"   {i}. {whale[:42]}")
                print(f"      Win Rate: {meta.get('win_rate_1min', 0):.1f}%")
                print(f"      Delay Cost: {meta.get('avg_delay_cost_1min', 0):+.2%}")
                print(f"      Simulations: {meta.get('simulations', 0)}")
        except FileNotFoundError:
            print("❌ Phase 2 analysis results not found!")
            print("   Run: python scripts/phase2_brutal_filtering.py")
            raise
        
        self.delay_seconds = delay_seconds  # 1-minute delay
        self.trades = []
        self.positions = {}  # {position_id: position_data}
        self.pending_entries = {}  # {trade_id: entry_data}
        
        # Load existing trades if any
        self.trades_file = Path('data/paper_trades.json')
        self.load_trades()
        
        # Telegram config
        self.telegram_enabled = False
        if self.telegram_notifications:
            try:
                import os
                self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
                self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
                self.telegram_enabled = bool(self.telegram_bot_token and self.telegram_chat_id)
                
                if self.telegram_enabled:
                    print("\n📱 Telegram: PAPER TRADING MODE")
                    print("   ✅ Paper trades recorded")
                    print("   ✅ Daily summaries")
                    print("   ✅ Critical errors")
                    print("   ❌ Regular whale monitoring")
                    print("   ❌ Simulation updates")
                    print("   ❌ Hourly summaries")
            except:
                pass
        
        print(f"\n📈 Paper Trading Stats:")
        print(f"   Total trades: {len(self.trades)}")
        print(f"   Open positions: {len([t for t in self.trades if t.get('status') == 'open'])}")
        print()
    
    def load_trades(self):
        """Load existing paper trades"""
        if self.trades_file.exists():
            try:
                with open(self.trades_file, 'r') as f:
                    self.trades = json.load(f)
            except:
                self.trades = []
        else:
            self.trades = []
    
    def save_trades(self):
        """Save paper trades to file"""
        Path('data').mkdir(exist_ok=True)
        with open(self.trades_file, 'w') as f:
            json.dump(self.trades, f, indent=2, default=str)
    
    async def send_telegram(self, message: str, important: bool = False):
        """Send Telegram notification (only if important in paper trading mode)"""
        if not self.telegram_enabled:
            return
        
        # In paper trading mode, only send important messages
        if self.telegram_notifications and not important:
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
            print(f"⚠️ Telegram error: {e}")
    
    async def send_startup_message(self):
        """Send startup notification"""
        whale_list = "\n".join([
            f"  {i}. {whale[:16]}..." 
            for i, whale in enumerate(self.target_whales, 1)
        ])
        
        await self.send_telegram(
            f"🚀 <b>Paper Trading Started</b>\n\n"
            f"<b>Monitoring:</b> {len(self.target_whales)} elite whales\n"
            f"{whale_list}\n\n"
            f"<b>Delay:</b> +{self.delay_seconds}s\n"
            f"<b>Mode:</b> Essential notifications only\n\n"
            f"📊 Status: Active and monitoring",
            important=True
        )
    
    async def send_heartbeat(self):
        """Send heartbeat status every 2 hours"""
        open_trades = len([t for t in self.trades if t.get('status') == 'open'])
        pending_trades = len([t for t in self.trades if t.get('status') == 'pending_entry'])
        completed_trades = len([t for t in self.trades if t.get('status') == 'completed'])
        
        trades_with_entry = [t for t in self.trades if 'our_entry_price' in t]
        if trades_with_entry:
            costs = [t.get('delay_cost_percent', 0) for t in trades_with_entry]
            avg_cost = sum(costs) / len(costs)
            cost_text = f"{avg_cost:+.2%}"
        else:
            cost_text = "N/A"
        
        await self.send_telegram(
            f"💓 <b>Paper Trading Heartbeat</b>\n\n"
            f"<b>Status:</b> ✅ Running\n"
            f"<b>Total Trades:</b> {len(self.trades)}\n"
            f"  • Open: {open_trades}\n"
            f"  • Pending Entry: {pending_trades}\n"
            f"  • Completed: {completed_trades}\n\n"
            f"<b>Avg Delay Cost:</b> {cost_text}\n"
            f"<b>Monitoring:</b> {len(self.target_whales)} whales\n\n"
            f"⏰ Next update in 2 hours",
            important=True
        )
    
    async def record_whale_trade(self, whale_address: str, market_slug: str, 
                                 whale_price: float, size: float, timestamp: datetime):
        """Record when target whale trades"""
        
        whale_lower = whale_address.lower()
        if whale_lower not in self.target_whales:
            return  # Not one of our target whales
        
        trade_id = f"paper_{timestamp.strftime('%Y%m%d_%H%M%S')}_{whale_lower[:8]}"
        
        # Record whale's entry
        trade = {
            'trade_id': trade_id,
            'timestamp': timestamp.isoformat(),
            'whale': whale_lower,
            'market': market_slug,
            'whale_entry_price': whale_price,
            'whale_size': size,
            'whale_value': size * whale_price,
            'status': 'pending_entry',  # Waiting for our delayed entry
            'delay_seconds': self.delay_seconds
        }
        
        self.trades.append(trade)
        self.pending_entries[trade_id] = {
            'trade': trade,
            'entry_time': timestamp + timedelta(seconds=self.delay_seconds),
            'market': market_slug
        }
        
        print(f"\n📝 Paper Trade Detected:")
        print(f"   Whale: {whale_lower[:16]}...")
        print(f"   Market: {market_slug[:50]}")
        print(f"   Whale Entry: {whale_price:.4f}")
        print(f"   Size: ${size * whale_price:,.2f}")
        print(f"   Our entry scheduled: +{self.delay_seconds}s")
        
        # Schedule delayed entry check
        asyncio.create_task(self.check_delayed_entry(trade_id, market_slug, timestamp))
        
        # Send Telegram notification
        if self.telegram_enabled:
            meta = self.whale_metadata.get(whale_lower, {})
            await self.send_telegram(
                f"📝 <b>Paper Trade Detected</b>\n\n"
                f"<b>Whale:</b> {whale_lower[:16]}...\n"
                f"<b>Market:</b> {market_slug[:50]}...\n"
                f"<b>Whale Entry:</b> {whale_price:.4f}\n"
                f"<b>Size:</b> ${size * whale_price:,.2f}\n"
                f"<b>Our Entry:</b> +{self.delay_seconds}s delay\n\n"
                f"Win Rate: {meta.get('win_rate_1min', 0):.1f}%\n"
                f"Expected Cost: {meta.get('avg_delay_cost_1min', 0):+.2%}"
            )
        
        self.save_trades()
    
    async def check_delayed_entry(self, trade_id: str, market_slug: str, detection_time: datetime):
        """Check price at delayed entry time"""
        await asyncio.sleep(self.delay_seconds)
        
        entry_time = datetime.now()
        
        # Find the trade
        trade = next((t for t in self.trades if t.get('trade_id') == trade_id), None)
        if not trade:
            return
        
        # Try to get actual price from price history if available
        our_entry_price = None
        price_source = "fallback"
        
        if trade_id in self.pending_entries:
            pending = self.pending_entries[trade_id]
            price_history = pending.get('price_history', [])
            
            if price_history:
                # Find closest price to entry_time (within 30 seconds)
                closest = None
                min_diff = float('inf')
                
                for hist_time, hist_price in price_history:
                    if isinstance(hist_time, str):
                        hist_time = datetime.fromisoformat(hist_time.replace('Z', '+00:00'))
                    diff = abs((hist_time - entry_time).total_seconds())
                    if diff < min_diff and diff <= 30:
                        min_diff = diff
                        closest = hist_price
                
                if closest is not None:
                    our_entry_price = closest
                    price_source = "actual_lookup"
        
        # Fallback: use detection price + slippage estimate
        if our_entry_price is None:
            whale_price = trade['whale_entry_price']
            slippage = 0.001  # 0.1% slippage estimate
            our_entry_price = whale_price * (1 + slippage)
            price_source = "fallback_slippage"
        
        # Update trade with our entry
        whale_price = trade['whale_entry_price']
        trade['our_entry_price'] = our_entry_price
        trade['our_entry_time'] = entry_time.isoformat()
        trade['price_source'] = price_source
        trade['delay_cost'] = our_entry_price - whale_price
        trade['delay_cost_percent'] = (our_entry_price - whale_price) / whale_price
        trade['status'] = 'open'
        
        print(f"\n✅ Delayed Entry Recorded:")
        print(f"   Trade ID: {trade_id}")
        print(f"   Our Entry: {our_entry_price:.4f}")
        print(f"   Delay Cost: {trade['delay_cost_percent']:+.2%}")
        print(f"   Price Source: {price_source}")
        
        # Send Telegram notification (IMPORTANT - always send in paper trading mode)
        await self.send_telegram(
            f"✅ <b>Paper Trade Entry #{len([t for t in self.trades if 'our_entry_price' in t])}</b>\n\n"
            f"<b>Trade ID:</b> {trade_id[-12:]}\n"
            f"<b>Whale Entry:</b> {whale_price:.4f}\n"
            f"<b>Our Entry:</b> {our_entry_price:.4f}\n"
            f"<b>Delay Cost:</b> {trade['delay_cost_percent']:+.2%}\n"
            f"<b>Price Source:</b> {price_source}\n"
            f"<b>Status:</b> Open position",
            important=True
        )
        
        self.save_trades()
    
    async def daily_report(self, send_telegram: bool = True):
        """Generate daily performance report"""
        if not self.trades:
            print("\n📊 Paper Trading Report: No trades yet")
            return
        
        open_trades = [t for t in self.trades if t.get('status') == 'open']
        completed_trades = [t for t in self.trades if t.get('status') == 'completed']
        pending_trades = [t for t in self.trades if t.get('status') == 'pending_entry']
        
        print("\n" + "=" * 80)
        print("📊 PAPER TRADING DAILY REPORT")
        print("=" * 80)
        print(f"\nTotal Trades: {len(self.trades)}")
        print(f"  • Open: {len(open_trades)}")
        print(f"  • Completed: {len(completed_trades)}")
        print(f"  • Pending Entry: {len(pending_trades)}")
        
        telegram_msg_parts = [
            f"📊 <b>Paper Trading Daily Report</b>\n\n",
            f"<b>Total Trades:</b> {len(self.trades)}\n",
            f"  • Open: {len(open_trades)}\n",
            f"  • Completed: {len(completed_trades)}\n",
            f"  • Pending Entry: {len(pending_trades)}\n"
        ]
        
        if open_trades or completed_trades:
            trades_with_entry = [t for t in self.trades if 'our_entry_price' in t]
            if trades_with_entry:
                costs = [t.get('delay_cost_percent', 0) for t in trades_with_entry]
                avg_cost = sum(costs) / len(costs)
                min_cost = min(costs)
                max_cost = max(costs)
                
                print(f"\nDelay Cost Statistics:")
                print(f"  • Average: {avg_cost:+.2%}")
                print(f"  • Minimum: {min_cost:+.2%}")
                print(f"  • Maximum: {max_cost:+.2%}")
                print(f"  • Trades analyzed: {len(trades_with_entry)}")
                
                telegram_msg_parts.extend([
                    f"\n<b>Delay Cost Statistics:</b>\n",
                    f"  • Average: {avg_cost:+.2%}\n",
                    f"  • Min: {min_cost:+.2%}\n",
                    f"  • Max: {max_cost:+.2%}\n",
                    f"  • Analyzed: {len(trades_with_entry)} trades\n"
                ])
        
        # Per-whale stats
        whale_stats = defaultdict(lambda: {'count': 0, 'avg_cost': 0, 'costs': []})
        for trade in self.trades:
            if 'our_entry_price' in trade:
                whale = trade['whale']
                whale_stats[whale]['count'] += 1
                whale_stats[whale]['costs'].append(trade.get('delay_cost_percent', 0))
        
        if whale_stats:
            print(f"\nPer-Whale Statistics:")
            telegram_msg_parts.append(f"\n<b>Per-Whale Stats:</b>\n")
            for whale, stats in whale_stats.items():
                if stats['costs']:
                    avg = sum(stats['costs']) / len(stats['costs'])
                    print(f"  • {whale[:16]}...: {stats['count']} trades, avg cost: {avg:+.2%}")
                    telegram_msg_parts.append(f"  • {whale[:16]}...: {stats['count']} trades, {avg:+.2%}\n")
        
        print("\n" + "=" * 80)
        
        # Send Telegram summary (IMPORTANT - daily report)
        if send_telegram:
            await self.send_telegram(''.join(telegram_msg_parts), important=True)
    
    async def monitor_websocket(self):
        """Monitor WebSocket for whale trades with robust error handling"""
        ws_url = "wss://ws-live-data.polymarket.com"
        
        print("\n🔌 Connecting to Polymarket WebSocket...")
        print("   Monitoring for target whale trades...")
        print()
        
        # Price history for delayed entry lookups
        price_history = defaultdict(list)  # {market: [(timestamp, price), ...]}
        
        reconnect_delay = 5
        max_reconnect_delay = 60
        consecutive_errors = 0
        
        while True:
            try:
                async with websockets.connect(ws_url, ping_interval=20, ping_timeout=10) as websocket:
                    print("✅ WebSocket connected")
                    consecutive_errors = 0
                    reconnect_delay = 5  # Reset delay on successful connection
                    
                    # Subscribe to trades
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
                    print("✅ Subscribed to trade activity")
                    print()
                    
                    async for message in websocket:
                        try:
                            data = json.loads(message)
                            
                            # Process trade message
                            if isinstance(data, dict) and 'data' in data:
                                trade_data = data['data']
                                
                                market_slug = trade_data.get('slug', '')
                                size = float(trade_data.get('size', 0))
                                price = float(trade_data.get('price', 0))
                                timestamp_raw = trade_data.get('timestamp')
                                wallet = trade_data.get('proxyWallet', '').lower()
                                
                                # Record price history for all trades
                                if isinstance(timestamp_raw, (int, float)):
                                    timestamp = datetime.fromtimestamp(timestamp_raw)
                                elif isinstance(timestamp_raw, str):
                                    timestamp = datetime.fromisoformat(timestamp_raw.replace('Z', '+00:00'))
                                else:
                                    timestamp = datetime.now()
                                
                                # Store price history (keep last 1000 per market)
                                price_history[market_slug].append((timestamp, price))
                                if len(price_history[market_slug]) > 1000:
                                    price_history[market_slug] = price_history[market_slug][-1000:]
                                
                                # Check if target whale
                                if wallet in self.target_whales:
                                    trade_value = size * price
                                    if trade_value >= 100:
                                        try:
                                            # Store price history reference before recording
                                            await self.record_whale_trade(
                                                wallet, market_slug, price, size, timestamp
                                            )
                                            
                                            # Update price history reference for delayed entry
                                            if self.pending_entries:
                                                latest_trade_id = list(self.pending_entries.keys())[-1]
                                                if latest_trade_id in self.pending_entries:
                                                    self.pending_entries[latest_trade_id]['price_history'] = price_history[market_slug].copy()
                                        except Exception as e:
                                            print(f"⚠️ Error recording whale trade: {e}")
                                            import traceback
                                            traceback.print_exc()
                                
                        except json.JSONDecodeError:
                            continue
                        except Exception as e:
                            print(f"⚠️ Error processing message: {e}")
                            import traceback
                            traceback.print_exc()
                            
            except websockets.exceptions.ConnectionClosed:
                consecutive_errors += 1
                print(f"⚠️ WebSocket disconnected (error #{consecutive_errors}), reconnecting in {reconnect_delay}s...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                
            except websockets.exceptions.WebSocketException as e:
                consecutive_errors += 1
                print(f"⚠️ WebSocket error (error #{consecutive_errors}): {e}")
                print(f"   Reconnecting in {reconnect_delay}s...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                
            except KeyboardInterrupt:
                print("\n\n⚠️ Keyboard interrupt received")
                raise
                
            except Exception as e:
                consecutive_errors += 1
                print(f"❌ Unexpected error (error #{consecutive_errors}): {e}")
                import traceback
                traceback.print_exc()
                print(f"   Reconnecting in {reconnect_delay}s...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                
                # Send error notification if Telegram enabled
                if self.telegram_enabled and consecutive_errors <= 3:
                    try:
                        await self.send_telegram(
                            f"⚠️ <b>Paper Trading Error</b>\n\n"
                            f"Error #{consecutive_errors}: {str(e)[:200]}\n"
                            f"Reconnecting automatically...",
                            important=True
                        )
                    except:
                        pass

async def main():
    """Main entry point with robust error handling"""
    trader = None
    startup_message_sent = False
    
    try:
        trader = PaperTrader()
        
        # Send startup message (only once)
        if trader.telegram_enabled and not startup_message_sent:
            try:
                await trader.send_startup_message()
                startup_message_sent = True
            except Exception as e:
                print(f"⚠️ Failed to send startup message: {e}")
        
        # Schedule daily report (once per day at midnight UTC)
        async def schedule_daily_reports():
            while True:
                try:
                    now = datetime.now()
                    # Calculate seconds until next midnight UTC
                    next_midnight = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
                    wait_seconds = (next_midnight - now).total_seconds()
                    await asyncio.sleep(wait_seconds)
                    if trader:
                        await trader.daily_report(send_telegram=True)
                except Exception as e:
                    print(f"⚠️ Error in daily report scheduler: {e}")
                    await asyncio.sleep(3600)  # Wait 1 hour before retrying
        
        # Schedule heartbeat (every 2 hours)
        async def schedule_heartbeat():
            while True:
                try:
                    await asyncio.sleep(2 * 3600)  # 2 hours = 7200 seconds
                    if trader:
                        await trader.send_heartbeat()
                except Exception as e:
                    print(f"⚠️ Error in heartbeat scheduler: {e}")
                    await asyncio.sleep(3600)  # Wait 1 hour before retrying
        
        # Start schedulers
        asyncio.create_task(schedule_daily_reports())
        asyncio.create_task(schedule_heartbeat())
        
        # Start monitoring (with infinite retry loop)
        print("🚀 Starting paper trading monitor...")
        await trader.monitor_websocket()
        
    except KeyboardInterrupt:
        print("\n\n📊 Generating final report...")
        if trader:
            try:
                await trader.daily_report(send_telegram=True)
            except:
                pass
        print("\n✅ Paper trading stopped by user")
        
    except Exception as e:
        print(f"\n❌ Fatal error in main: {e}")
        import traceback
        traceback.print_exc()
        
        # Send error notification
        if trader and trader.telegram_enabled:
            try:
                await trader.send_telegram(
                    f"❌ <b>Paper Trading Fatal Error</b>\n\n"
                    f"Error: {str(e)[:200]}\n\n"
                    f"System will attempt to restart...",
                    important=True
                )
            except:
                pass
        
        # Re-raise to trigger restart
        raise

if __name__ == "__main__":
    asyncio.run(main())
