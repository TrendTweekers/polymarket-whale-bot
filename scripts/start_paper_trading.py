#!/usr/bin/env python3
"""
Paper Trading Launcher
Starts paper trading with essential Telegram notifications only
"""
import subprocess
import sys
from pathlib import Path

def main():
    print("=" * 60)
    print("🚀 STARTING PAPER TRADING MODE")
    print("=" * 60)
    print()
    print("📱 Telegram: ESSENTIAL ONLY")
    print("  ✅ Paper trades recorded")
    print("  ✅ Daily summaries")
    print("  ✅ Critical errors")
    print("  ❌ Regular whale trades")
    print("  ❌ Simulations")
    print("  ❌ Hourly updates")
    print()
    print("━" * 60)
    print()
    
    # Check if Phase 2 results exist
    if not Path('data/phase2_analysis_results.json').exists():
        print("❌ ERROR: Phase 2 analysis results not found!")
        print("   Run: python scripts/phase2_brutal_filtering.py")
        sys.exit(1)
    
    # Start paper trading with auto-restart
    print("Starting paper trading system with auto-restart...")
    print("Press Ctrl+C to stop")
    print()
    
    try:
        subprocess.run([sys.executable, "scripts/run_paper_trading_with_restart.py"], check=True)
    except KeyboardInterrupt:
        print("\n✅ Paper trading stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
