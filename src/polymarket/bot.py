"""
Main Bot Orchestrator - Ties everything together
"""

import asyncio
from typing import Dict, List, Optional
from datetime import datetime
import structlog

from .core.capital_tracker import CapitalEfficiencyTracker
from .core.whale_scorer import SelfImprovingWhaleScorer
from .core.ml_predictor import MLWhalePredictor
from .core.ensemble_engine import EnsembleCopyingEngine
from .filters.velocity_filter import VelocityFilter
from .filters.market_context_filter import MarketContextFilter
from .api.polymarket_client import PolymarketClient

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
        
        # State
        self.active_trades: List[Dict] = []
        self.whale_watchlist: List[str] = []
        self.is_running = False
        
        log.info("whale_bot_initialized",
                bankroll=config['trading']['bankroll'],
                max_days=config['trading']['max_days_to_resolution'])
    
    async def load_whale_watchlist(self):
        """
        Load whale addresses to monitor
        In production, this would come from a database or configuration
        """
        # Placeholder - you'd load this from config/whale_list.json
        self.whale_watchlist = [
            # Add whale addresses here
            # "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
            # "0x..."
        ]
        
        log.info("whale_watchlist_loaded", count=len(self.whale_watchlist))
    
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
            'market_id': market_data['market_id'],
            'direction': bet_data['direction'],
            'position_size': evaluation['position_size'],
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
        
        self.active_trades.append(trade_record)
        
        log.info("trade_executed",
                trade_id=trade_record['trade_id'],
                market=market_data.get('question', 'Unknown'),
                size=evaluation['position_size'],
                confidence=evaluation['confidence'])
        
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
        
        # Update capital tracker
        self.capital_tracker.close_position(trade['market_id'], pnl)
        
        # Update whale scorer
        market_category = 'unknown'  # Would get from market_data
        self.whale_scorer.update_score_after_outcome(
            trade['whale_id'],
            market_category,
            outcome,
            pnl
        )
        
        # Update ML predictor
        whale_data = {'whale_id': trade['whale_id']}  # Would be full data
        market_data = {'market_id': trade['market_id']}
        bet_data = {'direction': trade['direction']}
        context_data = {}
        
        self.ml_predictor.add_training_example(
            whale_data, market_data, bet_data, context_data, outcome
        )
        
        # Update ensemble strategies
        # This would track which strategy recommended the trade
        strategy_used = trade['evaluation'].get('strategy_votes', {})
        for strategy, voted in strategy_used.items():
            if voted:
                self.ensemble.update_strategy_performance(strategy, outcome)
        
        # Mark trade complete
        trade['status'] = 'completed'
        trade['outcome'] = outcome
        trade['pnl'] = pnl
        trade['closed_at'] = datetime.now().isoformat()
        
        log.info("trade_outcome_recorded",
                trade_id=trade_id,
                outcome='WIN' if outcome else 'LOSS',
                pnl=pnl)
    
    async def monitoring_loop(self):
        """
        Main monitoring loop - checks for whale activity
        """
        log.info("monitoring_loop_started")
        
        poll_interval = self.config['api']['poll_interval']
        
        while self.is_running:
            try:
                async with self.api_client as client:
                    # Monitor whale wallets
                    whale_activities = await client.monitor_whale_wallets(self.whale_watchlist)
                    
                    for activity in whale_activities:
                        # Process each whale's new positions
                        await self.process_whale_activity(activity)
                
                # Check active positions for updates
                await self.check_active_positions()
                
                # Wait before next poll
                await asyncio.sleep(poll_interval)
            
            except Exception as e:
                log.error("monitoring_loop_error", error=str(e))
                await asyncio.sleep(poll_interval)
    
    async def process_whale_activity(self, activity: Dict):
        """
        Process detected whale activity
        """
        # This is where you'd detect new whale trades and evaluate them
        # Placeholder implementation
        pass
    
    async def check_active_positions(self):
        """
        Check if any active positions should be closed
        """
        # Check for position updates and close if needed
        # Placeholder implementation
        pass
    
    async def start(self):
        """Start the bot"""
        self.is_running = True
        await self.load_whale_watchlist()
        await self.monitoring_loop()
    
    async def stop(self):
        """Stop the bot"""
        self.is_running = False
        log.info("bot_stopped")
    
    def get_performance_summary(self) -> Dict:
        """Get comprehensive performance summary"""
        return {
            'capital_metrics': self.capital_tracker.get_velocity_metrics(),
            'ensemble_performance': self.ensemble.get_performance_summary(),
            'active_trades': len(self.active_trades),
            'completed_trades': len([t for t in self.active_trades if t['status'] == 'completed']),
            'top_whales': self.whale_scorer.get_top_whales(5)
        }
