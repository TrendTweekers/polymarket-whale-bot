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
from typing import Optional
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
        # Load existing trades to preserve history across restarts
        self.detected_trades = self.load_existing_trades()
        self.enable_telegram = enable_telegram
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        # Initialize market-first detection and dynamic whale management
        self.anomaly_detector = MarketAnomalyDetector()
        self.whale_manager = DynamicWhaleManager()
        
        # Track Phase 2 start time for progress calculation
        # Phase 2 goal: 48 hours of data collection
        # CRITICAL: Load persisted start time to prevent reset on restarts
        self.phase2_goal_hours = 48.0
        self.phase2_start_time = self._load_phase2_start_time()
        self.startup_notification_sent = False  # Track if startup notification was sent
        self.hourly_summary_task_started = False  # Track if hourly summary task was started
        
        # Initialize simulation for Phase 2 data collection
        try:
            import sys
            from pathlib import Path
            import json
            # Add project root to path
            project_root = Path(__file__).parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            
            from src.simulation import TradeSimulator
            
            # Load elite whales from API validation results
            elite_whales = set()
            elite_file = project_root / "data" / "api_validation_results.json"
            if elite_file.exists():
                try:
                    with open(elite_file, 'r') as f:
                        elite_data = json.load(f)
                    # Extract addresses of whales that pass validation
                    # Handle both list and dict formats
                    if isinstance(elite_data, list):
                        results = elite_data
                    else:
                        results = elite_data.get('results', [])
                    
                    elite_whales = {
                        w['address'].lower() 
                        for w in results
                        if w.get('passes', False)
                    }
                    if elite_whales:
                        print(f"✅ Loaded {len(elite_whales)} elite whales from API validation")
                        # Debug: Show sample addresses
                        print(f"   Sample elite addresses (first 3):")
                        for addr in list(elite_whales)[:3]:
                            print(f"     - {addr}")
                except Exception as e:
                    print(f"⚠️ Could not load elite whales: {e}")
            
            # Pass price lookup function to simulator for real-time price tracking
            self.trade_simulator = TradeSimulator(
                elite_whales=elite_whales,
                price_lookup_func=self.get_price_at_time
            )
            self.simulation_enabled = True
            print("✅ Simulation module loaded - Phase 2 data collection ENABLED")
            print(f"⏰ Phase 2 started at {self.phase2_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"🎯 Goal: {self.phase2_goal_hours} hours of data collection")
            
            # Save Phase 2 start time if it was just determined (deferred from __init__)
            if hasattr(self, '_pending_phase2_save'):
                self._save_phase2_start_time(self._pending_phase2_save)
                delattr(self, '_pending_phase2_save')
        except ImportError as e:
            self.trade_simulator = None
            self.simulation_enabled = False
            print(f"⚠️ Simulation module not available - data collection disabled: {e}")
        
        # Track stats for hourly summary
        self.trades_processed = 0
        self.whale_trades_detected = 0
        self.simulations_started = 0
        self.elite_simulations_started = 0
        
        # Health monitoring - track last activity time
        self.last_trade_time = datetime.now()
        self.health_check_interval = 300  # Check every 5 minutes
        self.max_idle_time = 3600  # Alert if no trades for 1 hour
        
        # Real-time price tracking for simulations
        # {market_slug: [{'timestamp': str, 'price': float}, ...]}
        self.market_price_history = {}
        self.MAX_PRICE_HISTORY = 1000  # Keep last 1000 prices per market
        
        # Debug counter initialization
        print(f"🔢 Counters initialized: trades_processed={self.trades_processed}")
        
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
    
    async def send_startup_notification(self):
        """Send startup notification to Telegram"""
        if not self.enable_telegram:
            return
        
        try:
            # Get whale stats
            whale_stats = self.whale_manager.get_whale_stats()
            elite_count = len(self.trade_simulator.elite_whales) if self.trade_simulator else 0
            
            message = (
                f"🚀 <b>WHALE WATCHER STARTED</b>\n\n"
                f"✅ WebSocket connected\n"
                f"✅ Elite whales loaded: {elite_count}\n"
                f"✅ Simulation module enabled\n\n"
                f"📊 <b>Status:</b>\n"
                f"• Total whales: {whale_stats['total_whales']}\n"
                f"• High-confidence: {whale_stats['high_confidence']}\n"
                f"• Active: {whale_stats['active_whales']}\n\n"
                f"🔍 <b>Monitoring:</b>\n"
                f"• {len(self.whale_addresses)} monitored addresses\n"
                f"• Min trade size: ${self.min_trade_size:,.0f}\n\n"
                f"<i>System operational - watching for trades...</i>"
            )
            
            await self.send_telegram(message)
            print("✅ Startup notification sent to Telegram")
        except Exception as e:
            print(f"⚠️ Failed to send startup notification: {e}")
    
    async def send_hourly_summary(self):
        """Send hourly summary to Telegram (reduces noise)"""
        if not self.enable_telegram:
            return
        
        # Wait until next full hour before sending first summary
        from datetime import datetime, timedelta
        now = datetime.now()
        next_hour = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
        wait_seconds = (next_hour - now).total_seconds()
        if wait_seconds > 0:
            print(f"⏰ First hourly summary will be sent in {wait_seconds/60:.1f} minutes (at {next_hour.strftime('%H:%M')})")
            await asyncio.sleep(wait_seconds)
        
        while True:
            try:
                # Capture counter values BEFORE resetting (at start of hour)
                current_trades = self.trades_processed
                current_whale_trades = self.whale_trades_detected
                current_simulations = self.simulations_started
                current_elite_simulations = getattr(self, 'elite_simulations_started', 0)
                
                # Get stats
                whale_stats = self.whale_manager.get_whale_stats()
                
                # Format simulation text with elite count
                sim_text = f"{current_simulations}"
                if current_elite_simulations > 0:
                    sim_text += f" ({current_elite_simulations} elite)"
                
                # Get current time for summary
                summary_time = datetime.now().strftime('%H:%M')
                
                # Calculate Phase 2 progress
                elapsed_time = datetime.now() - self.phase2_start_time
                elapsed_hours = elapsed_time.total_seconds() / 3600.0
                progress_percent = min(100.0, (elapsed_hours / self.phase2_goal_hours) * 100.0)
                hours_remaining = max(0, self.phase2_goal_hours - elapsed_hours)
                
                # Create progress bar (10 segments)
                progress_bar_length = 10
                filled_segments = int(progress_percent / 100 * progress_bar_length)
                progress_bar = "█" * filled_segments + "░" * (progress_bar_length - filled_segments)
                
                # Get cumulative totals from files (for clarity)
                sim_dir = Path("data/simulations")
                total_sims = len(list(sim_dir.glob("sim_*.json"))) if sim_dir.exists() else 0
                
                trades_file = Path("data/realtime_whale_trades.json")
                total_trades = 0
                if trades_file.exists():
                    try:
                        with open(trades_file, 'r') as f:
                            trades_data = json.load(f)
                            if isinstance(trades_data, list):
                                total_trades = len(trades_data)
                    except:
                        pass
                
                summary = (
                    f"📊 <b>Hourly Summary</b> ({summary_time})\n\n"
                    f"🎯 <b>Phase 2 Progress:</b> {progress_percent:.1f}%\n"
                    f"   {progress_bar} {elapsed_hours:.1f}h / {self.phase2_goal_hours:.0f}h\n"
                    f"   ⏰ {hours_remaining:.1f}h remaining\n\n"
                    f"🐋 <b>Whales:</b> {whale_stats['total_whales']} total\n"
                    f"   • High-conf: {whale_stats['high_confidence']}\n"
                    f"   • Active: {whale_stats['active_whales']}\n\n"
                    f"📈 <b>Trades (this hour):</b> {current_trades:,} processed\n"
                    f"   • Whale trades: {current_whale_trades}\n"
                    f"   • Simulations: {sim_text}\n\n"
                    f"💾 <b>Total (cumulative):</b>\n"
                    f"   • Total trades: {total_trades:,}\n"
                    f"   • Total simulations: {total_sims}\n\n"
                    f"🔥 <b>System:</b> Operational\n"
                    f"   • Avg confidence: {whale_stats['avg_confidence']:.1%}"
                )
                
                await self.send_telegram(summary)
                print(f"✅ Hourly summary sent: {current_trades:,} trades, {current_whale_trades} whale trades, {current_simulations} simulations")
                
                # Reset counters for next hour (AFTER sending summary)
                self.trades_processed = 0
                self.whale_trades_detected = 0
                self.simulations_started = 0
                if hasattr(self, 'elite_simulations_started'):
                    self.elite_simulations_started = 0
                
                # Wait exactly 1 hour before next summary
                await asyncio.sleep(3600)
                
            except Exception as e:
                # Don't let summary errors break the watcher
                print(f"⚠️ Hourly summary error: {e}")
                import traceback
                traceback.print_exc()
                # Wait before retrying
                await asyncio.sleep(60)
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
                    
                    # Send startup notification to Telegram (only once, not on every reconnect)
                    # Also check if we just started (avoid rapid restart spam)
                    if not self.startup_notification_sent:
                        # Small delay to avoid duplicate notifications on rapid restarts
                        await asyncio.sleep(2)
                        # Double-check flag after delay (in case of rapid restart)
                        if not self.startup_notification_sent:
                            await self.send_startup_notification()
                            self.startup_notification_sent = True
                    
                    # Start hourly summary task (only once, not on every reconnect)
                    if not self.hourly_summary_task_started:
                        asyncio.create_task(self.send_hourly_summary())
                        self.hourly_summary_task_started = True
                    
                    # Start health monitoring task (only once)
                    if not hasattr(self, '_health_monitor_started'):
                        asyncio.create_task(self._health_monitor())
                        self._health_monitor_started = True
                    
                    # Listen for messages
                    async for message in websocket:
                        await self.handle_message(message)
                        
            except websockets.exceptions.ConnectionClosed as e:
                print(f"\n⚠️ Connection closed: {e}")
                print(f"Reconnecting in {reconnect_delay} seconds...")
                
                # Send alert if enabled
                if self.enable_telegram:
                    try:
                        await self.send_telegram(
                            f"⚠️ <b>WebSocket Disconnected</b>\n\n"
                            f"Reconnecting in {reconnect_delay}s...\n"
                            f"<i>Auto-reconnect enabled</i>"
                        )
                    except:
                        pass
                
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                
            except websockets.exceptions.WebSocketException as e:
                print(f"\n❌ WebSocket error: {e}")
                print(f"Reconnecting in {reconnect_delay} seconds...")
                
                # Send alert if enabled
                if self.enable_telegram:
                    try:
                        await self.send_telegram(
                            f"❌ <b>WebSocket Error</b>\n\n"
                            f"Error: {str(e)[:100]}\n"
                            f"Reconnecting in {reconnect_delay}s...\n"
                            f"<i>Auto-reconnect enabled</i>"
                        )
                    except:
                        pass
                
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                
            except Exception as e:
                print(f"\n❌ Unexpected error: {e}")
                import traceback
                traceback.print_exc()
                
                # Send alert if enabled
                if self.enable_telegram:
                    try:
                        await self.send_telegram(
                            f"❌ <b>Watcher Error</b>\n\n"
                            f"Error: {str(e)[:100]}\n"
                            f"Reconnecting in {reconnect_delay}s...\n"
                            f"<i>Auto-recovery enabled</i>"
                        )
                    except:
                        pass
                
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
        
        # Check if whale is elite FIRST (before checking monitored list)
        # Elite whales should trigger simulations even if not in monitored list
        is_elite = False
        try:
            if hasattr(self, 'trade_simulator') and self.trade_simulator and hasattr(self.trade_simulator, 'elite_whales') and self.trade_simulator.elite_whales:
                whale_addr_lower = wallet.lower()
                is_elite = whale_addr_lower in self.trade_simulator.elite_whales
        except Exception as e:
            # Don't crash if elite check fails
            if not hasattr(self, '_elite_check_error_logged'):
                print(f"⚠️ Elite check error (non-fatal): {e}")
                self._elite_check_error_logged = True
        
        # Check if it's a whale trade (monitored OR elite)
        is_whale = wallet in self.whale_addresses or is_elite
        
        # Get whale confidence if it's a monitored whale or elite
        whale_confidence = None
        if is_whale:
            whale_data = self.whale_manager.whales.get(wallet)
            if whale_data:
                whale_confidence = whale_data.get('confidence', 0.0)
            elif is_elite:
                # Elite whale not in dynamic pool yet - give default confidence
                whale_confidence = 0.5  # 50% default for elite whales
            else:
                # Not in dynamic manager yet, check if in static list
                whale_confidence = 0.5  # Default for static list whales
        
        is_large = trade_value >= self.min_trade_size
        
        # Increment counter for ALL trades (before any filtering)
        # This ensures we count every trade that comes through
        self.trades_processed += 1
        
        # Update health monitoring - mark that we're processing trades
        self.last_trade_time = datetime.now()
        
        # Record market price for real-time price tracking (for simulations)
        # This allows us to get actual prices at +1, +3, +5 min delays
        self._record_market_price(market_slug, price, timestamp)
        
        # Debug: Log first few increments to verify counter is working
        if not hasattr(self, '_counter_debug_logged'):
            self._counter_debug_logged = 0
        if self._counter_debug_logged < 5:
            print(f"🔢 Counter increment: trades_processed = {self.trades_processed}")
            self._counter_debug_logged += 1
        
        if is_whale or is_large:
            # Format output
            whale_indicator = "🐋 WHALE" if is_whale else "📊 LARGE"
            
            print(f"{whale_indicator} TRADE DETECTED!")
            print(f"  Wallet: {wallet[:12]}...")
            print(f"  Market: {market_slug[:50]}")
            print(f"  Size: ${trade_value:,.2f} ({size} @ {price})")
            print(f"  Time: {timestamp}")
            if is_whale:
                if is_elite:
                    print(f"  ✅ This is an ELITE whale!")
                else:
                    print(f"  ✅ This is one of your monitored whales!")
            print()
            
            # Elite check already done above, use it here
            
            # Use different thresholds based on elite status
            # Elite whales: 50% threshold (pre-validated, just need some activity)
            # Regular whales: 65% threshold (need higher confidence)
            if is_elite:
                confidence_threshold = 0.50  # 50% for elite whales
                threshold_label = "≥50%"
            else:
                confidence_threshold = 0.65  # 65% for regular whales
                threshold_label = "≥65%"
            
            # Send Telegram notification for high-confidence whales
            # Elite whales use lower threshold (50%) since they're pre-validated
            if is_whale and whale_confidence and whale_confidence >= confidence_threshold:
                self.whale_trades_detected += 1
                
                elite_badge = "⭐ ELITE" if is_elite else ""
                telegram_msg = (
                    f"🐋 <b>HIGH-CONFIDENCE WHALE TRADE</b> {elite_badge}\n\n"
                    f"<b>Wallet:</b> <code>{wallet[:16]}...</code>\n"
                    f"<b>Confidence:</b> {whale_confidence:.0%}\n"
                    f"<b>Market:</b> {market_slug[:80]}\n"
                    f"<b>Size:</b> ${trade_value:,.2f}\n"
                    f"<b>Price:</b> {price:.2%}\n"
                    f"<b>Time:</b> {timestamp[:19]}\n\n"
                    f"✅ High-confidence whale ({threshold_label})\n\n"
                    f"<i>[Real-Time Detection]</i>"
                )
                # Send Telegram notification (with error handling)
                try:
                    await self.send_telegram(telegram_msg)
                except Exception as e:
                    # Log but don't crash - Telegram failures shouldn't stop simulations
                    if not hasattr(self, '_telegram_error_count'):
                        self._telegram_error_count = 0
                    self._telegram_error_count += 1
                    if self._telegram_error_count <= 3:
                        print(f"⚠️ Telegram send error (non-fatal): {e}")
                
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
                        
                        # Elite check already done above, use it here
                        
                        # Debug logging (first few only)
                        if not hasattr(self, '_elite_check_debug_count'):
                            self._elite_check_debug_count = 0
                        if self._elite_check_debug_count < 5:
                            print(f"🔍 Elite check:")
                            print(f"   Whale: {wallet[:20]}...")
                            print(f"   Lowercase: {whale_addr_lower[:20]}...")
                            print(f"   Is elite: {is_elite}")
                            print(f"   Confidence: {whale_confidence:.0%}")
                            print(f"   Threshold: {threshold_label}")
                            print(f"   Elite set size: {len(self.trade_simulator.elite_whales)}")
                            if is_elite:
                                print(f"   ✅ ELITE WHALE - Using lower threshold!")
                            self._elite_check_debug_count += 1
                        
                        # Start simulation with scheduled delay checks (NEW APPROACH)
                        # This schedules async tasks to check prices at T+60s, T+180s, T+300s
                        sim_id = await self.trade_simulator.simulate_trade(
                            whale_trade={
                                'wallet': wallet,
                                'market': market_slug,
                                'price': price,
                                'size': size,
                                'timestamp': trade_datetime.isoformat(),
                                'is_elite': is_elite,
                                'confidence': whale_confidence
                            },
                            telegram_callback=self.send_telegram if self.enable_telegram else None
                        )
                        
                        self.simulations_started += 1
                        if is_elite:
                            # Track elite simulations separately
                            if not hasattr(self, 'elite_simulations_started'):
                                self.elite_simulations_started = 0
                            self.elite_simulations_started += 1
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
    
    def _load_phase2_start_time(self) -> datetime:
        """Load Phase 2 start time from file, or use first simulation file timestamp"""
        phase2_file = Path("data/phase2_start_time.json")
        
        # Try to load from file
        if phase2_file.exists():
            try:
                with open(phase2_file, 'r') as f:
                    data = json.load(f)
                    start_time_str = data.get('start_time')
                    if start_time_str:
                        start_time = datetime.fromisoformat(start_time_str)
                        print(f"✅ Loaded Phase 2 start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
                        return start_time
            except Exception as e:
                print(f"⚠️ Could not load Phase 2 start time: {e}")
        
        # Fallback: Use first simulation file timestamp
        sim_dir = Path("data/simulations")
        if sim_dir.exists():
            sim_files = list(sim_dir.glob("sim_*.json"))
            if sim_files:
                # Get oldest simulation file
                oldest_sim = min(sim_files, key=lambda x: x.stat().st_mtime)
                start_time = datetime.fromtimestamp(oldest_sim.stat().st_mtime)
                print(f"✅ Using first simulation timestamp as Phase 2 start: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
                # Save it for future use (defer until after __init__ completes)
                # Store for saving later
                self._pending_phase2_save = start_time
                return start_time
        
        # First time: Use current time
        start_time = datetime.now()
        print(f"⏰ Phase 2 starting now: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        # Store for saving later (defer until after __init__ completes)
        self._pending_phase2_save = start_time
        return start_time
    
    def _save_phase2_start_time(self, start_time: datetime):
        """Save Phase 2 start time to file"""
        try:
            phase2_file = Path("data/phase2_start_time.json")
            phase2_file.parent.mkdir(parents=True, exist_ok=True)
            with open(phase2_file, 'w') as f:
                json.dump({'start_time': start_time.isoformat()}, f)
        except Exception as e:
            print(f"⚠️ Could not save Phase 2 start time: {e}")
    
    async def _health_monitor(self):
        """Monitor watcher health and alert if no activity"""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)  # Check every 5 minutes
                
                # Check time since last trade
                time_since_last_trade = (datetime.now() - self.last_trade_time).total_seconds()
                idle_minutes = time_since_last_trade / 60.0
                
                # Alert if no trades for 1+ hour
                if time_since_last_trade > self.max_idle_time:
                    alert_msg = (
                        f"⚠️ <b>Watcher Health Alert</b>\n\n"
                        f"No trades processed for {idle_minutes:.0f} minutes ({idle_minutes/60:.1f} hours)\n\n"
                        f"🔍 <b>Status:</b>\n"
                        f"• Last trade: {self.last_trade_time.strftime('%H:%M:%S')}\n"
                        f"• Trades this hour: {self.trades_processed}\n"
                        f"• WebSocket: Connected\n\n"
                        f"<i>Checking connection...</i>"
                    )
                    
                    if self.enable_telegram:
                        try:
                            await self.send_telegram(alert_msg)
                        except:
                            pass
                    
                    print(f"⚠️ Health check: No trades for {idle_minutes:.0f} minutes")
                
                # Log periodic health status (every 30 minutes)
                if int(idle_minutes) % 30 == 0 and idle_minutes > 0:
                    print(f"💚 Health check: Last trade {idle_minutes:.0f} minutes ago, {self.trades_processed} trades this hour")
                    
            except Exception as e:
                print(f"⚠️ Health monitor error: {e}")
                await asyncio.sleep(60)  # Wait 1 min before retrying
    
    def load_existing_trades(self):
        """Load existing trades from file to preserve history"""
        output_file = Path("data/realtime_whale_trades.json")
        if output_file.exists():
            try:
                with open(output_file, 'r') as f:
                    existing = json.load(f)
                    if isinstance(existing, list):
                        print(f"✅ Loaded {len(existing)} existing trades from file")
                        return existing
            except Exception as e:
                print(f"⚠️ Could not load existing trades: {e}")
        return []
    
    def _record_market_price(self, market_slug: str, price: float, timestamp: str):
        """Record market price for historical lookup (used by simulations)"""
        if market_slug not in self.market_price_history:
            self.market_price_history[market_slug] = []
        
        # Add price point
        self.market_price_history[market_slug].append({
            'timestamp': timestamp,
            'price': price
        })
        
        # Trim if too long (keep most recent)
        if len(self.market_price_history[market_slug]) > self.MAX_PRICE_HISTORY:
            self.market_price_history[market_slug] = \
                self.market_price_history[market_slug][-self.MAX_PRICE_HISTORY:]
    
    def get_price_at_time(self, market_slug: str, target_time: str) -> Optional[float]:
        """
        Get market price at specific time (or closest available)
        
        Used by TradeSimulator to get actual prices at +1, +3, +5 min delays
        
        Args:
            market_slug: Market identifier
            target_time: ISO format timestamp (e.g., "2025-12-20T00:16:18Z")
        
        Returns:
            float: Price at that time, or None if not found
        """
        if market_slug not in self.market_price_history:
            return None
        
        history = self.market_price_history[market_slug]
        if not history:
            return None
        
        # Parse target time
        try:
            if isinstance(target_time, str):
                if 'T' in target_time:
                    target_dt = datetime.fromisoformat(target_time.replace('Z', '+00:00'))
                else:
                    target_dt = datetime.fromisoformat(target_time)
            elif isinstance(target_time, datetime):
                target_dt = target_time
            else:
                return None
        except:
            return None
        
        # Find closest price to target time
        closest = None
        min_diff = None
        
        for price_point in history:
            try:
                point_time = datetime.fromisoformat(
                    price_point['timestamp'].replace('Z', '+00:00')
                )
                diff = abs((target_dt - point_time).total_seconds())
                
                if min_diff is None or diff < min_diff:
                    min_diff = diff
                    closest = price_point
            except:
                continue
        
        # Return price if within 2 minutes (120 seconds)
        if closest and min_diff is not None and min_diff <= 120:
            # Debug: Log first few lookups
            if not hasattr(self, '_lookup_debug_count'):
                self._lookup_debug_count = 0
            if self._lookup_debug_count < 3:
                print(f"🔍 Price lookup: {market_slug[:30]}... at {target_time} → found price {closest['price']:.6f} (diff: {min_diff:.0f}s)")
                self._lookup_debug_count += 1
            return closest['price']
        
        # Debug: Log when price not found
        if not hasattr(self, '_lookup_miss_count'):
            self._lookup_miss_count = 0
        if self._lookup_miss_count < 3:
            if closest:
                print(f"⚠️ Price lookup: {market_slug[:30]}... at {target_time} → closest too far (diff: {min_diff:.0f}s > 120s)")
            else:
                print(f"⚠️ Price lookup: {market_slug[:30]}... at {target_time} → no history found")
            self._lookup_miss_count += 1
        
        return None
    
    def save_trades(self):
        """Save detected trades to file (preserves all trades, not just current session)"""
        output_file = Path("data/realtime_whale_trades.json")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Save all trades (including previously loaded ones)
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
