"""
Machine Learning Predictor - Learns which trade features predict success
"""

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import pickle
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import structlog
from pathlib import Path

log = structlog.get_logger()


class MLWhalePredictor:
    """
    Learns which features predict successful whale copies
    Self-improves as more data is collected
    """
    
    def __init__(self, model_file: str = "data/ml_model.pkl"):
        self.model_file = model_file
        self.model = LogisticRegression(max_iter=1000)
        self.scaler = StandardScaler()
        self.training_data: List[Dict] = []
        self.is_trained = False
        self.feature_names = [
            'whale_win_rate', 'whale_sharpe', 'whale_volume',
            'whale_days_active', 'whale_recent_win_rate',
            'market_price', 'market_volume_24h', 'market_liquidity',
            'days_until_resolution', 'market_num_traders',
            'bet_size_pct', 'entry_price', 'hours_to_close',
            'num_other_whales_same_side', 'market_momentum',
            'whale_category_score'
        ]
        
        # Ensure data directory exists
        Path(model_file).parent.mkdir(parents=True, exist_ok=True)
        
        self.load_model()
        
        log.info("ml_predictor_initialized", 
                is_trained=self.is_trained,
                training_samples=len(self.training_data))
    
    def load_model(self):
        """Load saved model from disk"""
        try:
            with open(self.model_file, 'rb') as f:
                data = pickle.load(f)
                self.model = data['model']
                self.scaler = data['scaler']
                self.training_data = data['training_data']
                self.is_trained = data['is_trained']
                log.info("ml_model_loaded", samples=len(self.training_data))
        except FileNotFoundError:
            log.info("no_saved_model_found", creating_new=True)
        except Exception as e:
            log.warning("ml_model_load_failed", error=str(e), creating_new=True)
            self.is_trained = False
    
    def save_model(self):
        """Persist model to disk"""
        try:
            data = {
                'model': self.model,
                'scaler': self.scaler,
                'training_data': self.training_data,
                'is_trained': self.is_trained
            }
            with open(self.model_file, 'wb') as f:
                pickle.dump(data, f)
        except Exception as e:
            log.error("ml_model_save_failed", error=str(e))
    
    def extract_features(self, whale_data: Dict, market_data: Dict,
                        bet_data: Dict, context_data: Dict) -> np.ndarray:
        """
        Convert trade data into ML features
        """
        return np.array([
            # Whale features
            whale_data.get('win_rate', 0.5),
            whale_data.get('sharpe_ratio', 1.0),
            whale_data.get('total_volume', 0) / 100000,  # Normalize
            whale_data.get('days_active', 0) / 365,
            whale_data.get('recent_win_rate', 0.5),
            
            # Market features
            market_data.get('current_price', 0.5),
            market_data.get('volume_24h', 0) / 10000,
            market_data.get('liquidity', 0) / 10000,
            market_data.get('days_until_resolution', 3) / 5,  # Normalize by max 5
            market_data.get('num_traders', 0) / 1000,
            
            # Bet features
            bet_data.get('size_pct_of_bankroll', 0.05),
            bet_data.get('entry_price', 0.5),
            bet_data.get('hours_until_close', 72) / 120,  # 5 days max
            
            # Context features
            context_data.get('num_other_whales_same_side', 0),
            context_data.get('market_momentum', 0.0),
            context_data.get('whale_category_score', 0.5)
        ])
    
    def add_training_example(self, whale_data: Dict, market_data: Dict,
                           bet_data: Dict, context_data: Dict, outcome: bool):
        """
        Store trade for training
        """
        features = self.extract_features(whale_data, market_data, bet_data, context_data)
        label = 1 if outcome else 0
        
        self.training_data.append({
            'features': features.tolist(),
            'label': label,
            'timestamp': datetime.now().isoformat(),
            'whale_id': whale_data.get('whale_id'),
            'market_id': market_data.get('market_id')
        })
        
        # Retrain every 20 examples
        if len(self.training_data) % 20 == 0:
            self.retrain()
        
        # Save every 10 examples
        if len(self.training_data) % 10 == 0:
            self.save_model()
    
    def retrain(self):
        """
        Rebuild model with all accumulated data
        """
        if len(self.training_data) < 50:
            log.info("ml_insufficient_data", 
                    current=len(self.training_data),
                    needed=50)
            return
        
        log.info("ml_retraining", samples=len(self.training_data))
        
        try:
            # Prepare data
            X = np.array([d['features'] for d in self.training_data])
            y = np.array([d['label'] for d in self.training_data])
            
            # Normalize features
            X_scaled = self.scaler.fit_transform(X)
            
            # Train model
            self.model.fit(X_scaled, y)
            self.is_trained = True
            
            # Calculate accuracy
            accuracy = self.model.score(X_scaled, y)
            
            # Feature importance
            importance = np.abs(self.model.coef_[0])
            
            log.info("ml_model_retrained",
                    accuracy=f"{accuracy:.2%}",
                    samples=len(y))
            
            # Log top features
            feature_importance = list(zip(self.feature_names, importance))
            feature_importance.sort(key=lambda x: x[1], reverse=True)
            
            for name, imp in feature_importance[:5]:
                log.info("ml_feature_importance", feature=name, importance=f"{imp:.3f}")
            
            self.save_model()
        except Exception as e:
            log.error("ml_retrain_failed", error=str(e))
    
    def predict_should_copy(self, whale_data: Dict, market_data: Dict,
                           bet_data: Dict, context_data: Dict) -> Tuple[bool, float]:
        """
        Use ML to predict trade success probability
        Returns: (should_copy, probability)
        """
        if not self.is_trained:
            # Fall back to simple rule
            return whale_data.get('win_rate', 0.5) > 0.65, 0.5
        
        try:
            # Get prediction
            features = self.extract_features(whale_data, market_data, bet_data, context_data)
            features_scaled = self.scaler.transform([features])
            
            probability = self.model.predict_proba(features_scaled)[0][1]
            
            # Need >65% confidence to recommend copy
            should_copy = probability > 0.65
            
            return should_copy, probability
        except Exception as e:
            log.warning("ml_predict_failed", error=str(e))
            # Fallback
            return whale_data.get('win_rate', 0.5) > 0.65, 0.5
