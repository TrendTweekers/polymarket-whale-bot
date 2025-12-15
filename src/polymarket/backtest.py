"""
Backtesting module for Polymarket Whale Signal Engine.
Simulates trades from collected signals and computes performance metrics.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import os
import sys

# Add parent directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(parent_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def load_signals(date_str: str = "2025-12-15") -> pd.DataFrame:
    """Load signals CSV file with encoding handling."""
    log_dir = os.path.join(project_root, "logs")
    signals_file = os.path.join(log_dir, f"signals_{date_str}.csv")
    
    if not os.path.exists(signals_file):
        raise FileNotFoundError(f"Signals file not found: {signals_file}")
    
    # Try multiple encodings to handle various CSV formats
    encodings = ['utf-8-sig', 'latin-1', 'cp1252', 'utf-8']
    df = None
    
    for encoding in encodings:
        try:
            # Read file as bytes first, decode with error handling, then pass to pandas
            with open(signals_file, 'rb') as f:
                content = f.read()
                try:
                    decoded_content = content.decode(encoding)
                except UnicodeDecodeError:
                    # If decode fails, try with error replacement
                    decoded_content = content.decode(encoding, errors='replace')
                
                # Use StringIO to pass decoded content to pandas
                from io import StringIO
                df = pd.read_csv(StringIO(decoded_content), low_memory=False)
                break
        except (UnicodeDecodeError, UnicodeError, Exception) as e:
            continue
    
    if df is None:
        raise ValueError(f"Could not decode signals file with any encoding: {signals_file}")
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df


def load_activity(date_str: str = "2025-12-15") -> pd.DataFrame:
    """Load activity CSV file with encoding handling."""
    log_dir = os.path.join(project_root, "logs")
    activity_file = os.path.join(log_dir, f"activity_{date_str}.csv")
    
    if not os.path.exists(activity_file):
        print(f"Warning: Activity file not found: {activity_file}")
        return pd.DataFrame()
    
    # Try multiple encodings to handle various CSV formats
    encodings = ['utf-8-sig', 'latin-1', 'cp1252', 'utf-8']
    df = None
    
    for encoding in encodings:
        try:
            # Read file as bytes first, decode with error handling, then pass to pandas
            with open(activity_file, 'rb') as f:
                content = f.read()
                try:
                    decoded_content = content.decode(encoding)
                except UnicodeDecodeError:
                    # If decode fails, try with error replacement
                    decoded_content = content.decode(encoding, errors='replace')
                
                # Use StringIO to pass decoded content to pandas
                from io import StringIO
                df = pd.read_csv(StringIO(decoded_content), low_memory=False)
                break
        except (UnicodeDecodeError, UnicodeError, Exception) as e:
            continue
    
    if df is None:
        print(f"Warning: Could not decode activity file with any encoding: {activity_file}")
        return pd.DataFrame()
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df


def filter_production_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Filter signals to production thresholds."""
    filtered = df[
        (df['whale_score'] >= 0.70) &
        (df['discount_pct'] >= 2.0)
    ].copy()
    return filtered


def simulate_trade(signal: pd.Series, position_size_usd: float = 25.0, gas_fee: float = 0.10) -> dict:
    """
    Simulate a single trade from a signal.
    
    Exit conditions:
    - 50% profit target
    - 4-hour maximum hold
    - -15% stop loss
    
    Returns dict with trade results.
    """
    entry_price = signal['current_price']
    entry_time = signal['timestamp']
    
    # Calculate position size in shares
    position_size_shares = position_size_usd / entry_price
    
    # Exit conditions
    profit_target = entry_price * 1.50  # 50% gain
    stop_loss = entry_price * 0.85     # -15% stop
    
    # Simulate exit (simplified: assume random outcome within bounds)
    # In production, this would use actual market data
    # For now, we'll use a simplified model based on discount and score
    
    # Higher discount and score = better chance of profit
    base_probability = min(0.7, (signal['discount_pct'] / 10.0) + (signal['whale_score'] * 0.3))
    
    # Simulate outcome
    if np.random.random() < base_probability:
        # Win scenario - exit at profit target or 4-hour mark (whichever comes first)
        exit_time = entry_time + timedelta(hours=4)
        exit_price = profit_target  # Assume we hit profit target
        pnl_pct = 50.0  # 50% profit
    else:
        # Loss scenario - exit at stop loss or 4-hour mark
        exit_time = entry_time + timedelta(hours=4)
        exit_price = stop_loss  # Assume we hit stop loss
        pnl_pct = -15.0  # -15% loss
    
    # Calculate P&L
    pnl_usd = (exit_price - entry_price) * position_size_shares
    pnl_usd -= gas_fee * 2  # Entry + exit gas fees
    
    # Calculate ROI
    roi_pct = (pnl_usd / position_size_usd) * 100
    
    return {
        'signal_timestamp': entry_time,
        'entry_price': entry_price,
        'exit_price': exit_price,
        'entry_time': entry_time,
        'exit_time': exit_time,
        'hold_hours': 4.0,  # Maximum hold
        'position_size_usd': position_size_usd,
        'pnl_usd': pnl_usd,
        'pnl_pct': pnl_pct,
        'roi_pct': roi_pct,
        'is_win': pnl_usd > 0,
        'gas_fee': gas_fee * 2,
    }


