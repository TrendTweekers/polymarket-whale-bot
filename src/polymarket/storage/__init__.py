"""Storage module"""

from .trade_database import TradeDatabase

# Import SignalStore from parent storage.py (file) if it exists
# This allows: from src.polymarket.storage import SignalStore
try:
    from pathlib import Path
    import importlib.util
    import sys
    
    # Get parent directory (src/polymarket)
    parent_dir = Path(__file__).parent.parent
    storage_py = parent_dir / "storage.py"
    
    if storage_py.exists():
        # Load storage.py as a module
        spec = importlib.util.spec_from_file_location("polymarket_storage_module", storage_py)
        storage_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(storage_module)
        
        # Export SignalStore from the module
        if hasattr(storage_module, 'SignalStore'):
            SignalStore = storage_module.SignalStore
            __all__ = ['TradeDatabase', 'SignalStore']
        else:
            __all__ = ['TradeDatabase']
    else:
        __all__ = ['TradeDatabase']
except Exception as e:
    # If SignalStore not found, only export TradeDatabase
    # This prevents import errors if storage.py doesn't exist
    __all__ = ['TradeDatabase']
