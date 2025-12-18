"""
Bayesian Whale Scorer - Self-improving whale quality assessment
"""

from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
import json
import structlog

log = structlog.get_logger()


class WhaleScore:
    def __init__(self, whale_id: str, initial_score: float = 0.5):
        self.whale_id = whale_id
        self.score = initial_score
        self.confidence = 0.3  # Low confidence initially
        self.sample_size = 0
        self.wins = 0
        self.losses = 0
        self.total_pnl = 0.0
        self.recent_trades = []  # Last 20 trades
        self.last_updated = datetime.now()
        self.specialty_scores = {
            'politics': 0.5,
            'crypto': 0.5,
            'sports': 0.5,
            'finance': 0.5
        }
    
    def win_rate(self) -> float:
        if self.sample_size == 0:
            return 0.5
        return self.wins / self.sample_size
    
    def recent_win_rate(self) -> float:
        if not self.recent_trades:
            return 0.5
        return sum(self.recent_trades) / len(self.recent_trades)


class SelfImprovingWhaleScorer:
    """
    Bayesian update system for whale quality
    Learns which whales are actually profitable over time
    """
    
    def __init__(self, data_file: str = "data/whale_scores.json"):
        self.data_file = data_file
        self.whale_scores: Dict[str, WhaleScore] = {}
        self.load_scores()
        
        log.info("whale_scorer_initialized", whales_tracked=len(self.whale_scores))
    
    def load_scores(self):
        """Load saved whale scores from disk"""
        try:
            with open(self.data_file, 'r') as f:
                data = json.load(f)
                for whale_id, score_data in data.items():
                    whale_score = WhaleScore(whale_id)
                    whale_score.__dict__.update(score_data)
                    # Convert last_updated string back to datetime if needed
                    if isinstance(whale_score.last_updated, str):
                        try:
                            whale_score.last_updated = datetime.fromisoformat(whale_score.last_updated)
                        except:
                            whale_score.last_updated = datetime.now()
                    self.whale_scores[whale_id] = whale_score
        except FileNotFoundError:
            log.info("no_saved_scores_found", creating_new=True)
    
    def save_scores(self):
        """Persist whale scores to disk"""
        data = {}
        for whale_id, score in self.whale_scores.items():
            score_dict = {}
            for k, v in score.__dict__.items():
                if k != 'whale_id':
                    if isinstance(v, datetime):
                        score_dict[k] = v.isoformat()
                    else:
                        score_dict[k] = v
            data[whale_id] = score_dict
        
        with open(self.data_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    def get_or_create_score(self, whale_id: str) -> WhaleScore:
        """Get existing score or create new one"""
        if whale_id not in self.whale_scores:
            self.whale_scores[whale_id] = WhaleScore(whale_id)
        return self.whale_scores[whale_id]
    
    def calculate_initial_score(self, whale_data: Dict) -> float:
        """
        Calculate starting score from historical data
        Uses multiple factors, not just win rate
        """
        win_rate = whale_data.get('win_rate', 0.5)
        sharpe = whale_data.get('sharpe_ratio', 0.5)
        volume = whale_data.get('total_volume', 0)
        
        # Weighted combination
        score = (
            win_rate * 0.40 +
            min(sharpe / 2.0, 0.3) +  # Cap sharpe contribution
            min(volume / 100000, 0.3)  # Cap volume contribution
        )
        
        return max(0.1, min(score, 0.9))
    
    def update_score_after_outcome(self, whale_id: str, market_category: str,
                                   outcome_won: bool, pnl: float):
        """
        Bayesian update: adjust score based on new evidence
        Recent performance weighted more heavily
        """
        whale_score = self.get_or_create_score(whale_id)
        
        # Update counts
        whale_score.sample_size += 1
        if outcome_won:
            whale_score.wins += 1
        else:
            whale_score.losses += 1
        
        whale_score.total_pnl += pnl
        
        # Update recent trades (keep last 20)
        whale_score.recent_trades.append(1 if outcome_won else 0)
        if len(whale_score.recent_trades) > 20:
            whale_score.recent_trades.pop(0)
        
        # Bayesian update with recency weighting
        recent_win_rate = whale_score.recent_win_rate()
        overall_win_rate = whale_score.win_rate()
        
        # Weight recent performance 70%, historical 30%
        combined_win_rate = recent_win_rate * 0.7 + overall_win_rate * 0.3
        
        # Update score (exponential moving average)
        alpha = 0.15  # Learning rate
        old_score = whale_score.score
        
        if outcome_won:
            # Nudge score up
            whale_score.score = old_score * (1 - alpha) + alpha * min(combined_win_rate + 0.1, 1.0)
        else:
            # Nudge score down
            whale_score.score = old_score * (1 - alpha) + alpha * max(combined_win_rate - 0.1, 0.0)
        
        # Clamp score
        whale_score.score = max(0.1, min(whale_score.score, 0.95))
        
        # Increase confidence with more samples
        whale_score.confidence = min(
            0.95,
            0.3 + (whale_score.sample_size / 100) * 0.65
        )
        
        # Update category specialty
        if market_category in whale_score.specialty_scores:
            cat_score = whale_score.specialty_scores[market_category]
            if outcome_won:
                whale_score.specialty_scores[market_category] = min(cat_score + 0.05, 1.0)
            else:
                whale_score.specialty_scores[market_category] = max(cat_score - 0.05, 0.0)
        
        whale_score.last_updated = datetime.now()
        
        log.info("whale_score_updated",
                whale_id=whale_id,
                old_score=f"{old_score:.3f}",
                new_score=f"{whale_score.score:.3f}",
                confidence=f"{whale_score.confidence:.3f}",
                win_rate=f"{whale_score.win_rate():.3f}",
                sample_size=whale_score.sample_size)
        
        # Save periodically
        if whale_score.sample_size % 5 == 0:
            self.save_scores()
    
    def get_copy_decision(self, whale_id: str, market_category: str,
                         min_score: float = 0.70) -> Tuple[bool, float, str]:
        """
        Should we copy this whale in this market?
        Returns: (should_copy, confidence, reason)
        """
        whale_score = self.get_or_create_score(whale_id)
        
        # Check 1: Enough data?
        if whale_score.sample_size < 5:
            return False, 0.0, f"Insufficient data ({whale_score.sample_size} trades)"
        
        # Check 2: Low confidence whales need higher threshold
        if whale_score.confidence < 0.5:
            effective_threshold = min_score + 0.10
        else:
            effective_threshold = min_score
        
        # Check 3: Category specialty
        category_score = whale_score.specialty_scores.get(market_category, 0.5)
        if category_score < 0.55:
            return False, whale_score.score, f"Weak in {market_category} ({category_score:.2f})"
        
        # Check 4: Recent performance decay
        if whale_score.recent_win_rate() < 0.50 and whale_score.sample_size > 10:
            return False, whale_score.score, f"Recent performance declining ({whale_score.recent_win_rate():.2f})"
        
        # Check 5: Overall score
        if whale_score.score < effective_threshold:
            return False, whale_score.score, f"Score {whale_score.score:.2f} below threshold {effective_threshold:.2f}"
        
        # APPROVED
        return True, whale_score.score, f"Approved: score={whale_score.score:.2f}, confidence={whale_score.confidence:.2f}"
    
    def get_top_whales(self, n: int = 10, category: Optional[str] = None) -> List[Tuple[str, float]]:
        """Get top N whales by score"""
        whales = []
        for whale_id, score in self.whale_scores.items():
            if score.sample_size < 5:
                continue
            
            if category:
                whale_score_value = score.specialty_scores.get(category, 0.0)
            else:
                whale_score_value = score.score
            
            whales.append((whale_id, whale_score_value))
        
        whales.sort(key=lambda x: x[1], reverse=True)
        return whales[:n]
