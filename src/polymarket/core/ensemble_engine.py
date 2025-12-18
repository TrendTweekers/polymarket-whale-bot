"""
Ensemble Engine - Combines multiple strategies with adaptive weighting
METHOD 4: The most powerful self-improvement system
"""

from typing import Dict, List, Tuple, Optional
from datetime import datetime
import json
import structlog
from pathlib import Path

log = structlog.get_logger()


class Strategy:
    """Base class for trading strategies"""
    
    def __init__(self, name: str):
        self.name = name
        self.trades_executed = []
        self.wins = 0
        self.losses = 0
    
    def evaluate(self, whale_data: Dict, market_data: Dict,
                bet_data: Dict, context_data: Dict) -> Tuple[bool, float]:
        """
        Evaluate if strategy recommends copying
        Returns: (should_copy, confidence)
        """
        raise NotImplementedError
    
    def win_rate(self) -> float:
        total = len(self.trades_executed)
        if total == 0:
            return 0.5
        return self.wins / total


class FastCopyStrategy(Strategy):
    """Copy whale within 2-5 minutes - capitalize on information edge"""
    
    def __init__(self):
        super().__init__("fast_copy")
    
    def evaluate(self, whale_data: Dict, market_data: Dict,
                bet_data: Dict, context_data: Dict) -> Tuple[bool, float]:
        
        # Check whale quality
        if whale_data.get('win_rate', 0) < 0.62:
            return False, 0.0
        
        # Check market has liquidity for fast execution
        if market_data.get('liquidity', 0) < 10000:
            return False, 0.0
        
        # Check time since whale trade
        minutes_elapsed = context_data.get('minutes_since_whale_trade', 999)
        if minutes_elapsed > 10:
            return False, 0.0
        
        # Fast copy approved
        confidence = 0.7 + (whale_data.get('win_rate', 0.5) - 0.62) * 2
        return True, min(confidence, 0.95)


class ConsensusStrategy(Strategy):
    """Wait for multiple whales to agree - reduces false positives"""
    
    def __init__(self, min_whales: int = 2):
        super().__init__("consensus")
        self.min_whales = min_whales
    
    def evaluate(self, whale_data: Dict, market_data: Dict,
                bet_data: Dict, context_data: Dict) -> Tuple[bool, float]:
        
        # Count whales on same side
        whales_same_side = context_data.get('num_whales_same_side', 0)
        whales_opposite_side = context_data.get('num_whales_opposite_side', 0)
        
        # Need multiple whales agreeing
        if whales_same_side < self.min_whales:
            return False, 0.0
        
        # Reject if conflicting signals
        if whales_opposite_side > 0:
            return False, 0.0
        
        # Consensus found
        confidence = 0.6 + (whales_same_side * 0.1)
        return True, min(confidence, 0.95)


class ContrarianStrategy(Strategy):
    """Copy when whale disagrees with crowd - information asymmetry"""
    
    def __init__(self):
        super().__init__("contrarian")
    
    def evaluate(self, whale_data: Dict, market_data: Dict,
                bet_data: Dict, context_data: Dict) -> Tuple[bool, float]:
        
        # Get sentiment
        sentiment = context_data.get('social_sentiment', 0.5)
        whale_direction = bet_data.get('direction', 'YES')
        
        # Whale buying YES, crowd bearish = contrarian signal
        if whale_direction == 'YES' and sentiment < 0.4:
            confidence = 0.75
            return True, confidence
        
        # Whale buying NO, crowd bullish = contrarian signal
        if whale_direction == 'NO' and sentiment > 0.6:
            confidence = 0.75
            return True, confidence
        
        # Not contrarian enough
        return False, 0.0


class MomentumExploitStrategy(Strategy):
    """Wait for price reversion after whale impact - get better entry"""
    
    def __init__(self):
        super().__init__("momentum")
    
    def evaluate(self, whale_data: Dict, market_data: Dict,
                bet_data: Dict, context_data: Dict) -> Tuple[bool, float]:
        
        # Get price movement
        price_before = context_data.get('price_before_whale', 0.5)
        price_current = market_data.get('current_price', 0.5)
        whale_direction = bet_data.get('direction', 'YES')
        
        # Calculate impact
        if whale_direction == 'YES':
            spike = price_current - price_before
            # Looking for reversion (price dropped back)
            if spike > 0.02 and price_current < (price_before + 0.015):  # Was 2%+, now reverted
                confidence = 0.70
                return True, confidence
        else:
            spike = price_before - price_current
            if spike > 0.02 and price_current > (price_before - 0.015):
                confidence = 0.70
                return True, confidence
        
        return False, 0.0


