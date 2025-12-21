"""
DYNAMIC WHALE STATE MANAGER
============================
Tutte's recommendation: Maintain local whale state, auto-remove inactive whales

Instead of static whale list, maintain:
• wallet address
• last trade timestamp
• markets traded
• confidence score
• active / inactive flag

Rules:
• active if traded within 48-72 hours
• confidence decays over time
• auto-remove inactive whales
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set


class DynamicWhaleManager:
    """
    Manages whale list dynamically based on actual activity
    
    Features:
    • Auto-discovers whales from market anomalies
    • Tracks last activity timestamp
    • Calculates confidence score
    • Auto-removes inactive whales
    • Saves state to disk
    """
    
    def __init__(self, activity_threshold_hours: int = 72, 
                 min_confidence: float = 0.3,
                 state_file: str = "data/dynamic_whale_state.json"):
        
        self.activity_threshold = timedelta(hours=activity_threshold_hours)
        self.min_confidence = min_confidence
        self.state_file = Path(state_file)
        
        # Load existing state or start fresh
        self.whales = self.load_state()
    
    def load_state(self) -> Dict:
        """Load whale state from disk"""
        if not self.state_file.exists():
            return {}
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                # Handle empty or whitespace-only files
                if not content:
                    return {}
                # Handle empty JSON objects (with or without whitespace)
                content_stripped = content.strip()
                if content_stripped == '{}' or content_stripped == 'null' or content_stripped == '':
                    return {}
                # Try to parse JSON
                try:
                    data = json.loads(content)
                    # Ensure it's a dict
                    if not isinstance(data, dict):
                        return {}
                    return data
                except json.JSONDecodeError:
                    # If parsing fails, return empty dict
                    return {}
        except json.JSONDecodeError as e:
            print(f"⚠️ JSON decode error in whale state file: {e}")
            # Backup corrupted file
            import shutil
            backup_file = self.state_file.with_suffix('.json.backup')
            try:
                shutil.copy(self.state_file, backup_file)
                print(f"   Backed up corrupted file to {backup_file}")
            except:
                pass
            # Return empty state
            return {}
        except Exception as e:
            print(f"⚠️ Error loading whale state: {e}")
            return {}
    
    def save_state(self):
        """Save whale state to disk"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, 'w') as f:
            json.dump(self.whales, f, indent=2)
    
    def add_or_update_whale(self, wallet: str, market: str, trade_value: float, 
                            win_rate: float = None, source: str = "anomaly"):
        """
        Add new whale or update existing
        
        Args:
            wallet: Wallet address
            market: Market slug where they traded
            trade_value: Size of trade
            win_rate: Optional win rate (if known)
            source: How discovered (anomaly, manual, etc)
        """
        
        now = datetime.now().isoformat()
        
        if wallet not in self.whales:
            # New whale
            self.whales[wallet] = {
                'address': wallet,
                'first_seen': now,
                'last_activity': now,
                'markets_traded': [market],
                'trade_count': 1,
                'total_value': trade_value,
                'confidence': 0.5,  # Start neutral
                'win_rate': win_rate,
                'source': source,
                'active': True,
                'tags': []
            }
            print(f"🆕 New whale discovered: {wallet[:12]}... (from {source})")
        
        else:
            # Update existing
            whale = self.whales[wallet]
            whale['last_activity'] = now
            
            if market not in whale['markets_traded']:
                whale['markets_traded'].append(market)
            
            whale['trade_count'] += 1
            whale['total_value'] += trade_value
            whale['active'] = True
            
            # Boost confidence for continued activity
            whale['confidence'] = min(1.0, whale['confidence'] + 0.05)
        
        self.save_state()
    
    def update_confidence_scores(self):
        """
        Update confidence scores based on activity
        
        Rules:
        • Confidence decays over time (no recent activity)
        • Active whales get confidence boost
        • Inactive whales marked as such
        """
        
        now = datetime.now()
        updated_count = 0
        deactivated_count = 0
        
        for wallet, whale in self.whales.items():
            last_activity = datetime.fromisoformat(whale['last_activity'])
            time_since_activity = now - last_activity
            
            # Check if still active
            if time_since_activity > self.activity_threshold:
                if whale['active']:
                    whale['active'] = False
                    deactivated_count += 1
                
                # Decay confidence
                decay_rate = 0.01 * (time_since_activity.days - 3)
                whale['confidence'] = max(0.0, whale['confidence'] - decay_rate)
            
            else:
                # Recently active - maintain or boost confidence
                if not whale['active']:
                    whale['active'] = True
                    updated_count += 1
            
        self.save_state()
        
        if deactivated_count > 0:
            print(f"⏸️ Deactivated {deactivated_count} inactive whales")
        if updated_count > 0:
            print(f"✅ Reactivated {updated_count} whales")
    
    def get_active_whales(self, min_confidence: float = None) -> List[str]:
        """Get list of active whale addresses"""
        
        if min_confidence is None:
            min_confidence = self.min_confidence
        
        self.update_confidence_scores()
        
        active = [
            whale['address'] 
            for whale in self.whales.values()
            if whale['active'] and whale['confidence'] >= min_confidence
        ]
        
        return active
    
    def get_whale_stats(self) -> Dict:
        """Get overall whale statistics"""
        
        self.update_confidence_scores()
        
        total = len(self.whales)
        active = sum(1 for w in self.whales.values() if w['active'])
        high_conf = sum(1 for w in self.whales.values() if w['confidence'] >= 0.7)
        
        return {
            'total_whales': total,
            'active_whales': active,
            'inactive_whales': total - active,
            'high_confidence': high_conf,
            'avg_confidence': sum(w['confidence'] for w in self.whales.values()) / max(total, 1)
        }
    
    def remove_low_confidence_whales(self):
        """Remove whales below minimum confidence"""
        
        to_remove = [
            wallet for wallet, whale in self.whales.items()
            if whale['confidence'] < self.min_confidence
        ]
        
        for wallet in to_remove:
            del self.whales[wallet]
        
        if to_remove:
            print(f"🗑️ Removed {len(to_remove)} low-confidence whales")
            self.save_state()
    
    def print_report(self):
        """Print whale status report"""
        
        stats = self.get_whale_stats()
        
        print("\n" + "="*80)
        print("🐋 DYNAMIC WHALE LIST STATUS")
        print("="*80)
        print()
        print(f"Total Whales: {stats['total_whales']}")
        print(f"  • Active (traded < 72h): {stats['active_whales']}")
        print(f"  • Inactive: {stats['inactive_whales']}")
        print(f"  • High Confidence (≥70%): {stats['high_confidence']}")
        print(f"  • Avg Confidence: {stats['avg_confidence']:.2%}")
        print()
        
        # Show top active whales
        active_whales = [
            (wallet, whale) 
            for wallet, whale in self.whales.items() 
            if whale['active']
        ]
        active_whales.sort(key=lambda x: x[1]['confidence'], reverse=True)
        
        if active_whales:
            print("Top Active Whales:")
            for wallet, whale in active_whales[:10]:
                print(f"  {wallet[:12]}... | Confidence: {whale['confidence']:.2%} | "
                      f"Trades: {whale['trade_count']} | Value: ${whale['total_value']:,.0f}")
        
        print()
        print("="*80)
        print()


# Usage example
if __name__ == "__main__":
    """
    INTEGRATION EXAMPLE:
    
    1. Replace your static whale list with DynamicWhaleManager:
       
       whale_manager = DynamicWhaleManager()
    
    2. When anomaly detected (from market_anomaly_detector.py):
       
       for wallet in anomaly['wallets_involved']:
           whale_manager.add_or_update_whale(
               wallet=wallet,
               market=anomaly['market'],
               trade_value=trade_value,
               source='market_anomaly'
           )
    
    3. Get active whales for monitoring:
       
       active_addresses = whale_manager.get_active_whales(min_confidence=0.6)
    
    4. Periodic cleanup (every hour):
       
       whale_manager.update_confidence_scores()
       whale_manager.remove_low_confidence_whales()
    
    5. View status:
       
       whale_manager.print_report()
    
    Benefits:
    • Never stuck with inactive whales
    • Auto-discovers new active traders
    • Confidence-weighted selection
    • Self-cleaning list
    """
    
    print(__doc__)
