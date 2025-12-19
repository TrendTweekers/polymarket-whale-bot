"""
Main Bot Orchestrator - Ties everything together
"""

import asyncio
import json
import aiohttp
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
import structlog

from .core.capital_tracker import CapitalEfficiencyTracker
from .core.whale_scorer import SelfImprovingWhaleScorer
from .core.ml_predictor import MLWhalePredictor
from .core.ensemble_engine import EnsembleCopyingEngine
from .filters.velocity_filter import VelocityFilter
from .filters.market_context_filter import MarketContextFilter
from .api.polymarket_client import PolymarketClient
from .notifications.telegram_notifier import TelegramNotifier
from .notifications.command_handler import CommandHandler
from .storage.trade_database import TradeDatabase

# Risk management (Kimi's requirements)
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
from src.risk import RiskManager

log = structlog.get_logger()


class WhaleBot:
    """
    Self-improving whale copy trading bot
    """
    
    def __init__(self, config: Dict):
        self.config = config
        
        # Core components
        self.capital_tracker = CapitalEfficiencyTracker(
            bankroll=config['trading']['bankroll'],
            max_days=config['trading']['max_days_to_resolution']
        )
        
        # Risk Manager (Kimi's requirements - hard limits)
        self.risk_manager = RiskManager(
            bankroll=config['trading']['bankroll']
        )
        
        self.whale_scorer = SelfImprovingWhaleScorer()
        self.ml_predictor = MLWhalePredictor()
        self.ensemble = EnsembleCopyingEngine(config)
        
        # Filters
        self.velocity_filter = VelocityFilter(
            min_days=config['trading']['min_days'],
            max_days=config['trading']['max_days_to_resolution'],
            preferred_days=config['trading']['preferred_days']
        )
        
        self.context_filter = MarketContextFilter(config['market_filters'])
        
        # API client
        self.api_client = PolymarketClient(config['api'])
        
        # Telegram notifications
        self.telegram = TelegramNotifier()
        
        # Command handler
        self.command_handler = CommandHandler(self, self.telegram)
        
        # Trade database
        self.db = TradeDatabase()
        
        # State
        self.active_trades: List[Dict] = []
        self.whale_watchlist: List[str] = []
        self.whale_metadata: Dict[str, Dict] = {}
        self.previous_positions: Dict[str, Dict] = {}  # Track previous positions for trade detection
        self.is_running = False
        
        # Daily reset task for risk manager
        self._daily_reset_task = None
        
        log.info("whale_bot_initialized",
                bankroll=config['trading']['bankroll'],
                max_days=config['trading']['max_days_to_resolution'])
    
    async def discover_and_load_whales(self):
        """
        Auto-discover active whales if needed, then load them
        """
        whale_file = Path("config/whale_list.json")
        
        # Check if we need to discover whales
        need_discovery = False
        
        if not whale_file.exists():
            log.info("whale_list_not_found", auto_discovering=True)
            need_discovery = True
        else:
            # Check if existing whales are stale (>7 days old)
            try:
                with open(whale_file, 'r') as f:
                    data = json.load(f)
                    whales = data.get('whales', [])
                    
                    if not whales:
                        need_discovery = True
                    else:
                        # Check discovery date
                        discovered = whales[0].get('discovered', '')
                        if discovered:
                            try:
                                discovery_date = datetime.fromisoformat(discovered)
                                if (datetime.now() - discovery_date).days > 7:
                                    log.info("whale_list_stale", auto_refreshing=True)
                                    need_discovery = True
                            except Exception:
                                # Invalid date format, rediscover
                                need_discovery = True
                        else:
                            # No discovery date, rediscover
                            need_discovery = True
            except Exception as e:
                log.warning("whale_list_read_error", error=str(e), discovering=True)
                need_discovery = True
        
        # Auto-discover if needed
        if need_discovery:
            try:
                await self.telegram.send_message(
                    "🔍 <b>Auto-discovering active whales...</b>\n\nThis may take 30-60 seconds..."
                )
            except Exception:
                pass  # Telegram might not be configured
            
            whales = await self.auto_discover_whales()
            
            if whales:
                # Save to file
                whale_file.parent.mkdir(parents=True, exist_ok=True)
                with open(whale_file, 'w') as f:
                    json.dump({'whales': whales, 'discovery_settings': {
                        'min_volume_usd': 100000,
                        'min_trades': 50,
                        'min_win_rate': 0.55,
                        'lookback_days': 90
                    }}, f, indent=2)
                
                log.info("whales_discovered_and_saved", count=len(whales))
                try:
                    await self.telegram.send_message(
                        f"✅ <b>Discovered {len(whales)} active whales!</b>\n\nStarting monitoring..."
                    )
                except Exception:
                    pass
            else:
                log.error("whale_discovery_failed", using_defaults=True)
                try:
                    await self.telegram.send_message(
                        "⚠️ <b>Auto-discovery had issues</b>\n\nUsing default whale list..."
                    )
                except Exception:
                    pass
        
        # Now load the whales
        await self.load_whale_watchlist()
    
    async def auto_discover_whales(self) -> list:
        """
        Automatically discover top active whales
        Uses multiple methods to find the best traders
        """
        log.info("auto_discovery_started")
        
        discovered_whales = []
        
        # Method 1: Try Polymarket leaderboard API
        try:
            url = "https://api.polymarket.com/leaderboard"
            params = {'period': '7d', 'limit': 20}
            
            # Create a temporary session for discovery
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        leaderboard = data.get('leaderboard', [])
                        
                        for i, trader in enumerate(leaderboard[:10], 1):
                            address = trader.get('wallet_address', trader.get('address'))
                            if address and address != '0x0000000000000000000000000000000000000000':
                                discovered_whales.append({
                                    'address': address,
                                    'name': f"Top Trader #{i}",
                                    'volume_7d': float(trader.get('volume', 0)),
                                    'pnl_7d': float(trader.get('pnl', 0)),
                                    'num_trades': trader.get('trades', 0),
                                    'source': 'leaderboard',
                                    'discovered': datetime.now().isoformat(),
                                    'known_win_rate': 0.65,
                                    'specialty': ['unknown'],
                                    'avg_bet_size': 20000
                                })
                        
                        if discovered_whales:
                            log.info("leaderboard_discovery_success", count=len(discovered_whales))
                            return discovered_whales
        
        except Exception as e:
            log.warning("leaderboard_discovery_failed", error=str(e))
        
        # Method 2: Scan recent market activity
        try:
            log.info("scanning_market_activity")
            
            # Get active markets
            markets_data = await self.api_client.get_markets(limit=20)
            
            whale_activity = {}  # Track volume per address
            
            for market in markets_data[:10]:
                market_id = market.get('id', market.get('condition_id'))
                
                if not market_id:
                    continue
                
                # Get recent trades
                try:
                    trades = await self.api_client.get_recent_trades(market_id, limit=100)
                    
                    for trade in trades:
                        address = trade.get('user', trade.get('address', trade.get('maker')))
                        size = float(trade.get('size', trade.get('amount', 0)))
                        
                        if address and size > 500:  # Trades over $500
                            if address not in whale_activity:
                                whale_activity[address] = {'volume': 0, 'trades': 0}
                            whale_activity[address]['volume'] += size
                            whale_activity[address]['trades'] += 1
                
                except Exception as e:
                    log.debug("market_scan_error", market=market_id[:10], error=str(e))
                    continue
            
            # Sort by volume
            sorted_whales = sorted(
                whale_activity.items(),
                key=lambda x: x[1]['volume'],
                reverse=True
            )
            
            # Take top 10
            for i, (address, data) in enumerate(sorted_whales[:10], 1):
                if address != '0x0000000000000000000000000000000000000000':
                    discovered_whales.append({
                        'address': address,
                        'name': f"Active Trader #{i}",
                        'recent_volume': data['volume'],
                        'recent_trades': data['trades'],
                        'source': 'market_activity',
                        'discovered': datetime.now().isoformat(),
                        'known_win_rate': 0.65,
                        'specialty': ['unknown'],
                        'avg_bet_size': 20000
                    })
            
            if discovered_whales:
                log.info("market_scan_success", count=len(discovered_whales))
                return discovered_whales
        
        except Exception as e:
            log.error("market_scan_failed", error=str(e))
        
        # Method 3: Fallback to subgraph top users
        try:
            log.info("trying_subgraph_discovery")
            
            subgraph_url = "https://api.goldsky.com/api/public/project_cl6mb8i9h0003e201j6li0diw/subgraphs/positions-subgraph/0.0.7/gn"
            
            query = """
            query TopUsers {
                netUserBalances(
                    first: 20,
                    orderBy: balance,
                    orderDirection: desc
                ) {
                    user
                    balance
                }
            }
            """
            
            async with aiohttp.ClientSession() as session:
                async with session.post(subgraph_url, json={'query': query}) as response:
                    if response.status == 200:
                        data = await response.json()
                        users = data.get('data', {}).get('netUserBalances', [])
                        
                        for i, user_data in enumerate(users[:10], 1):
                            address = user_data.get('user')
                            balance = float(user_data.get('balance', 0)) / 1e18  # Convert from wei
                            
                            if address and address != '0x0000000000000000000000000000000000000000':
                                discovered_whales.append({
                                    'address': address,
                                    'name': f"Trader #{i}",
                                    'balance': balance,
                                    'source': 'subgraph',
                                    'discovered': datetime.now().isoformat(),
                                    'known_win_rate': 0.65,
                                    'specialty': ['unknown'],
                                    'avg_bet_size': 20000
                                })
                        
                        if discovered_whales:
                            log.info("subgraph_discovery_success", count=len(discovered_whales))
                            return discovered_whales
        
        except Exception as e:
            log.error("subgraph_discovery_failed", error=str(e))
        
        # If all methods failed, return empty list
        log.error("all_discovery_methods_failed")
        return []
    
    async def load_whale_watchlist(self):
        """
        Load whale addresses to monitor from config
        """
        try:
            whale_file = Path("config/whale_list.json")
            
            if whale_file.exists():
                with open(whale_file, 'r') as f:
                    data = json.load(f)
                    whales = data.get('whales', [])
                    
                    self.whale_watchlist = [w['address'] for w in whales]
                    self.whale_metadata = {w['address']: w for w in whales}
                    
                    log.info("whale_watchlist_loaded",
                            count=len(self.whale_watchlist),
                            whales=[w.get('name', w['address'][:10]) for w in whales])
                    
                    # Notify via Telegram
                    try:
                        whale_names = "\n".join([f"• {w.get('name', 'Unknown')}" for w in whales[:10]])
                        await self.telegram.send_message(
                            f"🐋 <b>Monitoring {len(self.whale_watchlist)} Whales</b>\n\n{whale_names}"
                        )
                    except Exception as e:
                        log.warning("whale_notification_failed", error=str(e))
            else:
                log.warning("whale_list_not_found", creating_default=True)
                self.whale_watchlist = []
        
        except Exception as e:
            log.error("whale_list_load_error", error=str(e))
            self.whale_watchlist = []
    
    async def evaluate_trade_opportunity(self, whale_data: Dict, market_data: Dict,
                                        bet_data: Dict) -> Dict:
        """
        Full evaluation pipeline for a potential trade
        """
        
        evaluation = {
            'should_trade': False,
            'confidence': 0.0,
            'reasons': [],
            'filters_passed': {},
            'scores': {}
        }
        
        # FILTER 1: Velocity (1-5 days only)
        velocity_ok, velocity_score, velocity_reason = self.velocity_filter.check_market(market_data)
        evaluation['filters_passed']['velocity'] = velocity_ok
        evaluation['scores']['velocity'] = velocity_score
        evaluation['reasons'].append(velocity_reason)
        
        if not velocity_ok:
            log.info("trade_rejected_velocity", reason=velocity_reason)
            return evaluation
        
        # FILTER 2: Market context (liquidity, spread, whale specialty)
        context_ok, context_reason = self.context_filter.check_whale_market_fit(whale_data, market_data)
        evaluation['filters_passed']['context'] = context_ok
        evaluation['reasons'].append(context_reason)
        
        if not context_ok:
            log.info("trade_rejected_context", reason=context_reason)
            return evaluation
        
        # FILTER 3: Capital availability
        position_size = self.calculate_position_size(whale_data, market_data, velocity_score)
        can_trade, capital_reason = self.capital_tracker.should_take_position(
            amount=position_size,
            days_to_resolve=market_data.get('days_until_resolution', 3),
            whale_id=whale_data['whale_id']
        )
        evaluation['filters_passed']['capital'] = can_trade
        evaluation['reasons'].append(capital_reason)
        
        if not can_trade:
            log.info("trade_rejected_capital", reason=capital_reason)
            return evaluation
        
        # FILTER 4: Risk Manager (Kimi's hard limits)
        risk_allowed, risk_reason = self.risk_manager.can_trade(position_size)
        
        evaluation['filters_passed']['risk'] = risk_allowed
        evaluation['reasons'].append(risk_reason)
        
        if not risk_allowed:
            log.warning("trade_rejected_risk",
                       reason=risk_reason,
                       position_size=position_size,
                       risk_status=self.risk_manager.get_risk_status())
            
            # Send Telegram alert if kill switch activated
            if self.risk_manager.kill_switch_active:
                try:
                    await self.telegram.send_message(
                        f"🚨 <b>KILL SWITCH ACTIVATED</b>\n\n"
                        f"Reason: {risk_reason}\n"
                        f"Daily P&L: ${self.risk_manager.daily_pnl:.2f}\n"
                        f"Trading halted until daily reset."
                    )
                except:
                    pass
            
            return evaluation
        
        # SCORING 1: Bayesian whale score
        market_category = market_data.get('category', 'unknown')
        bayesian_ok, bayesian_score, bayesian_reason = self.whale_scorer.get_copy_decision(
            whale_data['whale_id'],
            market_category,
            min_score=self.config['risk_management']['min_whale_score']
        )
        evaluation['scores']['bayesian'] = bayesian_score
        evaluation['reasons'].append(bayesian_reason)
        
        if not bayesian_ok:
            log.info("trade_rejected_bayesian", reason=bayesian_reason)
            return evaluation
        
        # SCORING 2: ML prediction
        context_data = self.build_context_data(market_data, bet_data)
        ml_ok, ml_prob = self.ml_predictor.predict_should_copy(
            whale_data, market_data, bet_data, context_data
        )
        evaluation['scores']['ml_probability'] = ml_prob
        
        if ml_prob < self.config['risk_management']['min_ml_confidence']:
            log.info("trade_rejected_ml", probability=ml_prob)
            return evaluation
        
        # SCORING 3: Ensemble strategies
        ensemble_ok, ensemble_conf, strategy_votes = self.ensemble.get_ensemble_decision(
            whale_data, market_data, bet_data, context_data
        )
        evaluation['scores']['ensemble'] = ensemble_conf
        evaluation['strategy_votes'] = strategy_votes
        
        if not ensemble_ok or ensemble_conf < self.config['risk_management']['min_ensemble_confidence']:
            log.info("trade_rejected_ensemble", confidence=ensemble_conf)
            return evaluation
        
        # CALCULATE FINAL SCORE
        final_score = (
            bayesian_score * 0.30 +
            ml_prob * 0.30 +
            ensemble_conf * 0.40
        )
        
        evaluation['should_trade'] = True
        evaluation['confidence'] = final_score
        evaluation['position_size'] = position_size
        evaluation['reasons'].append(f"APPROVED: Final score {final_score:.3f}")
        
        log.info("trade_approved",
                whale_id=whale_data['whale_id'],
                market_id=market_data['market_id'],
                confidence=f"{final_score:.3f}",
                size=position_size)
        
        # Notify evaluation result
        try:
            await self.telegram.notify_trade_evaluation(evaluation, whale_data, market_data)
        except Exception as e:
            log.warning("evaluation_notification_failed", error=str(e))
        
        return evaluation
    
    def calculate_position_size(self, whale_data: Dict, market_data: Dict, velocity_score: float) -> float:
        """
        Calculate position size based on confidence and velocity
        """
        base_size = self.config['trading']['bankroll'] * self.config['trading']['max_position_size']
        
        # Adjust based on velocity score
        # Faster resolution = can size bigger (faster turnover)
        size_multiplier = 0.5 + (velocity_score * 0.5)  # 0.5x to 1.0x
        
        position_size = base_size * size_multiplier
        
        # Cap at configured max
        max_size = self.config['trading']['bankroll'] * self.config['trading']['max_position_size']
        
        return min(position_size, max_size)
    
    def build_context_data(self, market_data: Dict, bet_data: Dict) -> Dict:
        """
        Build context data for strategies and ML
        """
        return {
            'num_whales_same_side': 1,  # Placeholder - count from active monitoring
            'num_whales_opposite_side': 0,
            'minutes_since_whale_trade': 5,  # Placeholder
            'price_before_whale': market_data.get('current_price', 0.5) - 0.01,  # Placeholder
            'social_sentiment': 0.5,  # Placeholder - would come from Twitter API
            'market_momentum': 0.0,
            'whale_category_score': 0.65
        }
    
    async def execute_trade(self, evaluation: Dict, whale_data: Dict,
                          market_data: Dict, bet_data: Dict):
        """
        Execute approved trade (paper trading for now)
        """
        
        trade_record = {
            'trade_id': f"trade_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            'timestamp': datetime.now().isoformat(),
            'whale_id': whale_data['whale_id'],
            'whale_name': self.whale_metadata.get(whale_data['whale_id'], {}).get('name', 'Unknown'),
            'market_id': market_data['market_id'],
            'market_question': market_data.get('question', 'Unknown'),
            'direction': bet_data['direction'],
            'position_size': evaluation['position_size'],
            'entry_price': bet_data.get('entry_price', 0.5),
            'confidence': evaluation['confidence'],
            'evaluation': evaluation,
            'status': 'active'
        }
        
        # Add position to capital tracker
        resolution_date = market_data.get('end_date', datetime.now())
        if isinstance(resolution_date, str):
            resolution_date = datetime.fromisoformat(resolution_date.replace('Z', '+00:00'))
        
        self.capital_tracker.add_position(
            market_id=market_data['market_id'],
            amount=evaluation['position_size'],
            resolution_date=resolution_date,
            whale_id=whale_data['whale_id']
        )
        
        # Add position to Risk Manager (Kimi's requirement)
        side = 'YES' if bet_data.get('direction') == 'YES' else 'NO'
        risk_success, risk_msg = self.risk_manager.add_position(
            market_slug=market_data.get('slug', market_data['market_id']),
            entry_price=bet_data.get('entry_price', 0.5),
            size=evaluation['position_size'],
            side=side,
            whale_address=whale_data['whale_id']
        )
        
        if not risk_success:
            log.error("risk_manager_add_position_failed",
                     reason=risk_msg,
                     trade_id=trade_record['trade_id'])
            # This shouldn't happen if can_trade() passed, but log it anyway
        
        # Save to database
        self.db.add_trade(trade_record)
        
        self.active_trades.append(trade_record)
        
        log.info("trade_executed",
                trade_id=trade_record['trade_id'],
                market=market_data.get('question', 'Unknown'),
                size=evaluation['position_size'],
                confidence=evaluation['confidence'])
        
        # Notify via Telegram
        try:
            await self.telegram.notify_trade_executed(trade_record)
        except Exception as e:
            log.warning("trade_execution_notification_failed", error=str(e))
        
        # TODO: Actual execution via Polymarket API would go here
        # For now, this is paper trading
    
    async def record_trade_outcome(self, trade_id: str, outcome: bool, pnl: float):
        """
        Record trade result and update all learning systems
        """
        
        # Find trade
        trade = next((t for t in self.active_trades if t['trade_id'] == trade_id), None)
        if not trade:
            log.warning("trade_not_found", trade_id=trade_id)
            return
        
        # Update database
        self.db.update_trade_outcome(trade_id, outcome, pnl)
        
        # Update capital tracker
        self.capital_tracker.close_position(trade['market_id'], pnl)
        
        # Record trade outcome in Risk Manager (Kimi's requirement)
        market_slug = trade.get('market_id', '')
        exit_price = 1.0 if outcome else 0.0
        
        risk_closed, risk_pnl = self.risk_manager.close_position(
            market_slug=market_slug,
            exit_price=exit_price
        )
        
        if risk_closed:
            log.info("risk_manager_trade_closed",
                    trade_id=trade_id,
                    pnl=risk_pnl,
                    daily_pnl=self.risk_manager.daily_pnl)
        else:
            # Position not found in risk manager (might have been added before integration)
            # Record manually
            self.risk_manager.record_trade(
                size=trade.get('position_size', 0),
                pnl=pnl,
                market_slug=market_slug
            )
            log.info("risk_manager_trade_recorded_manually",
                    trade_id=trade_id,
                    pnl=pnl)
        
        # Check if kill switch activated after this trade
        if self.risk_manager.kill_switch_active:
            log.warning("kill_switch_activated_after_trade",
                       trade_id=trade_id,
                       daily_pnl=self.risk_manager.daily_pnl)
            try:
                await self.telegram.send_message(
                    f"🚨 <b>KILL SWITCH ACTIVATED</b>\n\n"
                    f"After trade: {trade_id}\n"
                    f"Daily P&L: ${self.risk_manager.daily_pnl:.2f}\n"
                    f"Trading halted until daily reset."
                )
            except:
                pass
        
        # Update whale scorer
        market_category = 'unknown'  # Would get from market_data
        self.whale_scorer.update_score_after_outcome(
            trade['whale_id'],
            market_category,
            outcome,
            pnl
        )
        
        # Update ML predictor
        whale_data = {'whale_id': trade['whale_id']}
        market_data = {'market_id': trade['market_id']}
        bet_data = {'direction': trade['direction']}
        context_data = {}
        
        self.ml_predictor.add_training_example(
            whale_data, market_data, bet_data, context_data, outcome
        )
        
        # Update ensemble strategies
        strategy_used = trade['evaluation'].get('strategy_votes', {})
        for strategy, voted in strategy_used.items():
            if voted:
                self.ensemble.update_strategy_performance(strategy, outcome)
        
        # Mark trade complete
        trade['status'] = 'completed'
        trade['outcome'] = outcome
        trade['pnl'] = pnl
        trade['closed_at'] = datetime.now().isoformat()
        
        # Calculate duration
        duration_days = (datetime.now() - datetime.fromisoformat(trade['timestamp'])).days
        
        log.info("trade_outcome_recorded",
                trade_id=trade_id,
                outcome='WIN' if outcome else 'LOSS',
                pnl=pnl)
        
        # Notify via Telegram
        try:
            await self.telegram.notify_trade_outcome(trade_id, outcome, pnl, duration_days)
        except Exception as e:
            log.warning("outcome_notification_failed", error=str(e))
    
    async def monitoring_loop(self):
        """
        Main monitoring loop - checks for REAL whale activity
        """
        log.info("monitoring_loop_started", whales=len(self.whale_watchlist))
        
        # Track previous positions for each whale
        previous_positions = {whale: {'positions_dict': {}} 
                            for whale in self.whale_watchlist}
        
        poll_interval = self.config['api']['poll_interval']
        
        last_daily_summary = datetime.now().date()
        last_command_check = datetime.now()
        
        while self.is_running:
            try:
                # Check for Telegram commands every 3 seconds
                if (datetime.now() - last_command_check).total_seconds() >= 3:
                    await self.command_handler.process_updates()
                    last_command_check = datetime.now()
                
                # Check if new day - send daily summary
                current_date = datetime.now().date()
                if current_date > last_daily_summary:
                    self.db.log_daily_summary()
                    await self.send_daily_summary()
                    last_daily_summary = current_date
                
                async with self.api_client as client:
                    # Check each whale
                    for whale_address in self.whale_watchlist:
                        # Get current positions
                        current = await client.get_wallet_positions(whale_address)
                        
                        # Detect new trades
                        new_trades = await client.detect_whale_trades(
                            whale_address,
                            previous_positions[whale_address]
                        )
                        
                        # Process new trades
                        for trade in new_trades:
                            log.info("whale_trade_detected",
                                    whale=whale_address[:10],
                                    market=trade['market_id'][:10],
                                    size=trade['size'])
                            
                            # Notify via Telegram
                            whale_meta = self.whale_metadata.get(whale_address, {})
                            await self.telegram.notify_whale_detected(
                                whale_data={'whale_id': whale_address, **whale_meta},
                                market_data=trade['market_data'],
                                bet_data=trade
                            )
                            
                            # Evaluate the trade
                            await self.process_whale_trade(trade)
                        
                        # Update previous positions
                        # Subgraph returns positions with nested market structure
                        previous_positions[whale_address] = {
                            'positions_dict': {
                                pos['market']['id']: pos 
                                for pos in current['positions']
                            }
                        }
                
                # Check active positions
                await self.check_active_positions()
                
                # Wait before next poll
                await asyncio.sleep(poll_interval)
            
            except Exception as e:
                log.error("monitoring_loop_error", error=str(e))
                await self.telegram.notify_error("monitoring_loop", str(e))
                await asyncio.sleep(poll_interval)
    
    async def process_whale_trade(self, trade: Dict):
        """
        Process detected whale trade through evaluation pipeline
        """
        try:
            # Use market_data from trade (already fetched from Subgraph)
            trade_market_data = trade.get('market_data', {})
            
            # Build data structures
            whale_address = trade['whale_address']
            whale_meta = self.whale_metadata.get(whale_address, {})
            
            # Handle specialty as either string or list
            specialty = whale_meta.get('specialty', ['unknown'])
            if isinstance(specialty, str):
                # Convert string to list (split by common delimiters or use as single item)
                if '&' in specialty or 'and' in specialty.lower():
                    specialty_list = [s.strip().lower() for s in specialty.replace('&', ',').replace('and', ',').split(',')]
                else:
                    specialty_list = [specialty.lower()]
            else:
                specialty_list = [s.lower() if isinstance(s, str) else str(s).lower() for s in specialty]
            
            whale_data = {
                'whale_id': whale_address,
                'win_rate': whale_meta.get('known_win_rate', 0.65),
                'avg_bet_size': whale_meta.get('avg_bet_size', trade.get('size', 20000)),
                'specialty_scores': {
                    cat: 0.65 for cat in specialty_list
                }
            }
            
            # Calculate days until resolution from market data
            end_date_str = trade_market_data.get('end_date')
            if end_date_str:
                if isinstance(end_date_str, str):
                    # Handle timestamp format from Subgraph
                    try:
                        end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                    except:
                        # Try Unix timestamp
                        try:
                            end_date = datetime.fromtimestamp(int(end_date_str))
                        except:
                            end_date = datetime.now()
                else:
                    end_date = end_date_str
                days_until_resolution = (end_date - datetime.now()).days
            else:
                days_until_resolution = 3  # Default
            
            market_data = {
                'market_id': trade['market_id'],
                'question': trade_market_data.get('question', 'Unknown'),
                'category': 'unknown',  # Subgraph doesn't provide category directly
                'end_date': end_date_str if end_date_str else datetime.now().isoformat(),
                'days_until_resolution': days_until_resolution,
                'liquidity': trade_market_data.get('liquidity', 0),
                'volume_24h': 0,  # Would need separate query
                'current_price': trade.get('price', 0.5)
            }
            
            bet_data = {
                'direction': trade['direction'],
                'amount': trade['size'],
                'entry_price': trade['price'],
                'size_pct_of_bankroll': trade['size'] / self.config['trading']['bankroll']
            }
            
            # Evaluate
            evaluation = await self.evaluate_trade_opportunity(
                whale_data, market_data, bet_data
            )
            
            # If approved, log it (paper trade)
            if evaluation['should_trade']:
                await self.execute_trade(evaluation, whale_data, market_data, bet_data)
        
        except Exception as e:
            log.error("process_whale_trade_error", error=str(e), trade=trade)
    
    async def check_active_positions(self):
        """
        Check if any active positions should be closed
        """
        # Check for position updates and close if needed
        # Placeholder implementation
        pass
    
    async def handle_telegram_commands(self):
        """
        Process incoming Telegram commands
        """
        try:
            await self.command_handler.process_updates()
        except Exception as e:
            log.warning("telegram_command_error", error=str(e))
    
    async def start(self):
        """Start the bot with auto-discovery"""
        self.is_running = True
        
        # Send startup notification
        try:
            await self.telegram.notify_bot_started(self.config)
        except Exception as e:
            log.warning("startup_notification_failed", error=str(e))
        
        # Auto-discover and load whales (replaces load_whale_watchlist)
        await self.discover_and_load_whales()
        
        # Start monitoring
        await self.monitoring_loop()
    
    async def stop(self):
        """Stop the bot"""
        self.is_running = False
        
        # Cancel daily reset task
        if self._daily_reset_task:
            self._daily_reset_task.cancel()
            try:
                await self._daily_reset_task
            except asyncio.CancelledError:
                pass
        
        # Log final risk status
        risk_status = self.risk_manager.get_risk_status()
        log.info("risk_manager_final_status",
                daily_pnl=risk_status['daily_pnl'],
                active_positions=risk_status['active_positions'],
                total_trades=risk_status['total_trades'],
                bankroll=risk_status['bankroll'])
        
        log.info("bot_stopped")
    
    def get_performance_summary(self) -> Dict:
        """Get comprehensive performance summary"""
        risk_status = self.risk_manager.get_risk_status()
        
        return {
            'database_stats': self.db.get_stats_summary(),
            'capital_metrics': self.capital_tracker.get_velocity_metrics(),
            'ensemble_performance': self.ensemble.get_performance_summary(),
            'active_trades': len(self.active_trades),
            'top_whales': self.whale_scorer.get_top_whales(5),
            'risk_status': {
                'daily_pnl': risk_status['daily_pnl'],
                'bankroll': risk_status['bankroll'],
                'active_positions': risk_status['active_positions'],
                'max_positions': risk_status['max_positions'],
                'kill_switch_active': risk_status['kill_switch_active'],
                'remaining_loss_capacity': risk_status['remaining_loss_capacity']
            }
        }
    
    async def send_daily_summary(self):
        """Send daily performance summary"""
        try:
            # Log daily summary to database
            self.db.log_daily_summary()
            
            # Send Telegram notification
            summary = self.get_performance_summary()
            await self.telegram.notify_daily_summary(summary)
        except Exception as e:
            log.warning("daily_summary_failed", error=str(e))