class EnsembleCopyingEngine:
    """
    Combines multiple strategies with adaptive weighting
    Learns which strategies work best and rebalances
    """
    
    def __init__(self, config: Dict, data_file: str = "data/ensemble_state.json"):
        self.data_file = data_file
        self.strategies: Dict[str, Strategy] = {}
        self.strategy_weights: Dict[str, float] = {}
        self.strategy_performance: Dict[str, List[bool]] = {}
        
        # Ensure data directory exists
        Path(data_file).parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize strategies from config
        ensemble_config = config.get('ensemble', {})
        strategies_config = ensemble_config.get('strategies', {})
        
        if strategies_config.get('fast_copy', {}).get('enabled', True):
            self.strategies['fast_copy'] = FastCopyStrategy()
            self.strategy_weights['fast_copy'] = strategies_config.get('fast_copy', {}).get('initial_weight', 0.25)
        
        if strategies_config.get('consensus', {}).get('enabled', True):
            min_whales = strategies_config.get('consensus', {}).get('min_whales', 2)
            self.strategies['consensus'] = ConsensusStrategy(min_whales)
            self.strategy_weights['consensus'] = strategies_config.get('consensus', {}).get('initial_weight', 0.25)
        
        if strategies_config.get('contrarian', {}).get('enabled', True):
            self.strategies['contrarian'] = ContrarianStrategy()
            self.strategy_weights['contrarian'] = strategies_config.get('contrarian', {}).get('initial_weight', 0.25)
        
        if strategies_config.get('momentum', {}).get('enabled', True):
            self.strategies['momentum'] = MomentumExploitStrategy()
            self.strategy_weights['momentum'] = strategies_config.get('momentum', {}).get('initial_weight', 0.25)
        
        # Initialize performance tracking
        for name in self.strategies:
            self.strategy_performance[name] = []
        
        self.rebalance_frequency = ensemble_config.get('rebalance_frequency', 10)
        self.min_strategy_trades = ensemble_config.get('min_strategy_trades', 5)
        
        self.load_state()
        
        log.info("ensemble_engine_initialized",
                strategies=list(self.strategies.keys()),
                weights=self.strategy_weights)
    
    def load_state(self):
        """Load saved ensemble state"""
        try:
            with open(self.data_file, 'r') as f:
                data = json.load(f)
                self.strategy_weights = data.get('weights', self.strategy_weights)
                self.strategy_performance = data.get('performance', self.strategy_performance)
                log.info("ensemble_state_loaded")
        except FileNotFoundError:
            log.info("no_saved_ensemble_state")
        except Exception as e:
            log.warning("ensemble_state_load_failed", error=str(e))
    
    def save_state(self):
        """Persist ensemble state"""
        try:
            data = {
                'weights': self.strategy_weights,
                'performance': self.strategy_performance,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log.error("ensemble_state_save_failed", error=str(e))
    
    def get_ensemble_decision(self, whale_data: Dict, market_data: Dict,
                             bet_data: Dict, context_data: Dict) -> Tuple[bool, float, Dict]:
        """
        Get weighted ensemble decision from all strategies
        Returns: (should_copy, confidence, strategy_votes)
        """
        votes = {}
        confidences = {}
        
        # Get each strategy's opinion
        for name, strategy in self.strategies.items():
            should_copy, confidence = strategy.evaluate(
                whale_data, market_data, bet_data, context_data
            )
            votes[name] = should_copy
            confidences[name] = confidence
        
        # Calculate weighted score
        total_weight = 0
        weighted_score = 0
        
        for name in self.strategies:
            if votes[name]:
                weight = self.strategy_weights[name]
                total_weight += weight
                weighted_score += weight * confidences[name]
        
        if total_weight == 0:
            return False, 0.0, votes
        
        final_confidence = weighted_score / total_weight
        should_copy = final_confidence > 0.60
        
        log.info("ensemble_decision",
                should_copy=should_copy,
                confidence=f"{final_confidence:.3f}",
                votes=votes,
                weights=self.strategy_weights)
        
        return should_copy, final_confidence, votes
    
    def update_strategy_performance(self, strategy_name: str, outcome: bool):
        """
        Record strategy performance and trigger rebalancing
        """
        if strategy_name not in self.strategy_performance:
            return
        
        self.strategy_performance[strategy_name].append(outcome)
        
        # Update strategy object
        if outcome:
            self.strategies[strategy_name].wins += 1
        else:
            self.strategies[strategy_name].losses += 1
        
        # Check if rebalancing needed
        total_trades = sum([len(p) for p in self.strategy_performance.values()])
        if total_trades % self.rebalance_frequency == 0:
            self.rebalance_weights()
    
    def rebalance_weights(self):
        """
        Reallocate weight to winning strategies
        This is the SELF-IMPROVEMENT magic
        """
        log.info("ensemble_rebalancing_weights")
        
        strategy_scores = {}
        
        for name, outcomes in self.strategy_performance.items():
            if len(outcomes) < self.min_strategy_trades:
                # Not enough data - keep neutral
                strategy_scores[name] = 0.5
                continue
            
            # Calculate recent performance (last 20 trades)
            recent = outcomes[-20:]
            win_rate = sum(recent) / len(recent)
            
            # Bonus for consistency
            if len(outcomes) > 20:
                consistency = 1.0 - (abs(win_rate - 0.5) * 0.2)
            else:
                consistency = 1.0
            
            strategy_scores[name] = win_rate * consistency
        
        # Normalize to sum to 1.0
        total_score = sum(strategy_scores.values())
        if total_score > 0:
            new_weights = {
                name: score / total_score
                for name, score in strategy_scores.items()
            }
            
            old_weights = self.strategy_weights.copy()
            self.strategy_weights = new_weights
            
            log.info("ensemble_weights_rebalanced")
            for name in self.strategies:
                log.info("strategy_weight_update",
                        strategy=name,
                        old_weight=f"{old_weights.get(name, 0):.3f}",
                        new_weight=f"{new_weights[name]:.3f}",
                        win_rate=f"{strategy_scores[name]:.3f}")
        
        self.save_state()
    
    def get_performance_summary(self) -> Dict:
        """Get current ensemble performance"""
        summary = {}
        for name, strategy in self.strategies.items():
            summary[name] = {
                'weight': self.strategy_weights[name],
                'trades': len(self.strategy_performance[name]),
                'win_rate': strategy.win_rate(),
                'wins': strategy.wins,
                'losses': strategy.losses
            }
        return summary
