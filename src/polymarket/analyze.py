"""
Phase 2 Analysis: Answer 5 Key Questions
Analyzes collected signals to evaluate edge, filters, and signal quality.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import sys

# Add parent directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(parent_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def load_signals(date_str: str = None) -> pd.DataFrame:
    """Load signals CSV file with encoding handling."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    log_dir = os.path.join(project_root, "logs")
    signals_file = os.path.join(log_dir, f"signals_{date_str}.csv")
    
    if not os.path.exists(signals_file):
        raise FileNotFoundError(f"Signals file not found: {signals_file}")
    
    # Try multiple encodings
    encodings = ['utf-8-sig', 'latin-1', 'cp1252', 'utf-8']
    df = None
    
    for encoding in encodings:
        try:
            with open(signals_file, 'rb') as f:
                content = f.read()
                try:
                    decoded_content = content.decode(encoding)
                except UnicodeDecodeError:
                    decoded_content = content.decode(encoding, errors='replace')
                from io import StringIO
                df = pd.read_csv(StringIO(decoded_content), low_memory=False)
                break
        except Exception:
            continue
    
    if df is None:
        raise ValueError(f"Could not decode signals file: {signals_file}")
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df


def question_1_win_rate(df: pd.DataFrame) -> dict:
    """
    Question 1: Win rate at different thresholds (+1%, +2%, resolution).
    Note: This is a simplified analysis. Real win rate requires market outcome data.
    """
    print("\n" + "="*70)
    print("QUESTION 1: WIN RATE")
    print("="*70)
    
    total_signals = len(df)
    print(f"Total Signals: {total_signals}")
    
    # Note: We don't have actual market outcomes, so we'll analyze what we can
    # In production, you'd need to fetch market resolution data
    
    # Analyze discount distribution (signals with better discounts may have better outcomes)
    if 'discount_pct' in df.columns:
        avg_discount = df['discount_pct'].mean()
        signals_with_discount = len(df[df['discount_pct'] > 0])
        print(f"\nDiscount Analysis:")
        print(f"  Average Discount: {avg_discount:.2f}%")
        print(f"  Signals with Discount > 0%: {signals_with_discount} ({signals_with_discount/total_signals*100:.1f}%)")
        print(f"  Signals with Discount ≥ 1%: {len(df[df['discount_pct'] >= 1.0])} ({len(df[df['discount_pct'] >= 1.0])/total_signals*100:.1f}%)")
        print(f"  Signals with Discount ≥ 2%: {len(df[df['discount_pct'] >= 2.0])} ({len(df[df['discount_pct'] >= 2.0])/total_signals*100:.1f}%)")
    
    # Score distribution
    if 'whale_score' in df.columns:
        avg_score = df['whale_score'].mean()
        high_score_signals = len(df[df['whale_score'] >= 0.7])
        print(f"\nScore Analysis:")
        print(f"  Average Score: {avg_score:.2f}")
        print(f"  Signals with Score ≥ 0.7: {high_score_signals} ({high_score_signals/total_signals*100:.1f}%)")
    
    print("\n⚠️  NOTE: Actual win rate requires market resolution data.")
    print("   To calculate real win rate, you need:")
    print("   - Market outcome (YES/NO resolution)")
    print("   - Entry price vs resolution price")
    print("   - Time-series price data for +1%/+2% thresholds")
    
    return {
        'total_signals': total_signals,
        'avg_discount': avg_discount if 'discount_pct' in df.columns else 0,
        'signals_with_discount': signals_with_discount if 'discount_pct' in df.columns else 0,
    }


def question_2_time_to_resolution(df: pd.DataFrame) -> dict:
    """
    Question 2: Time to resolution.
    Note: Requires market resolution timestamps (not available in signals alone).
    """
    print("\n" + "="*70)
    print("QUESTION 2: TIME TO RESOLUTION")
    print("="*70)
    
    if 'timestamp' not in df.columns:
        print("⚠️  No timestamp data available")
        return {}
    
    # Analyze signal timing distribution
    df_sorted = df.sort_values('timestamp')
    first_signal = df_sorted['timestamp'].iloc[0]
    last_signal = df_sorted['timestamp'].iloc[-1]
    collection_duration = last_signal - first_signal
    
    print(f"Signal Collection Period:")
    print(f"  First Signal: {first_signal}")
    print(f"  Last Signal: {last_signal}")
    print(f"  Collection Duration: {collection_duration}")
    print(f"  Total Signals: {len(df)}")
    
    # Signal frequency
    if collection_duration.total_seconds() > 0:
        signals_per_hour = len(df) / (collection_duration.total_seconds() / 3600)
        print(f"\nSignal Generation Rate:")
        print(f"  Signals per Hour: {signals_per_hour:.1f}")
        print(f"  Average Time Between Signals: {collection_duration / len(df)}")
    
    print("\n⚠️  NOTE: Actual time-to-resolution requires:")
    print("   - Market resolution timestamps")
    print("   - Compare signal timestamp to market close/resolution timestamp")
    print("   - Categorize: minutes (<1h), hours (1-24h), overnight (>24h)")
    
    return {
        'collection_duration_hours': collection_duration.total_seconds() / 3600,
        'signals_per_hour': signals_per_hour if collection_duration.total_seconds() > 0 else 0,
    }


