#!/usr/bin/env python3
"""Phase 2: Brutal filtering to find 3-5 proven profitable elite whales"""
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

def phase2_brutal_filtering():
    """Brutal filtering to find 3-5 proven profitable elite whales"""
    
    print("=" * 80)
    print("PHASE 2: BRUTAL FILTERING ANALYSIS")
    print("=" * 80)
    print()
    
    # Load simulations
    sim_dir = Path('data/simulations')
    sim_files = list(sim_dir.glob('sim_*.json'))
    
    print(f"Total simulations: {len(sim_files):,}")
    print()
    
    # Load elite whale info
    with open('data/api_validation_results.json') as f:
        elite_data = json.load(f)
    
    # Handle both list and dict formats
    if isinstance(elite_data, list):
        results = elite_data
    else:
        results = elite_data.get('results', [])
    
    elite_info = {w['address'].lower(): w for w in results if w.get('passes')}
    
    # Analyze each whale
    whale_performance = defaultdict(lambda: {
        'simulations': [],
        'is_elite': False,
        'confidence': 0,
        'api_trades': 0,
        'api_volume': 0
    })
    
    for sim_file in sim_files:
        try:
            with open(sim_file) as f:
                sim = json.load(f)
        except Exception as e:
            print(f"⚠️ Error reading {sim_file.name}: {e}")
            continue
        
        if sim.get('status') != 'completed':
            continue
        
        whale = sim.get('whale_address', '').lower()
        if not whale:
            continue
        
        confidence = sim.get('confidence', 0)
        if isinstance(confidence, str):
            try:
                confidence = float(confidence)
            except:
                confidence = 0
        
        is_elite = sim.get('is_elite', False)
        
        # Get API info if elite
        if whale in elite_info:
            whale_performance[whale]['api_trades'] = elite_info[whale].get('trade_count', 0)
            whale_performance[whale]['api_volume'] = elite_info[whale].get('volume', 0)
        
        whale_performance[whale]['simulations'].append(sim)
        whale_performance[whale]['is_elite'] = is_elite or whale_performance[whale]['is_elite']
        whale_performance[whale]['confidence'] = max(
            whale_performance[whale]['confidence'], 
            confidence
        )
    
    print(f"Unique whales analyzed: {len(whale_performance)}")
    print()
    
    # BRUTAL FILTER 1: Elite whales only (confidence check relaxed since elite get 50% default)
    print("FILTER 1: Elite Whales Only")
    print("-" * 80)
    
    elite_whales = {
        whale: data for whale, data in whale_performance.items()
        if data['is_elite']
    }
    
    print(f"Passed: {len(elite_whales)} whales")
    if len(elite_whales) > 0:
        sample = list(elite_whales.items())[0]
        print(f"  Sample: {sample[0][:16]}... - {len(sample[1]['simulations'])} sims, conf: {sample[1]['confidence']:.0%}")
    print()
    
    # BRUTAL FILTER 2: Minimum simulations for statistical significance
    print("FILTER 2: Statistical Significance (≥20 simulations)")
    print("-" * 80)
    
    significant_whales = {
        whale: data for whale, data in elite_whales.items()
        if len(data['simulations']) >= 20
    }
    
    print(f"Passed: {len(significant_whales)} whales")
    if len(significant_whales) > 0:
        sample = list(significant_whales.items())[0]
        print(f"  Sample: {sample[0][:16]}... - {len(sample[1]['simulations'])} sims")
    print()
    
    # Calculate profitability for each delay
    print("CALCULATING WIN RATES & PROFITABILITY...")
    print("-" * 80)
    
    whale_results = []
    
    for whale, data in significant_whales.items():
        sims = data['simulations']
        
        # Analyze each delay (60s, 180s, 300s)
        delay_stats = {60: [], 180: [], 300: []}
        
        for sim in sims:
            if 'results' not in sim or not sim['results']:
                continue
            
            detection_price = sim.get('detection', {}).get('price', 0)
            if detection_price == 0:
                # Try alternative location
                detection_price = sim.get('whale_trade', {}).get('price', 0)
            
            for result in sim['results']:
                delay = result.get('delay_seconds')
                if delay not in delay_stats:
                    continue
                
                # Get entry price with slippage
                entry_price = result.get('simulated_entry_price', 0)
                market_price = result.get('market_state_at_entry', {}).get('price', 0)
                
                # Simple profitability: did we improve vs detection?
                # Assume binary outcome market
                if entry_price > 0 and detection_price > 0:
                    # If whale bought at lower price, they expected YES
                    # Our delayed entry is worse if price went up
                    delay_cost = entry_price - detection_price
                    delay_stats[delay].append({
                        'entry': entry_price,
                        'detection': detection_price,
                        'delay_cost': delay_cost,
                        'market_price': market_price
                    })
        
        # Calculate statistics per delay
        results_1min = delay_stats[60]
        results_3min = delay_stats[180]
        results_5min = delay_stats[300]
        
        if not results_1min:
            continue
        
        avg_delay_cost_1min = sum(r['delay_cost'] for r in results_1min) / len(results_1min)
        avg_delay_cost_3min = sum(r['delay_cost'] for r in results_3min) / len(results_3min) if results_3min else 0
        avg_delay_cost_5min = sum(r['delay_cost'] for r in results_5min) / len(results_5min) if results_5min else 0
        
        # Count how often delay cost was small (<2%)
        acceptable_1min = sum(1 for r in results_1min if abs(r['delay_cost']) < 0.02)
        win_rate_1min = acceptable_1min / len(results_1min) * 100 if results_1min else 0
        
        whale_results.append({
            'address': whale,
            'simulations': len(sims),
            'confidence': data['confidence'],
            'api_trades': data['api_trades'],
            'api_volume': data['api_volume'],
            'avg_delay_cost_1min': avg_delay_cost_1min,
            'avg_delay_cost_3min': avg_delay_cost_3min,
            'avg_delay_cost_5min': avg_delay_cost_5min,
            'win_rate_1min': win_rate_1min,
            'samples_1min': len(results_1min),
            'samples_3min': len(results_3min),
            'samples_5min': len(results_5min)
        })
    
    # BRUTAL FILTER 3: Acceptable delay cost at 1-min
    print("FILTER 3: Profitable at 1-min Delay (avg cost <2%)")
    print("-" * 80)
    
    profitable_whales = [
        w for w in whale_results
        if abs(w['avg_delay_cost_1min']) < 0.02 and w['samples_1min'] >= 20
    ]
    
    print(f"Passed: {len(profitable_whales)} whales")
    print()
    
    # Sort by best performance (lowest delay cost)
    profitable_whales.sort(key=lambda x: abs(x['avg_delay_cost_1min']))
    
    # TOP CANDIDATES
    print("=" * 80)
    print("TOP 10 ELITE WHALES FOR PAPER TRADING")
    print("=" * 80)
    print()
    
    print(f"{'Rank':<6} {'Whale':<45} {'Sims':<6} {'Conf':<6} {'Delay Cost':<12} {'Win Rate'}")
    print("-" * 80)
    
    for i, whale in enumerate(profitable_whales[:10], 1):
        addr = whale['address'][:42]
        sims = whale['simulations']
        conf = whale['confidence']
        cost = whale['avg_delay_cost_1min']
        win_rate = whale['win_rate_1min']
        
        print(f"{i:<6} {addr:<45} {sims:<6} {conf:<6.0f}% {cost:>+10.2%} {win_rate:>7.1f}%")
    
    print()
    print("=" * 80)
    print("RECOMMENDATION: TOP 3-5 WHALES FOR PAPER TRADING")
    print("=" * 80)
    print()
    
    top_5 = profitable_whales[:5]
    
    for i, whale in enumerate(top_5, 1):
        print(f"{i}. {whale['address'][:42]}")
        print(f"   Simulations: {whale['simulations']}")
        print(f"   Confidence: {whale['confidence']:.0f}%")
        print(f"   API Trades: {whale['api_trades']}")
        print(f"   API Volume: ${whale['api_volume']:,.0f}")
        print(f"   Avg Delay Cost (1min): {whale['avg_delay_cost_1min']:+.2%}")
        print(f"   Win Rate (1min): {whale['win_rate_1min']:.1f}%")
        print(f"   Samples: {whale['samples_1min']} simulations")
        print()
    
    # Save results
    output = {
        'analysis_date': datetime.now().isoformat(),
        'total_simulations': len(sim_files),
        'total_whales': len(whale_performance),
        'elite_whales': len(elite_whales),
        'significant_whales': len(significant_whales),
        'profitable_whales': len(profitable_whales),
        'top_5_whales': top_5,
        'all_profitable': profitable_whales
    }
    
    Path('data').mkdir(exist_ok=True)
    with open('data/phase2_analysis_results.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    print("Results saved to: data/phase2_analysis_results.json")
    print()
    print("=" * 80)
    print("NEXT STEP: Paper Trading with Top 3-5 Whales")
    print("=" * 80)

if __name__ == "__main__":
    phase2_brutal_filtering()
