#!/usr/bin/env python3
"""
Paper Trading Wrapper with Auto-Restart
Automatically restarts paper trading if it crashes
"""
import subprocess
import sys
import time
from pathlib import Path

def main():
    """Run paper trading with auto-restart on crash"""
    script_path = Path(__file__).parent / "paper_trading.py"
    max_restarts = 1000  # Effectively infinite
    restart_delay = 10  # Wait 10 seconds before restarting
    
    restart_count = 0
    
    print("=" * 60)
    print("🚀 PAPER TRADING - AUTO-RESTART MODE")
    print("=" * 60)
    print(f"Script: {script_path}")
    print(f"Max restarts: {max_restarts}")
    print(f"Restart delay: {restart_delay}s")
    print("=" * 60)
    print()
    
    while restart_count < max_restarts:
        try:
            print(f"▶️ Starting paper trading (attempt {restart_count + 1})...")
            print()
            
            # Run paper trading script
            result = subprocess.run(
                [sys.executable, str(script_path)],
                check=False  # Don't raise on non-zero exit
            )
            
            # If exit code is 0, it was a clean shutdown
            if result.returncode == 0:
                print("\n✅ Paper trading stopped cleanly")
                break
            else:
                restart_count += 1
                print(f"\n⚠️ Paper trading crashed (exit code: {result.returncode})")
                print(f"   Restarting in {restart_delay} seconds... (restart #{restart_count})")
                print()
                time.sleep(restart_delay)
                
        except KeyboardInterrupt:
            print("\n\n⚠️ Stopped by user")
            break
        except Exception as e:
            restart_count += 1
            print(f"\n❌ Error running paper trading: {e}")
            print(f"   Restarting in {restart_delay} seconds... (restart #{restart_count})")
            print()
            time.sleep(restart_delay)
    
    if restart_count >= max_restarts:
        print(f"\n❌ Maximum restarts ({max_restarts}) reached. Stopping.")
    
    print("\n✅ Wrapper stopped")

if __name__ == "__main__":
    main()