def question_3_drawdown_reality(df: pd.DataFrame) -> dict:
    """
    Question 3: Drawdown reality - longest losing streak.
    Note: Requires actual trade outcomes (simulated or real).
    """
    print("\n" + "="*70)
    print("QUESTION 3: DRAWDOWN REALITY")
    print("="*70)
    
    total_signals = len(df)
    print(f"Total Signals: {total_signals}")
    
    # Analyze signal quality distribution (as proxy for potential outcomes)
    if 'whale_score' in df.columns and 'discount_pct' in df.columns:
        # Create a simple "quality score" combining score and discount
        df['quality_score'] = df['whale_score'] * 0.7 + (df['discount_pct'] / 10) * 0.3
        df_sorted = df.sort_values('timestamp')
        
        # Simulate outcomes based on quality (for demonstration)
        # In production, use actual market outcomes
        np.random.seed(42)
        df_sorted['simulated_outcome'] = np.random.binomial(1, df_sorted['quality_score'].clip(0.3, 0.9))
        
        # Find longest losing streak
        losing_streak = 0
        max_losing_streak = 0
        current_streak = 0
        
        for outcome in df_sorted['simulated_outcome']:
            if outcome == 0:  # Loss
                current_streak += 1
                max_losing_streak = max(max_losing_streak, current_streak)
            else:  # Win
                current_streak = 0
        
        wins = df_sorted['simulated_outcome'].sum()
        losses = len(df_sorted) - wins
        win_rate = wins / len(df_sorted) * 100
        
        print(f"\nSimulated Outcomes (based on quality score):")
        print(f"  Wins: {wins}")
        print(f"  Losses: {losses}")
        print(f"  Win Rate: {win_rate:.1f}%")
        print(f"  Longest Losing Streak: {max_losing_streak}")
        
        # Calculate drawdown
        cumulative_pnl = df_sorted['simulated_outcome'].cumsum() - np.arange(len(df_sorted)) * (1 - win_rate/100)
        running_max = cumulative_pnl.expanding().max()
        drawdown = running_max - cumulative_pnl
        max_drawdown = drawdown.max()
        
        print(f"\nDrawdown Analysis:")
        print(f"  Max Drawdown: {max_drawdown:.1f} consecutive losses")
        print(f"  Longest Losing Streak: {max_losing_streak} signals")
        
        return {
            'simulated_win_rate': win_rate,
            'longest_losing_streak': max_losing_streak,
            'max_drawdown': max_drawdown,
        }
    
    print("\n⚠️  NOTE: Real drawdown analysis requires actual trade outcomes.")
    return {}


def question_4_filter_sensitivity(df: pd.DataFrame) -> dict:
    """
    Question 4: Filter sensitivity - slice same dataset with different filters.
    """
    print("\n" + "="*70)
    print("QUESTION 4: FILTER SENSITIVITY")
    print("="*70)
    
    total_signals = len(df)
    print(f"Base Dataset: {total_signals} signals")
    
    results = {}
    
    # Filter 1: discount ≥ 1.0%
    if 'discount_pct' in df.columns:
        filtered_1 = df[df['discount_pct'] >= 1.0]
        results['discount_1pct'] = len(filtered_1)
        print(f"\nFilter: discount_pct ≥ 1.0%")
        print(f"  Signals: {len(filtered_1)} ({len(filtered_1)/total_signals*100:.1f}%)")
        if len(filtered_1) > 0:
            print(f"  Avg Score: {filtered_1['whale_score'].mean():.2f}" if 'whale_score' in filtered_1.columns else "")
    
    # Filter 2: cluster_trades ≥ 3
    if 'cluster_trades_count' in df.columns:
        filtered_2 = df[df['cluster_trades_count'] >= 3]
        results['cluster_3'] = len(filtered_2)
        print(f"\nFilter: cluster_trades_count ≥ 3")
        print(f"  Signals: {len(filtered_2)} ({len(filtered_2)/total_signals*100:.1f}%)")
        if len(filtered_2) > 0:
            print(f"  Avg Discount: {filtered_2['discount_pct'].mean():.2f}%" if 'discount_pct' in filtered_2.columns else "")
    
    # Filter 3: score ≥ 0.7
    if 'whale_score' in df.columns:
        filtered_3 = df[df['whale_score'] >= 0.7]
        results['score_07'] = len(filtered_3)
        print(f"\nFilter: whale_score ≥ 0.7")
        print(f"  Signals: {len(filtered_3)} ({len(filtered_3)/total_signals*100:.1f}%)")
        if len(filtered_3) > 0:
            print(f"  Avg Discount: {filtered_3['discount_pct'].mean():.2f}%" if 'discount_pct' in filtered_3.columns else "")
    
    # Combined filters
    if all(col in df.columns for col in ['discount_pct', 'cluster_trades_count', 'whale_score']):
        filtered_combined = df[
            (df['discount_pct'] >= 1.0) &
            (df['cluster_trades_count'] >= 3) &
            (df['whale_score'] >= 0.7)
        ]
        results['combined'] = len(filtered_combined)
        print(f"\nCombined Filter: discount ≥ 1.0% AND cluster_trades ≥ 3 AND score ≥ 0.7")
        print(f"  Signals: {len(filtered_combined)} ({len(filtered_combined)/total_signals*100:.1f}%)")
    
    return results


