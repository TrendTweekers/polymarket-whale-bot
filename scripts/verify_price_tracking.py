"""
Verify Price Tracking Implementation
====================================
Checks simulation files to verify that real-time price tracking is working.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

def analyze_simulation_file(filepath: Path) -> Dict[str, Any]:
    """Analyze a single simulation file"""
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    results = {
        'file': filepath.name,
        'detection_time': data.get('detection_time'),
        'market_slug': data.get('market_slug'),
        'whale_address': data.get('whale_address'),
        'delays': []
    }
    
    if 'results' in data and data['results']:
        for result in data['results']:
            delay_info = {
                'delay_seconds': result.get('delay_seconds'),
                'execution_time': result.get('execution_time'),
                'price': None,
                'timestamp': None
            }
            
            if 'market_state_at_entry' in result:
                market_state = result['market_state_at_entry']
                delay_info['price'] = market_state.get('price')
                delay_info['timestamp'] = market_state.get('timestamp')
            
            results['delays'].append(delay_info)
    
    return results

def verify_price_tracking():
    """Verify price tracking is working correctly"""
    sim_dir = Path("data/simulations")
    
    if not sim_dir.exists():
        print("❌ Simulations directory not found")
        return
    
    sim_files = list(sim_dir.glob("sim_*.json"))
    
    if not sim_files:
        print("⏰ No simulation files found yet")
        print("   Waiting for next high-confidence whale trade...")
        return
    
    print("=" * 70)
    print("PRICE TRACKING VERIFICATION")
    print("=" * 70)
    print(f"\nFound {len(sim_files)} simulation file(s)")
    
    # Analyze latest file
    latest_file = max(sim_files, key=lambda p: p.stat().st_mtime)
    print(f"\n📄 Analyzing latest file: {latest_file.name}")
    print(f"   Created: {datetime.fromtimestamp(latest_file.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        analysis = analyze_simulation_file(latest_file)
        
        print(f"\n📊 Simulation Details:")
        print(f"   Detection Time: {analysis['detection_time']}")
        print(f"   Market: {analysis['market_slug']}")
        print(f"   Whale: {analysis['whale_address'][:16]}...")
        
        if not analysis['delays']:
            print("\n⚠️ No delay results found in file")
            return
        
        print(f"\n🔍 Delay Price Analysis:")
        print("-" * 70)
        
        prices = []
        timestamps = []
        
        for delay in analysis['delays']:
            delay_sec = delay['delay_seconds']
            delay_min = delay_sec / 60.0
            price = delay['price']
            exec_time = delay['execution_time']
            timestamp = delay['timestamp']
            
            price_str = f"{price:.6f}" if price is not None else "N/A"
            print(f"  +{delay_sec:3d}s ({delay_min:4.1f}min): Price = {price_str:>12} | Exec: {exec_time}")
            
            if price is not None:
                prices.append(price)
            if timestamp:
                timestamps.append(timestamp)
        
        print("-" * 70)
        
        # Verification checks
        print(f"\n✅ Verification Results:")
        
        # Check 1: Prices differ
        unique_prices = len(set(prices)) if prices else 0
        if unique_prices > 1:
            print(f"   ✅ Prices differ at each delay ({unique_prices} unique prices)")
            print(f"      Price range: {min(prices):.6f} to {max(prices):.6f}")
            print(f"      Price change: {((max(prices) - min(prices)) / min(prices) * 100):.2f}%")
        elif unique_prices == 1 and len(prices) > 0:
            print(f"   ⚠️  All delays show same price: {prices[0]:.6f}")
            print(f"      This may indicate:")
            print(f"      - Market price didn't change during delays")
            print(f"      - File created before price tracking fix")
            print(f"      - Price lookup failed (check watcher logs)")
        else:
            print(f"   ❌ No prices found in delay results")
        
        # Check 2: Timestamps match execution times
        if timestamps:
            print(f"   ✅ Timestamps present for all delays")
            # Parse and verify timestamps
            try:
                detection_dt = datetime.fromisoformat(analysis['detection_time'].replace('Z', '+00:00'))
                for i, delay in enumerate(analysis['delays']):
                    if delay['timestamp']:
                        delay_dt = datetime.fromisoformat(delay['timestamp'].replace('Z', '+00:00'))
                        expected_delay = delay['delay_seconds']
                        actual_delay = (delay_dt - detection_dt).total_seconds()
                        if abs(actual_delay - expected_delay) < 5:  # Allow 5 second tolerance
                            print(f"      ✅ Delay {delay['delay_seconds']}s: Timestamp matches ({actual_delay:.0f}s)")
                        else:
                            print(f"      ⚠️  Delay {delay['delay_seconds']}s: Timestamp mismatch (expected {expected_delay}s, got {actual_delay:.0f}s)")
            except Exception as e:
                print(f"   ⚠️  Could not verify timestamps: {e}")
        else:
            print(f"   ⚠️  No timestamps found in delay results")
        
        # Check 3: File age (to determine if created before/after fix)
        file_age_hours = (datetime.now().timestamp() - latest_file.stat().st_mtime) / 3600
        if file_age_hours < 1:
            print(f"\n📅 File created {file_age_hours*60:.0f} minutes ago (likely after fix)")
        else:
            print(f"\n📅 File created {file_age_hours:.1f} hours ago")
        
        print("\n" + "=" * 70)
        
        # Summary
        if unique_prices > 1:
            print("\n🎉 SUCCESS: Price tracking appears to be working!")
            print("   Different prices at each delay indicate real-time tracking is active.")
        elif unique_prices == 1:
            print("\n⏳ INCONCLUSIVE: Need more recent simulation files")
            print("   Wait for next high-confidence whale trade to verify fix.")
        else:
            print("\n❌ ERROR: No price data found")
            print("   Check watcher logs for errors.")
        
    except Exception as e:
        print(f"\n❌ Error analyzing file: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_price_tracking()
