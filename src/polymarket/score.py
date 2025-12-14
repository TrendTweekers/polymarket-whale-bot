"""
Whale scoring module for Polymarket.
Computes 0-1 scores based on trading performance metrics.
"""

from typing import List, Dict
import pandas as pd


def whale_score(whale_stats: dict, category: str) -> float:
    """
    Computes a 0-1 whale score based on trading performance.
    
    Scoring breakdown:
    - 40% category-specific win-rate (max 0 if < 55%)
    - 30% consistency = total_profit / (max_drawdown + 1) capped at 1
    - 20% hold-time score = 1 if 2 ≤ avg_hold ≤ 24 h else 0.5
    - 10% recent 30-day win-rate (uses overall win_rate as proxy if not available)
    
    Args:
        whale_stats: Dictionary with whale stats from profiler
        category: Category to score ('elections', 'sports', 'crypto', 'geo')
    
    Returns:
        Float score between 0 and 1
    """
    # 40% - Category-specific win-rate (max 0 if < 55%)
    segmented_win_rate = whale_stats.get("segmented_win_rate", {})
    category_win_rate = segmented_win_rate.get(category, 0.0)
    
    if category_win_rate < 0.55:
        category_score = 0.0
    else:
        # Normalize: 0.55 -> 0, 1.0 -> 1.0, so (win_rate - 0.55) / 0.45
        category_score = min(1.0, (category_win_rate - 0.55) / 0.45)
    
    category_weighted = category_score * 0.40
    
    # 30% - Consistency = total_profit / (max_drawdown + 1) capped at 1
    total_profit = whale_stats.get("total_profit", 0.0)
    max_drawdown = abs(whale_stats.get("max_drawdown", 0.0))
    
    if max_drawdown == 0:
        consistency_score = min(1.0, total_profit / 1000.0)  # Normalize if no drawdown
    else:
        consistency_score = min(1.0, total_profit / (max_drawdown + 1))
    
    consistency_weighted = consistency_score * 0.30
    
    # 20% - Hold-time score = 1 if 2 ≤ avg_hold ≤ 24 h else 0.5
    avg_hold_time = whale_stats.get("avg_hold_time_hours", 0.0)
    if 2.0 <= avg_hold_time <= 24.0:
        hold_time_score = 1.0
    else:
        hold_time_score = 0.5
    
    hold_time_weighted = hold_time_score * 0.20
    
    # 10% - Recent 30-day win-rate (use overall win_rate as proxy)
    # Note: In production, this would come from time-filtered stats
    overall_win_rate = whale_stats.get("win_rate", 0.0)
    recent_win_rate_score = overall_win_rate  # Already 0-1 normalized
    recent_win_rate_weighted = recent_win_rate_score * 0.10
    
    # Sum all weighted components
    total_score = (
        category_weighted +
        consistency_weighted +
        hold_time_weighted +
        recent_win_rate_weighted
    )
    
    return min(1.0, max(0.0, total_score))  # Clamp between 0 and 1


def whitelist_whales(whales: List[Dict], min_score: float = 0.70) -> List[Dict]:
    """
    Filters whales by minimum score and returns top 5 per category.
    
    Args:
        whales: List of whale dictionaries, each must have 'stats' and 'category' keys
        min_score: Minimum score threshold (default 0.70)
    
    Returns:
        List of filtered whales, top 5 per category
    """
    if not whales:
        return []
    
    # Score each whale
    scored_whales = []
    for whale in whales:
        stats = whale.get("stats", {})
        category = whale.get("category", "crypto")  # Default category
        
        score = whale_score(stats, category)
        whale_with_score = {
            **whale,
            "score": score,
            "category": category
        }
        
        if score >= min_score:
            scored_whales.append(whale_with_score)
    
    # Group by category and get top 5 per category
    df = pd.DataFrame(scored_whales)
    
    if df.empty:
        return []
    
    # Sort by score descending
    df = df.sort_values("score", ascending=False)
    
    # Get top 5 per category
    top_whales = []
    for category in df["category"].unique():
        category_df = df[df["category"] == category].head(5)
        top_whales.extend(category_df.to_dict("records"))
    
    # Sort final list by score descending
    top_whales.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    return top_whales


def demo():
    """Demo function that prints scores for dummy data."""
    print("\n" + "="*70)
    print("Whale Scoring Demo")
    print("="*70)
    
    # Create dummy whale data
    dummy_whales = [
        {
            "wallet": "0x1111111111111111111111111111111111111111",
            "category": "crypto",
            "stats": {
                "total_profit": 50000.0,
                "win_rate": 0.75,
                "max_drawdown": 0.15,
                "avg_hold_time_hours": 12.0,
                "trades_count": 150,
                "segmented_win_rate": {
                    "crypto": 0.78,
                    "elections": 0.60,
                    "sports": 0.55,
                    "geo": 0.50,
                }
            }
        },
        {
            "wallet": "0x2222222222222222222222222222222222222222",
            "category": "elections",
            "stats": {
                "total_profit": 30000.0,
                "win_rate": 0.68,
                "max_drawdown": 0.20,
                "avg_hold_time_hours": 18.0,
                "trades_count": 200,
                "segmented_win_rate": {
                    "crypto": 0.50,
                    "elections": 0.72,
                    "sports": 0.55,
                    "geo": 0.45,
                }
            }
        },
        {
            "wallet": "0x3333333333333333333333333333333333333333",
            "category": "crypto",
            "stats": {
                "total_profit": 10000.0,
                "win_rate": 0.52,
                "max_drawdown": 0.30,
                "avg_hold_time_hours": 1.0,
                "trades_count": 50,
                "segmented_win_rate": {
                    "crypto": 0.50,
                    "elections": 0.45,
                    "sports": 0.40,
                    "geo": 0.35,
                }
            }
        },
        {
            "wallet": "0x4444444444444444444444444444444444444444",
            "category": "sports",
            "stats": {
                "total_profit": 25000.0,
                "win_rate": 0.70,
                "max_drawdown": 0.10,
                "avg_hold_time_hours": 6.0,
                "trades_count": 100,
                "segmented_win_rate": {
                    "crypto": 0.55,
                    "elections": 0.60,
                    "sports": 0.80,
                    "geo": 0.50,
                }
            }
        },
    ]
    
    # Score each whale
    print("\nIndividual Whale Scores:")
    print("-" * 70)
    for whale in dummy_whales:
        score = whale_score(whale["stats"], whale["category"])
        print(f"\nWallet: {whale['wallet'][:20]}...")
        print(f"Category: {whale['category'].upper()}")
        print(f"Score: {score:.4f} ({score*100:.2f}%)")
        print(f"  Category Win Rate: {whale['stats']['segmented_win_rate'][whale['category']]:.2%}")
        print(f"  Total Profit: ${whale['stats']['total_profit']:,.2f}")
        print(f"  Max Drawdown: {whale['stats']['max_drawdown']:.2%}")
        print(f"  Avg Hold Time: {whale['stats']['avg_hold_time_hours']:.2f} hours")
    
    # Test whitelist filtering
    print("\n" + "="*70)
    print("Whitelisted Whales (min_score=0.70, top 5 per category):")
    print("-" * 70)
    
    whitelisted = whitelist_whales(dummy_whales, min_score=0.70)
    
    if whitelisted:
        for whale in whitelisted:
            print(f"\nWallet: {whale['wallet'][:20]}...")
            print(f"Category: {whale['category'].upper()}")
            print(f"Score: {whale['score']:.4f} ({whale['score']*100:.2f}%)")
    else:
        print("\nNo whales meet the minimum score threshold of 0.70")
    
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    demo()

