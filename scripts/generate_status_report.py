"""Generate comprehensive data status report"""
import json
from datetime import datetime, timedelta
from dynamic_whale_manager import DynamicWhaleManager
from pathlib import Path
import sys

def generate_status_report():
    """Generate comprehensive data status report"""
    
    print("=" * 80)
    print("POLYMARKET WHALE BOT - DATA STATUS REPORT")
    print("=" * 80)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 1. Elite Whales (API Validation)
    print("1. ELITE WHALES (API Validated)")
    print("-" * 80)
    try:
        elite_file = Path('data/api_validation_results.json')
        if elite_file.exists():
            with open(elite_file, 'r') as f:
                elite_data = json.load(f)
            
            # Handle both list and dict formats
            if isinstance(elite_data, dict):
                results = elite_data.get('results', [])
            else:
                results = elite_data
            
            elite_whales = [w for w in results if w.get('passes', False)]
            
            print(f"✅ Total validated: {len(results)}")
            print(f"✅ Elite whales (passed criteria): {len(elite_whales)}")
            print()
            
            if elite_whales:
                # Top 10 by volume
                print("Top 10 Elite Whales by Volume:")
                sorted_by_volume = sorted(elite_whales, key=lambda x: x.get('total_volume_usd', 0) or x.get('volume', 0) or 0, reverse=True)[:10]
                for i, whale in enumerate(sorted_by_volume, 1):
                    addr = whale.get('address', 'Unknown')[:16] + '...'
                    volume = whale.get('total_volume_usd', 0) or whale.get('volume', 0) or 0
                    trades = whale.get('trade_count', 0) or whale.get('trades', 0)
                    profit_eth = whale.get('total_profit_eth', 0) or 0
                    win_rate = whale.get('win_rate', 0) * 100 if whale.get('win_rate', 0) < 1 else whale.get('win_rate', 0)
                    print(f"  {i:2}. {addr} | ${volume:,.0f} | {trades} trades | {profit_eth:.2f} ETH profit | {win_rate:.1f}% WR")
                print()
                
                # Top 10 by trade count
                print("Top 10 Elite Whales by Trade Count:")
                sorted_by_trades = sorted(elite_whales, key=lambda x: x.get('trade_count', 0) or x.get('trades', 0), reverse=True)[:10]
                for i, whale in enumerate(sorted_by_trades, 1):
                    addr = whale.get('address', 'Unknown')[:16] + '...'
                    trades = whale.get('trade_count', 0) or whale.get('trades', 0)
                    volume = whale.get('total_volume_usd', 0) or whale.get('volume', 0) or 0
                    profit_eth = whale.get('total_profit_eth', 0) or 0
                    win_rate = whale.get('win_rate', 0) * 100 if whale.get('win_rate', 0) < 1 else whale.get('win_rate', 0)
                    print(f"  {i:2}. {addr} | {trades} trades | ${volume:,.0f} | {profit_eth:.2f} ETH profit | {win_rate:.1f}% WR")
        else:
            print("❌ Elite whales file not found")
    except Exception as e:
        print(f"❌ Error loading elite whales: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    
    # 2. Dynamic Whale Pool (Rebuilding)
    print("2. DYNAMIC WHALE POOL (Rebuilding)")
    print("-" * 80)
    try:
        manager = DynamicWhaleManager()
        stats = manager.get_whale_stats()
        
        print(f"✅ Total whales discovered: {stats['total_whales']:,}")
        print(f"✅ High-confidence (≥70%): {stats['high_confidence']}")
        print(f"✅ Active whales: {stats['active_whales']:,}")
        avg_conf = stats['avg_confidence']
        # get_whale_stats returns as percentage string, convert if needed
        if isinstance(avg_conf, str):
            avg_conf = float(avg_conf.rstrip('%'))
        elif avg_conf < 1:
            avg_conf = avg_conf * 100
        print(f"✅ Average confidence: {avg_conf:.1f}%")
        print()
        
        # Top 10 by confidence
        if stats['total_whales'] > 0:
            print("Top 10 by Confidence:")
            whales_sorted = sorted(
                manager.whales.items(), 
                key=lambda x: x[1]['confidence'], 
                reverse=True
            )[:10]
            for i, (addr, data) in enumerate(whales_sorted, 1):
                addr_short = addr[:16] + '...'
                conf = data['confidence']
                # Confidence is stored as decimal (0.5-1.0), convert to percentage
                conf_pct = conf * 100 if conf <= 1.0 else conf
                trades = data['trade_count']
                value = data['total_value']
                print(f"  {i:2}. {addr_short} | {conf_pct:.0f}% | {trades} trades | ${value:,.0f}")
    except Exception as e:
        print(f"❌ Error loading whale pool: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    
    # 3. Trade Data
    print("3. TRADE DATA (Accumulating)")
    print("-" * 80)
    try:
        trade_file = Path('data/realtime_whale_trades.json')
        if trade_file.exists():
            try:
                with open(trade_file, 'r') as f:
                    trades = json.load(f)
            except json.JSONDecodeError as e:
                print(f"⚠️ Trade file corrupted at line {e.lineno if hasattr(e, 'lineno') else 'unknown'}")
                print(f"   Attempting to load partial data...")
                # Try to load what we can
                trades = []
                try:
                    with open(trade_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # Try to extract valid JSON chunks
                        import re
                        # Simple approach: count file size
                        file_size = trade_file.stat().st_size
                        print(f"   File size: {file_size / (1024*1024):.2f} MB")
                        print(f"   ⚠️ Cannot parse corrupted JSON - file needs repair")
                        trades = None
                except:
                    trades = None
            
            print(f"✅ Total trades preserved: {len(trades):,}")
            
            if len(trades) > 0:
                # Unique wallets
                unique_wallets = len(set(t.get('wallet', '') for t in trades if t.get('wallet')))
                print(f"✅ Unique wallets detected: {unique_wallets:,}")
                
                # Monitored whale trades
                whale_trades = sum(1 for t in trades if t.get('is_monitored_whale'))
                print(f"✅ Monitored whale trades: {whale_trades}")
                
                # Large trades
                large_trades = sum(1 for t in trades if t.get('value', 0) >= 100)
                print(f"✅ Large trades (>$100): {large_trades:,}")
                
                # Time range
                timestamps = [t.get('timestamp') for t in trades if t.get('timestamp')]
                if timestamps:
                    first_trade = min(timestamps)
                    last_trade = max(timestamps)
                    print(f"✅ Time range: {first_trade[:19]} to {last_trade[:19]}")
                    
                    # Calculate trades per hour
                    first_dt = datetime.fromisoformat(first_trade.replace('Z', '+00:00'))
                    last_dt = datetime.fromisoformat(last_trade.replace('Z', '+00:00'))
                    hours = (last_dt - first_dt).total_seconds() / 3600
                    if hours > 0:
                        rate = len(trades) / hours
                        print(f"✅ Average rate: {rate:.1f} trades/hour")
                    
                    # Age of latest trade
                    age_min = (datetime.now(last_dt.tzinfo) - last_dt).total_seconds() / 60
                    print(f"✅ Latest trade: {age_min:.1f} minutes ago")
        else:
            print("❌ Trade file not found")
    except Exception as e:
        print(f"❌ Error loading trades: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    
    # 4. Simulation Data (Phase 2)
    print("4. SIMULATION DATA (Phase 2)")
    print("-" * 80)
    try:
        sim_dir = Path('data/simulations')
        if sim_dir.exists():
            sim_files = list(sim_dir.glob('*.json'))
            print(f"✅ Simulation files: {len(sim_files)}")
            
            if sim_files:
                # Get latest simulation
                latest = max(sim_files, key=lambda p: p.stat().st_mtime)
                latest_time = datetime.fromtimestamp(latest.stat().st_mtime)
                print(f"✅ Latest simulation: {latest.name}")
                print(f"✅ Created: {latest_time.strftime('%Y-%m-%d %H:%M:%S')}")
                
                # Try to load and count elite simulations
                elite_count = 0
                total_sims = 0
                for sim_file in sim_files[:10]:  # Check first 10 files
                    try:
                        with open(sim_file, 'r') as f:
                            sim_data = json.load(f)
                            if isinstance(sim_data, list):
                                total_sims += len(sim_data)
                                elite_count += sum(1 for s in sim_data if s.get('is_elite', False))
                            elif isinstance(sim_data, dict) and sim_data.get('is_elite', False):
                                total_sims += 1
                                elite_count += 1
                    except:
                        pass
                
                if total_sims > 0:
                    print(f"✅ Total simulations (sample): {total_sims}")
                    print(f"✅ Elite simulations (sample): {elite_count}")
        else:
            print("⚠️ Simulation directory not found (may not have started yet)")
    except Exception as e:
        print(f"⚠️ Error checking simulations: {e}")
    
    print()
    
    # 5. System Health
    print("5. SYSTEM HEALTH")
    print("-" * 80)
    
    # Watcher process
    try:
        import subprocess
        result = subprocess.run(
            ['powershell', '-Command', 
             'Get-Process python -ErrorAction SilentlyContinue | Where-Object { (Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine -like "*realtime_whale_watcher*" } | Select-Object -First 1 | Select-Object Id, StartTime'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.stdout and 'Id' in result.stdout:
            print("✅ Watcher: RUNNING")
            # Try to extract runtime
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                print(f"   {lines[1].strip()}")
        else:
            print("⚠️ Watcher: NOT RUNNING")
    except:
        print("⚠️ Could not check watcher status")
    
    print()
    
    # File Status
    print("File Status:")
    files = {
        'Elite whales': 'data/api_validation_results.json',
        'Dynamic whales': 'data/dynamic_whale_state.json',
        'Trade history': 'data/realtime_whale_trades.json',
    }
    
    total_size = 0
    for name, filepath in files.items():
        path = Path(filepath)
        if path.exists():
            size = path.stat().st_size
            size_mb = size / (1024 * 1024)
            size_kb = size / 1024
            total_size += size
            modified = datetime.fromtimestamp(path.stat().st_mtime)
            age = (datetime.now() - modified).total_seconds() / 60
            if size_mb >= 1:
                size_str = f"{size_mb:.2f} MB"
            else:
                size_str = f"{size_kb:.1f} KB"
            print(f"  ✅ {name}: {size_str} (modified: {modified.strftime('%Y-%m-%d %H:%M:%S')}, {age:.0f} min ago)")
        else:
            print(f"  ❌ {name}: NOT FOUND")
    
    if total_size > 0:
        total_mb = total_size / (1024 * 1024)
        print(f"\n  📊 Total data size: {total_mb:.2f} MB")
    
    print()
    print("=" * 80)
    print("END OF REPORT")
    print("=" * 80)

if __name__ == "__main__":
    generate_status_report()