def question_5_signal_decay(df: pd.DataFrame) -> dict:
    """
    Question 5: Signal decay - are earlier entries better than late ones?
    """
    print("\n" + "="*70)
    print("QUESTION 5: SIGNAL DECAY")
    print("="*70)
    
    if 'timestamp' not in df.columns:
        print("⚠️  No timestamp data available")
        return {}
    
    df_sorted = df.sort_values('timestamp').reset_index(drop=True)
    total_signals = len(df_sorted)
    
    # Split into thirds: early, middle, late
    third_size = total_signals // 3
    early = df_sorted.iloc[:third_size]
    middle = df_sorted.iloc[third_size:2*third_size]
    late = df_sorted.iloc[2*third_size:]
    
    print(f"Total Signals: {total_signals}")
    print(f"\nSplit into thirds:")
    print(f"  Early: {len(early)} signals")
    print(f"  Middle: {len(middle)} signals")
    print(f"  Late: {len(late)} signals")
    
    # Compare metrics across time periods
    if 'whale_score' in df_sorted.columns:
        print(f"\nAverage Whale Score:")
        print(f"  Early: {early['whale_score'].mean():.3f}")
        print(f"  Middle: {middle['whale_score'].mean():.3f}")
        print(f"  Late: {late['whale_score'].mean():.3f}")
    
    if 'discount_pct' in df_sorted.columns:
        print(f"\nAverage Discount:")
        print(f"  Early: {early['discount_pct'].mean():.2f}%")
        print(f"  Middle: {middle['discount_pct'].mean():.2f}%")
        print(f"  Late: {late['discount_pct'].mean():.2f}%")
    
    if 'cluster_trades_count' in df_sorted.columns:
        print(f"\nAverage Cluster Trades:")
        print(f"  Early: {early['cluster_trades_count'].mean():.2f}")
        print(f"  Middle: {middle['cluster_trades_count'].mean():.2f}")
        print(f"  Late: {late['cluster_trades_count'].mean():.2f}")
    
    # Trend analysis
    if 'whale_score' in df_sorted.columns and 'discount_pct' in df_sorted.columns:
        # Calculate correlation with time (signal number)
        df_sorted['signal_number'] = range(len(df_sorted))
        score_trend = df_sorted['whale_score'].corr(df_sorted['signal_number'])
        discount_trend = df_sorted['discount_pct'].corr(df_sorted['signal_number'])
        
        print(f"\nTrend Analysis (correlation with signal order):")
        print(f"  Score Trend: {score_trend:.3f} ({'decreasing' if score_trend < 0 else 'increasing'} over time)")
        print(f"  Discount Trend: {discount_trend:.3f} ({'decreasing' if discount_trend < 0 else 'increasing'} over time)")
    
    return {
        'early_avg_score': early['whale_score'].mean() if 'whale_score' in early.columns else 0,
        'late_avg_score': late['whale_score'].mean() if 'whale_score' in late.columns else 0,
        'score_trend': score_trend if 'whale_score' in df_sorted.columns else 0,
    }


def run_analysis(date_str: str = None):
    """Run all 5 questions analysis."""
    print("\n" + "="*70)
    print("PHASE 2 ANALYSIS: 5 KEY QUESTIONS")
    print("="*70)
    print(f"Analysis Date: {date_str or datetime.now().strftime('%Y-%m-%d')}")
    
    # Load signals
    try:
        df = load_signals(date_str)
        print(f"\n✅ Loaded {len(df)} signals")
    except Exception as e:
        print(f"\n❌ Error loading signals: {e}")
        return
    
    # Answer all 5 questions
    q1_results = question_1_win_rate(df)
    q2_results = question_2_time_to_resolution(df)
    q3_results = question_3_drawdown_reality(df)
    q4_results = question_4_filter_sensitivity(df)
    q5_results = question_5_signal_decay(df)
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Total Signals Analyzed: {len(df)}")
    print(f"\nKey Insights:")
    if 'discount_pct' in df.columns:
        print(f"  - Average Discount: {df['discount_pct'].mean():.2f}%")
    if 'whale_score' in df.columns:
        print(f"  - Average Score: {df['whale_score'].mean():.2f}")
    if 'cluster_trades_count' in df.columns:
        print(f"  - Average Cluster Size: {df['cluster_trades_count'].mean():.2f} trades")
    
    print("\n" + "="*70)
    print("Analysis Complete")
    print("="*70)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Phase 2 Analysis: Answer 5 Key Questions")
    parser.add_argument("--date", type=str, help="Date string (YYYY-MM-DD), defaults to today")
    args = parser.parse_args()
    
    run_analysis(args.date)

