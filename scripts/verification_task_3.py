"""Task 3: Simulation progress"""
import sys
from pathlib import Path

project_root = Path('.').resolve()
sys.path.insert(0, str(project_root))

try:
    from src.simulation import TradeSimulator
    s = TradeSimulator()
    sim_count = len(s.simulations) if hasattr(s, 'simulations') else 0
    print(f'Simulations started: {sim_count}')
except Exception as e:
    print(f'Error checking simulations: {e}')
    print('Simulations: N/A (check implementation)')
