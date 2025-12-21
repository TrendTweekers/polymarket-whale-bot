"""
Trade Simulator - Phase 2
=========================
Simulates copying a whale trade with realistic delays and slippage

For each detected whale trade:
1. Record market state at detection time
2. Simulate execution at +1, +3, +5 min delays
3. Calculate entry price with slippage
4. Calculate P&L when market resolves
5. Return simulation results
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

from .market_state_tracker import MarketStateTracker
from .slippage_calculator import SlippageCalculator


@dataclass
class SimulationResult:
    """Results for a single delay simulation"""
    delay_seconds: int
    delay_minutes: float
    entry_price: float
    slippage_pct: float
    execution_time: datetime
    market_state_at_entry: Dict
    pnl: Optional[float] = None  # Calculated when market resolves
    pnl_pct: Optional[float] = None
    resolved: bool = False
    resolution_time: Optional[datetime] = None


@dataclass
class TradeSimulation:
    """Complete simulation results for a whale trade"""
    whale_address: str
    market_slug: str
    whale_trade_time: datetime
    whale_entry_price: float
    whale_trade_size: float
    detection_time: datetime
    
    # Results for each delay
    results: List[SimulationResult]
    
    # Summary
    best_delay: Optional[int] = None  # Delay with best P&L
    profitable: Optional[bool] = None  # True if any delay was profitable
    avg_pnl: Optional[float] = None
    
    # Elite whale flag (from API validation)
    is_elite: bool = False  # True if whale is in validated elite list


class TradeSimulator:
    """
    Simulates copying whale trades with realistic delays
    
    Usage:
        simulator = TradeSimulator()
        result = await simulator.simulate_trade(whale_trade_data)
    """
    
    def __init__(self, elite_whales: Optional[set] = None, storage_path: Optional[str] = None, price_lookup_func=None):
        self.market_tracker = MarketStateTracker()
        self.slippage_calc = SlippageCalculator()
        
        # Default delays: 1min, 3min, 5min
        self.default_delays = [60, 180, 300]
        
        # Elite whales set (from API validation)
        # Format: {address.lower() for address in elite_list}
        self.elite_whales = elite_whales or set()
        
        # Price lookup function for real-time price tracking
        # Function signature: (market_slug: str, target_time: str) -> Optional[float]
        self.price_lookup_func = price_lookup_func
        
        # Storage for simulation results
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            # Default: data/simulations/
            project_root = Path(__file__).parent.parent.parent
            self.storage_path = project_root / "data" / "simulations"
        
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Track simulations in memory (for quick access)
        self.simulations: List[TradeSimulation] = []
        
        # Track active scheduled tasks for delay checks
        self.active_tasks: List[asyncio.Task] = []
        
        # Telegram callback for notifications (set by watcher)
        self.telegram_callback = None
        
        if self.elite_whales:
            print(f"✅ TradeSimulator initialized with {len(self.elite_whales)} elite whales")
        print(f"✅ Simulation storage: {self.storage_path}")
        print(f"✅ Scheduled delay checks enabled (real-time price tracking)")
    
    async def simulate_trade(
        self, 
        whale_trade: Dict, 
        delays: List[int] = None,
        telegram_callback=None
    ) -> str:
        """
        Start simulation with scheduled delay price checks
        
        NEW APPROACH: Schedule async tasks to check prices at actual execution times
        - Creates initial simulation file immediately
        - Schedules tasks to check prices at T+60s, T+180s, T+300s
        - Each task updates simulation file when delay time arrives
        
        Args:
            whale_trade: Detected trade data with keys:
                - wallet: Whale address
                - market: Market slug
                - price: Entry price
                - size: Trade size
                - timestamp: Detection time
                - is_elite: Optional flag
                - confidence: Optional whale confidence
            delays: List of delays in seconds [60, 180, 300]
            telegram_callback: Optional callback for Telegram notifications
        
        Returns:
            str: Simulation ID
        """
        if delays is None:
            delays = self.default_delays
        
        # Store telegram callback for notifications
        if telegram_callback:
            self.telegram_callback = telegram_callback
        
        # Extract trade data
        whale_address = whale_trade.get('wallet', '').lower()
        market_slug = whale_trade.get('market', '')
        whale_price = float(whale_trade.get('price', 0))
        whale_size = float(whale_trade.get('size', 0))
        detection_time = self._parse_timestamp(whale_trade.get('timestamp'))
        confidence = whale_trade.get('confidence', 0)
        
        # Check if whale is elite
        is_elite = whale_trade.get('is_elite', False)
        
        # Double-check against elite_whales set (ensure address is normalized)
        if not is_elite and self.elite_whales:
            # Ensure whale_address is lowercase for comparison
            whale_addr_normalized = whale_address.lower()
            is_elite = whale_addr_normalized in self.elite_whales
            
            # Debug logging (first few only)
            if not hasattr(self, '_sim_elite_debug_count'):
                self._sim_elite_debug_count = 0
            if self._sim_elite_debug_count < 3:
                print(f"🔍 Simulator elite check:")
                print(f"   Address: {whale_address[:20]}...")
                print(f"   Normalized: {whale_addr_normalized[:20]}...")
                print(f"   In elite set: {is_elite}")
                print(f"   Elite set size: {len(self.elite_whales)}")
                self._sim_elite_debug_count += 1
        
        # Create simulation ID
        timestamp_str = detection_time.strftime('%Y%m%d_%H%M%S')
        whale_short = whale_address[:8]
        sim_id = f"sim_{timestamp_str}_{whale_short}"
        
        # Create initial simulation record
        simulation_data = {
            'simulation_id': sim_id,
            'whale_address': whale_address,
            'market_slug': market_slug,
            'is_elite': is_elite,
            'confidence': confidence,
            'detection': {
                'timestamp': detection_time.isoformat(),
                'market': market_slug,
                'price': whale_price,
                'size': whale_size
            },
            'results': [],
            'status': 'pending',
            'created_at': datetime.now().isoformat(),
            'delays_scheduled': delays
        }
        
        # Save initial simulation file
        sim_file = self.storage_path / f"{sim_id}.json"
        with open(sim_file, 'w') as f:
            json.dump(simulation_data, f, indent=2, default=str)
        
        # Send Telegram notification
        if self.telegram_callback:
            elite_text = " 🏆 ELITE" if is_elite else ""
            delay_text = ", ".join([f"+{d//60}min" for d in delays])
            msg = (
                f"🔬 <b>Simulation Started{elite_text}</b>\n\n"
                f"🐋 Whale: <code>{whale_address[:16]}...</code>\n"
                f"📊 Market: {market_slug[:50]}...\n"
                f"💰 Size: ${whale_size:,.0f}\n"
                f"📈 Price: {whale_price:.4f}\n\n"
                f"⏰ Delay checks scheduled:\n"
                f"   {delay_text}\n\n"
                f"<i>Prices will be checked at actual execution times</i>"
            )
            try:
                await self.telegram_callback(msg)
            except:
                pass
        
        print(f"🔬 Simulation started: {sim_id}")
        print(f"   Delay checks scheduled: {', '.join([f'+{d//60}min' for d in delays])}")
        
        # Schedule async tasks to check prices at each delay
        for delay_seconds in delays:
            task = asyncio.create_task(
                self._check_price_at_delay(
                    sim_id=sim_id,
                    trade_data={
                        'wallet': whale_address,
                        'market': market_slug,
                        'price': whale_price,
                        'size': whale_size,
                        'timestamp': detection_time.isoformat(),
                        'confidence': confidence
                    },
                    delay_seconds=delay_seconds
                )
            )
            self.active_tasks.append(task)
        
        return sim_id
    
    async def _save_simulation(self, simulation: TradeSimulation):
        """Save simulation result to disk"""
        try:
            # Create filename based on timestamp and whale address
            timestamp_str = simulation.detection_time.strftime('%Y%m%d_%H%M%S')
            whale_short = simulation.whale_address[:8]
            filename = f"sim_{timestamp_str}_{whale_short}.json"
            filepath = self.storage_path / filename
            
            # Convert dataclass to dict for JSON serialization
            sim_dict = self._simulation_to_dict(simulation)
            
            # Save to file
            with open(filepath, 'w') as f:
                json.dump(sim_dict, f, indent=2, default=str)
            
        except Exception as e:
            # Don't let save errors break simulation
            print(f"⚠️ Failed to save simulation: {e}")
    
    def _simulation_to_dict(self, simulation: TradeSimulation) -> Dict:
        """Convert TradeSimulation dataclass to dict for JSON serialization"""
        result = asdict(simulation)
        # Convert datetime objects to ISO strings
        if isinstance(result.get('whale_trade_time'), datetime):
            result['whale_trade_time'] = result['whale_trade_time'].isoformat()
        if isinstance(result.get('detection_time'), datetime):
            result['detection_time'] = result['detection_time'].isoformat()
        
        # Convert results list
        if result.get('results'):
            for r in result['results']:
                if isinstance(r, dict):
                    if 'execution_time' in r and isinstance(r['execution_time'], datetime):
                        r['execution_time'] = r['execution_time'].isoformat()
                    if 'resolution_time' in r and isinstance(r['resolution_time'], datetime):
                        r['resolution_time'] = r['resolution_time'].isoformat()
        
        return result
    
    async def _check_price_at_delay(
        self,
        sim_id: str,
        trade_data: Dict,
        delay_seconds: int
    ):
        """
        Wait for delay, then check actual price and update simulation
        
        This is the CRITICAL FIX: Waits for actual delay time, then checks
        real market price at that moment (which will exist in price history).
        
        Args:
            sim_id: Simulation ID
            trade_data: Trade data dict
            delay_seconds: Delay in seconds
        """
        # Wait for the delay (this is the key!)
        await asyncio.sleep(delay_seconds)
        
        # Now we're at T+delay, so prices should exist in history
        detection_time = self._parse_timestamp(trade_data['timestamp'])
        execution_time = detection_time + timedelta(seconds=delay_seconds)
        market_slug = trade_data['market']
        trade_size = float(trade_data['size'])
        
        # Get actual price at THIS moment (T+delay)
        actual_price = None
        price_source = 'fallback_detection'
        
        if self.price_lookup_func:
            try:
                # Look for price within last 2 minutes (should find recent price)
                # Use current time since we just waited
                current_time_str = datetime.now().isoformat() + 'Z'
                actual_price = self.price_lookup_func(market_slug, current_time_str)
                
                if actual_price is not None:
                    price_source = 'actual_lookup'
            except Exception as e:
                # If lookup fails, use fallback
                pass
        
        # Fallback to detection price if no price found
        if actual_price is None:
            actual_price = float(trade_data['price'])
        
        # Calculate slippage
        slippage_pct = self.slippage_calc.calculate_slippage(
            market_slug=market_slug,
            trade_size=trade_size,
            current_price=actual_price,
            market_state={'price': actual_price}
        )
        
        # Calculate entry price with slippage
        entry_price = actual_price * (1 + slippage_pct)
        
        # Create result for this delay
        result = {
            'delay_seconds': delay_seconds,
            'delay_minutes': delay_seconds / 60.0,
            'execution_time': execution_time.isoformat(),
            'market_state_at_entry': {
                'price': actual_price,
                'timestamp': datetime.now().isoformat(),
                'source': price_source
            },
            'simulated_entry_price': entry_price,
            'slippage_percent': slippage_pct * 100,
            'checked_at': datetime.now().isoformat(),
            'pnl': None,
            'pnl_pct': None,
            'resolved': False
        }
        
        # Load simulation file
        sim_file = self.storage_path / f"{sim_id}.json"
        try:
            with open(sim_file, 'r') as f:
                simulation = json.load(f)
        except Exception as e:
            print(f"⚠️ Failed to load simulation {sim_id}: {e}")
            return
        
        # Add result
        simulation['results'].append(result)
        
        # Update status
        expected_results = len(simulation.get('delays_scheduled', []))
        if len(simulation['results']) >= expected_results:
            simulation['status'] = 'completed'
            simulation['completed_at'] = datetime.now().isoformat()
        
        # Save updated simulation
        try:
            with open(sim_file, 'w') as f:
                json.dump(simulation, f, indent=2, default=str)
        except Exception as e:
            print(f"⚠️ Failed to save simulation {sim_id}: {e}")
            return
        
        # Log completion
        delay_min = delay_seconds // 60
        print(f"✅ Delay {delay_seconds}s (+{delay_min}min) check complete for {sim_id}")
        print(f"   Price: {actual_price:.6f} (source: {price_source})")
        print(f"   Entry: {entry_price:.6f} (slippage: {slippage_pct*100:.2f}%)")
        
        # Send Telegram notification
        if self.telegram_callback:
            status_icon = "✅" if simulation['status'] == 'completed' else "⏳"
            msg = (
                f"{status_icon} <b>Delay Check Complete</b>\n\n"
                f"🔬 Simulation: <code>{sim_id}</code>\n"
                f"⏰ Delay: +{delay_min}min ({delay_seconds}s)\n"
                f"📈 Price: {actual_price:.6f}\n"
                f"💰 Entry: {entry_price:.6f}\n"
                f"📊 Source: {price_source}\n\n"
            )
            if simulation['status'] == 'completed':
                msg += f"🎉 <b>All delay checks complete!</b>"
            else:
                remaining = expected_results - len(simulation['results'])
                msg += f"⏳ {remaining} check(s) remaining"
            
            try:
                await self.telegram_callback(msg)
            except:
                pass
    
    async def resolve_simulation(
        self,
        simulation: TradeSimulation,
        resolution_price: float,
        resolution_time: datetime
    ):
        """
        Calculate P&L when market resolves
        
        Args:
            simulation: TradeSimulation to resolve
            resolution_price: Final market price (0 or 1)
            resolution_time: When market resolved
        """
        for result in simulation.results:
            if result.resolved:
                continue
            
            # Calculate P&L
            # If we bought at result.entry_price, profit = resolution_price - entry_price
            pnl = resolution_price - result.entry_price
            pnl_pct = (pnl / result.entry_price) * 100 if result.entry_price > 0 else 0
            
            result.pnl = pnl
            result.pnl_pct = pnl_pct
            result.resolved = True
            result.resolution_time = resolution_time
        
        # Recalculate summary
        self._calculate_summary(simulation)
    
    def _calculate_summary(self, simulation: TradeSimulation):
        """Calculate summary metrics for simulation"""
        resolved_results = [r for r in simulation.results if r.resolved]
        
        if not resolved_results:
            return
        
        # Find best delay
        best_result = max(resolved_results, key=lambda r: r.pnl or -999)
        simulation.best_delay = best_result.delay_seconds
        
        # Check if profitable
        simulation.profitable = any(r.pnl and r.pnl > 0 for r in resolved_results)
        
        # Average P&L
        pnls = [r.pnl for r in resolved_results if r.pnl is not None]
        if pnls:
            simulation.avg_pnl = sum(pnls) / len(pnls)
    
    def _parse_timestamp(self, timestamp) -> datetime:
        """Parse timestamp from various formats"""
        if isinstance(timestamp, datetime):
            return timestamp
        elif isinstance(timestamp, (int, float)):
            return datetime.fromtimestamp(timestamp)
        elif isinstance(timestamp, str):
            if 'T' in timestamp:
                return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                return datetime.fromtimestamp(float(timestamp))
        else:
            return datetime.now()