def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Calculate Sharpe ratio."""
    if len(returns) == 0 or returns.std() == 0:
        return 0.0
    
    excess_returns = returns - risk_free_rate
    sharpe = excess_returns.mean() / returns.std() * np.sqrt(252)  # Annualized
    return sharpe


def calculate_max_drawdown(equity_curve: pd.Series) -> float:
    """Calculate maximum drawdown."""
    if len(equity_curve) == 0:
        return 0.0
    
    running_max = equity_curve.expanding().max()
    drawdown = (equity_curve - running_max) / running_max
    max_drawdown = drawdown.min()
    return abs(max_drawdown) * 100  # Return as percentage


def calculate_expectancy(trades: pd.DataFrame) -> float:
    """Calculate expectancy (average expected value per trade)."""
    if len(trades) == 0:
        return 0.0
    
    win_rate = trades['is_win'].mean()
    avg_win = trades[trades['is_win']]['pnl_usd'].mean() if (trades['is_win']).any() else 0
    avg_loss = trades[~trades['is_win']]['pnl_usd'].mean() if (~trades['is_win']).any() else 0
    
    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
    return expectancy


def run_backtest(date_str: str = "2025-12-15", position_size_usd: float = 25.0, gas_fee: float = 0.10):
    """Run backtest on signals."""
    print(f"Loading signals for {date_str}...")
    signals_df = load_signals(date_str)
    print(f"Loaded {len(signals_df)} total signals")
    
    # Filter to production thresholds
    production_signals = filter_production_signals(signals_df)
    print(f"Filtered to {len(production_signals)} production signals (score >= 0.70, discount >= 2%)")
    
    if len(production_signals) == 0:
        print("No production signals found. Cannot run backtest.")
        return pd.DataFrame(), {
            'total_trades': 0,
            'win_rate': 0.0,
            'avg_roi': 0.0,
            'total_pnl': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'expectancy': 0.0,
        }
    
    # Simulate trades
    print("\nSimulating trades...")
    trades = []
    for idx, signal in production_signals.iterrows():
        trade_result = simulate_trade(signal, position_size_usd, gas_fee)
        trades.append(trade_result)
    
    trades_df = pd.DataFrame(trades)
    
    # Calculate metrics
    total_trades = len(trades_df)
    win_rate = trades_df['is_win'].mean() * 100
    avg_roi = trades_df['roi_pct'].mean()
    total_pnl = trades_df['pnl_usd'].sum()
    
    # Calculate Sharpe ratio
    returns = trades_df['roi_pct'] / 100  # Convert to decimal
    sharpe_ratio = calculate_sharpe_ratio(returns)
    
    # Calculate equity curve
    trades_df = trades_df.sort_values('entry_time')
    trades_df['cumulative_pnl'] = trades_df['pnl_usd'].cumsum()
    trades_df['equity'] = (position_size_usd * total_trades) + trades_df['cumulative_pnl']
    
    max_drawdown = calculate_max_drawdown(trades_df['equity'])
    expectancy = calculate_expectancy(trades_df)
    
    # Print results
    print("\n" + "="*70)
    print("BACKTEST RESULTS")
    print("="*70)
    print(f"Date: {date_str}")
    print(f"Total Signals: {len(signals_df)}")
    print(f"Production Signals: {len(production_signals)}")
    print(f"\nTrade Metrics:")
    print(f"  Total Trades: {total_trades}")
    print(f"  Win Rate: {win_rate:.2f}%")
    print(f"  Average ROI: {avg_roi:.2f}%")
    print(f"  Total P&L: ${total_pnl:.2f}")
    print(f"  Expectancy: ${expectancy:.2f} per trade")
    print(f"\nRisk Metrics:")
    print(f"  Sharpe Ratio: {sharpe_ratio:.3f}")
    print(f"  Max Drawdown: {max_drawdown:.2f}%")
    print(f"\nPosition Details:")
    print(f"  Position Size: ${position_size_usd}")
    print(f"  Gas Fee per Trade: ${gas_fee * 2:.2f}")
    print("="*70)
    
    # Create plots
    print("\nGenerating plots...")
    fig, axes = plt.subplots(2, 1, figsize=(12, 10))
    
    # ROI Histogram
    axes[0].hist(trades_df['roi_pct'], bins=30, edgecolor='black', alpha=0.7)
    axes[0].axvline(x=0, color='red', linestyle='--', linewidth=2, label='Break Even')
    axes[0].set_xlabel('ROI (%)')
    axes[0].set_ylabel('Frequency')
    axes[0].set_title('ROI Distribution')
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    
    # Equity Curve
    axes[1].plot(trades_df['entry_time'], trades_df['equity'], linewidth=2)
    axes[1].axhline(y=position_size_usd * total_trades, color='red', linestyle='--', linewidth=2, label='Initial Capital')
    axes[1].set_xlabel('Time')
    axes[1].set_ylabel('Equity ($)')
    axes[1].set_title('Equity Curve')
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    axes[1].tick_params(axis='x', rotation=45)
    
    plt.tight_layout()
    
    # Save plot
    output_file = os.path.join(project_root, "backtest_results.png")
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"Plots saved to: {output_file}")
    
    return trades_df, {
        'total_trades': total_trades,
        'win_rate': win_rate,
        'avg_roi': avg_roi,
        'total_pnl': total_pnl,
        'sharpe_ratio': sharpe_ratio,
        'max_drawdown': max_drawdown,
        'expectancy': expectancy,
    }


if __name__ == "__main__":
    # Set random seed for reproducibility
    np.random.seed(42)
    
    # Run backtest for Dec 15, 2025
    try:
        trades_df, metrics = run_backtest(date_str="2025-12-15", position_size_usd=25.0, gas_fee=0.10)
        print("\nBacktest completed successfully!")
    except Exception as e:
        print(f"\nError running backtest: {e}")
        import traceback
        traceback.print_exc()

