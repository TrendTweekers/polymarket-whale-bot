# src/polymarket/storage.py
"""
Persistent signal storage in SQLite database with paper trading and resolver.
Keeps CSV logging intact, adds database for querying, analysis, and paper trading.
"""
import sqlite3
import os
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
import logging
import threading
import time

logger = logging.getLogger(__name__)


class SignalStore:
    """
    SQLite storage for whale signals.
    Provides deduplication and easy querying for analysis.
    """
    
    def __init__(self, db_path: str = "logs/paper_trading.sqlite"):
        """
        Initialize signal store with paper trading support.
        
        Args:
            db_path: Path to SQLite database file
        """
        # Ensure logs directory exists
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        
        self.db_path = db_path
        self._db_lock = threading.Lock()
        self.init_db()
    
    def _get_connection(self):
        """
        Get SQLite connection with proper settings for concurrent access.
        Uses WAL mode and busy_timeout to handle file locks gracefully.
        """
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=30000;")  # 30 seconds
        return conn
    
    def _retry_db(self, fn, *, tries=20, delay=0.2, backoff=1.2):
        """
        Retry a database operation with exponential backoff on lock errors.
        
        Args:
            fn: Callable that performs the database operation
            tries: Maximum number of retry attempts
            delay: Initial delay in seconds
            backoff: Multiplier for delay after each retry
            
        Returns:
            Result of fn()
            
        Raises:
            sqlite3.OperationalError: If all retries fail or error is not a lock error
        """
        last = None
        for _ in range(tries):
            try:
                return fn()
            except sqlite3.OperationalError as e:
                msg = str(e).lower()
                if "database is locked" not in msg:
                    raise
                last = e
                time.sleep(delay)
                delay *= backoff
        raise last
    
    def init_db(self):
        """Create database table if it doesn't exist."""
        with self._db_lock:
            def _do():
                conn = self._get_connection()
                try:
                    cursor = conn.cursor()
                    
                    # Create signals table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS signals(
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            ts TEXT,
                            event_id TEXT,
                            market_id TEXT,
                            condition_id TEXT,
                            slug TEXT,
                            market TEXT,
                            category TEXT,
                            category_inferred INTEGER,
                            wallet TEXT,
                            wallet_prefix10 TEXT,
                            side TEXT,
                            outcome_index INTEGER,
                            outcome_name TEXT,
                            token_id TEXT,
                            whale_score REAL,
                            confidence INTEGER,
                            discount REAL,
                            trade_value_usd REAL,
                            size REAL,
                            entry_price REAL,
                            current_price REAL,
                            midpoint REAL,
                            cluster_trades_count INTEGER,
                            days_to_expiry REAL,
                            tx_hash TEXT,
                            created_at TEXT DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    
                    # Create unique index to prevent duplicates
                    cursor.execute("""
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_signal_unique 
                        ON signals(event_id, outcome_index, side, wallet_prefix10)
                    """)
                    
                    # Create paper_trades table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS paper_trades(
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            signal_id INTEGER,
                            opened_at TEXT,
                            status TEXT DEFAULT 'OPEN',
                            stake_eur REAL,
                            stake_usd REAL,
                            entry_price REAL,
                            outcome_index INTEGER,
                            outcome_name TEXT,
                            side TEXT,
                            event_id TEXT,
                            market_id TEXT,
                            token_id TEXT,
                            confidence INTEGER,
                            resolved_at TEXT NULL,
                            resolved_outcome_index INTEGER NULL,
                            won INTEGER NULL,
                            pnl_usd REAL NULL,
                            FOREIGN KEY(signal_id) REFERENCES signals(id)
                        )
                    """)
                    
                    # Create resolutions table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS resolutions(
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            paper_trade_id INTEGER,
                            checked_at TEXT,
                            status TEXT,
                            details TEXT,
                            FOREIGN KEY(paper_trade_id) REFERENCES paper_trades(id)
                        )
                    """)
                    
                    # Create equity_curve table (optional snapshots)
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS equity_curve(
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            snapshot_at TEXT,
                            total_trades INTEGER,
                            open_trades INTEGER,
                            resolved_trades INTEGER,
                            total_pnl_usd REAL,
                            win_rate REAL,
                            equity_usd REAL
                        )
                    """)
                    
                    # Create indexes for performance
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_paper_trades_status 
                        ON paper_trades(status)
                    """)
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_paper_trades_event_id 
                        ON paper_trades(event_id)
                    """)
                    
                    conn.commit()
                finally:
                    conn.close()
            
            try:
                self._retry_db(_do)
            except Exception as e:
                logger.exception(
                    "storage_init_failed",
                    extra={
                        "event": "storage_init_failed",
                        "db_path": self.db_path,
                    }
                )
    
    def insert_signal(self, signal_row: Dict) -> bool:
        """
        Insert signal into database.
        
        Args:
            signal_row: Signal dictionary with all signal fields
            
        Returns:
            True if inserted, False if duplicate or error
        """
        try:
            # Extract fields from signal dict
            wallet = signal_row.get("wallet", "")
            wallet_prefix10 = wallet[:10] if wallet else ""
            
            # Compute confidence from whale_score if not provided
            whale_score = signal_row.get("whale_score")
            if whale_score is not None:
                try:
                    confidence = int(round(float(whale_score) * 100))
                except Exception:
                    confidence = None
            else:
                confidence = signal_row.get("confidence")
            
            # Prepare data for insertion
            data = {
                "ts": signal_row.get("timestamp", datetime.utcnow().isoformat()),
                "event_id": signal_row.get("event_id") or signal_row.get("condition_id", ""),
                "market_id": signal_row.get("market_id", ""),
                "condition_id": signal_row.get("condition_id", ""),
                "slug": signal_row.get("slug", ""),
                "market": signal_row.get("market", ""),
                "category": signal_row.get("category", ""),
                "category_inferred": 1 if signal_row.get("category_inferred") else 0,
                "wallet": wallet,
                "wallet_prefix10": wallet_prefix10,
                "side": signal_row.get("side", ""),
                "outcome_index": signal_row.get("outcome_index"),
                "outcome_name": signal_row.get("outcome_name") or signal_row.get("outcome", ""),
                "token_id": signal_row.get("token_id", ""),
                "whale_score": whale_score,
                "confidence": confidence,
                "discount": signal_row.get("discount_pct"),
                "trade_value_usd": signal_row.get("trade_value_usd"),
                "size": signal_row.get("size"),
                "entry_price": signal_row.get("whale_entry_price") or signal_row.get("entry_price"),
                "current_price": signal_row.get("current_price"),
                "midpoint": signal_row.get("midpoint"),
                "cluster_trades_count": signal_row.get("cluster_trades_count", 1),
                "days_to_expiry": signal_row.get("days_to_expiry"),
                "tx_hash": signal_row.get("transaction_hash") or signal_row.get("tx_hash", "")
            }
            
            with self._db_lock:
                def _do():
                    conn = self._get_connection()
                    try:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO signals(
                                ts, event_id, market_id, condition_id, slug, market,
                                category, category_inferred, wallet, wallet_prefix10,
                                side, outcome_index, outcome_name, token_id,
                                whale_score, confidence, discount, trade_value_usd,
                                size, entry_price, current_price, midpoint,
                                cluster_trades_count, days_to_expiry, tx_hash
                            ) VALUES (
                                :ts, :event_id, :market_id, :condition_id, :slug, :market,
                                :category, :category_inferred, :wallet, :wallet_prefix10,
                                :side, :outcome_index, :outcome_name, :token_id,
                                :whale_score, :confidence, :discount, :trade_value_usd,
                                :size, :entry_price, :current_price, :midpoint,
                                :cluster_trades_count, :days_to_expiry, :tx_hash
                            )
                        """, data)
                        signal_id = cursor.lastrowid
                        conn.commit()
                        return signal_id
                    finally:
                        conn.close()
                
                return self._retry_db(_do)
            
        except sqlite3.IntegrityError:
            # Duplicate signal (unique constraint violation) - return existing ID
            with self._db_lock:
                def _do():
                    conn = self._get_connection()
                    try:
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT id FROM signals 
                            WHERE event_id = :event_id 
                            AND outcome_index = :outcome_index 
                            AND side = :side 
                            AND wallet_prefix10 = :wallet_prefix10
                        """, {
                            "event_id": data.get("event_id", ""),
                            "outcome_index": data.get("outcome_index"),
                            "side": data.get("side", ""),
                            "wallet_prefix10": data.get("wallet_prefix10", "")
                        })
                        result = cursor.fetchone()
                        return result[0] if result else None
                    finally:
                        conn.close()
                
                result = self._retry_db(_do)
                if result:
                    logger.debug("signal_duplicate_skipped", 
                                event_id=data.get("event_id", "")[:20] if 'data' in locals() else "",
                                wallet_prefix10=data.get("wallet_prefix10", "") if 'data' in locals() else "")
                    return result
                return None
        except Exception as e:
            # Database error - log but don't crash engine
            logger.exception(
                "signal_db_insert_failed",
                extra={
                    "event": "signal_db_insert_failed",
                    "event_id": signal_row.get("event_id", "")[:20] if signal_row else "",
                }
            )
            return None
    
    def insert_paper_trade(self, signal_id: int, signal_dict: Dict, stake_eur: float, fx_eur_usd: float) -> Optional[int]:
        """
        Create a paper trade for a signal.
        
        Args:
            signal_id: ID of the signal from signals table
            signal_dict: Signal dictionary with trade details
            stake_eur: Stake amount in EUR
            fx_eur_usd: EUR to USD exchange rate
            
        Returns:
            Paper trade ID if created, None on error
        """
        try:
            stake_usd = stake_eur * fx_eur_usd
            entry_price = signal_dict.get("whale_entry_price") or signal_dict.get("entry_price") or signal_dict.get("current_price")
            
            # Extract outcome fields explicitly (ensure they're never None)
            outcome_index = signal_dict.get("outcome_index")
            outcome_name = signal_dict.get("outcome_name") or signal_dict.get("outcome", "")
            confidence = signal_dict.get("confidence")
            
            with self._db_lock:
                def _do():
                    conn = self._get_connection()
                    try:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO paper_trades(
                                signal_id, opened_at, status, stake_eur, stake_usd,
                                entry_price, outcome_index, outcome_name, side,
                                event_id, market_id, token_id, confidence
                            ) VALUES (
                                :signal_id, :opened_at, 'OPEN', :stake_eur, :stake_usd,
                                :entry_price, :outcome_index, :outcome_name, :side,
                                :event_id, :market_id, :token_id, :confidence
                            )
                        """, {
                            "signal_id": signal_id,
                            "opened_at": datetime.utcnow().isoformat(),
                            "stake_eur": stake_eur,
                            "stake_usd": stake_usd,
                            "entry_price": entry_price,
                            "outcome_index": outcome_index,
                            "outcome_name": outcome_name,
                            "side": signal_dict.get("side", ""),
                            "event_id": signal_dict.get("event_id") or signal_dict.get("condition_id", ""),
                            "market_id": signal_dict.get("market_id", ""),
                            "token_id": signal_dict.get("token_id", ""),
                            "confidence": confidence
                        })
                        trade_id = cursor.lastrowid
                        conn.commit()
                        return trade_id
                    finally:
                        conn.close()
                
                return self._retry_db(_do)
            
        except Exception as e:
            logger.exception(
                "paper_trade_insert_failed",
                extra={
                    "event": "paper_trade_insert_failed",
                    "signal_id": signal_id,
                }
            )
            return None
    
    def has_open_paper_trade(self, condition_id: str) -> bool:
        """
        Check if there's already an open paper trade for this condition_id.
        Checks both event_id and condition_id fields for compatibility.
        
        Args:
            condition_id: Market condition ID (event_id)
            
        Returns:
            True if open paper trade exists, False otherwise
        """
        if not condition_id:
            return False
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            # Check event_id field (which stores condition_id)
            cursor.execute(
                "SELECT 1 FROM paper_trades WHERE event_id = ? AND status = 'OPEN' LIMIT 1",
                (condition_id,)
            )
            result = cursor.fetchone() is not None
            conn.close()
            return result
        except Exception as e:
            logger.exception(
                "has_open_paper_trade_failed",
                extra={
                    "event": "has_open_paper_trade_failed",
                    "condition_id": condition_id[:20] if condition_id else "",
                }
            )
            return False  # On error, allow trade (fail open)
    
    def get_open_paper_trades(self, limit: int = 100) -> List[Dict]:
        """
        Get all open paper trades.
        
        Args:
            limit: Maximum number of trades to return
            
        Returns:
            List of trade dictionaries
        """
        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT pt.*, s.market, s.category, s.confidence
                FROM paper_trades pt
                LEFT JOIN signals s ON pt.signal_id = s.id
                WHERE pt.status = 'OPEN'
                ORDER BY pt.opened_at ASC
                LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.exception(
                "get_open_trades_failed",
                extra={
                    "event": "get_open_trades_failed",
                }
            )
            return []
    
    def mark_trade_resolved(self, paper_trade_id: int, resolved_outcome_index: int, 
                           won: bool, resolved_price: float) -> bool:
        """
        Mark a paper trade as resolved and compute PnL.
        
        Args:
            paper_trade_id: ID of the paper trade
            resolved_outcome_index: Outcome index that won
            won: Whether the trade won
            resolved_price: Final resolved price (1.0 for win, 0.0 for loss typically)
            
        Returns:
            True if updated successfully
        """
        try:
            with self._db_lock:
                def _do():
                    conn = self._get_connection()
                    try:
                        cursor = conn.cursor()
                        
                        # Get trade details
                        cursor.execute("""
                            SELECT stake_usd, entry_price, outcome_index FROM paper_trades
                            WHERE id = ?
                        """, (paper_trade_id,))
                        
                        trade = cursor.fetchone()
                        if not trade:
                            return False
                        
                        stake_usd, entry_price, trade_outcome_index = trade
                        
                        # Compute PnL
                        # If we bet on outcome_index and resolved_outcome_index matches, we win
                        # PnL = stake_usd * (resolved_price - entry_price) / entry_price
                        # Simplified: if won, PnL = stake_usd * (1.0 - entry_price) / entry_price
                        # If lost, PnL = -stake_usd
                        
                        if won:
                            # We won - profit based on price difference
                            if entry_price and entry_price > 0:
                                pnl_usd = stake_usd * (resolved_price - entry_price) / entry_price
                            else:
                                pnl_usd = stake_usd * (1.0 - entry_price) if entry_price else stake_usd
                        else:
                            # We lost - lose the stake
                            pnl_usd = -stake_usd
                        
                        # Update trade
                        cursor.execute("""
                            UPDATE paper_trades
                            SET status = 'RESOLVED',
                                resolved_at = :resolved_at,
                                resolved_outcome_index = :resolved_outcome_index,
                                won = :won,
                                pnl_usd = :pnl_usd
                            WHERE id = :trade_id
                        """, {
                            "resolved_at": datetime.utcnow().isoformat(),
                            "resolved_outcome_index": resolved_outcome_index,
                            "won": 1 if won else 0,
                            "pnl_usd": pnl_usd,
                            "trade_id": paper_trade_id
                        })
                        
                        conn.commit()
                        return True
                    finally:
                        conn.close()
                
                return self._retry_db(_do)
            
        except Exception as e:
            logger.exception(
                "mark_trade_resolved_failed",
                extra={
                    "event": "mark_trade_resolved_failed",
                    "trade_id": paper_trade_id,
                }
            )
            return False
    
    def write_resolution(self, paper_trade_id: int, status: str, details: str):
        """
        Write a resolution record.
        
        Args:
            paper_trade_id: ID of the paper trade
            status: Resolution status
            details: Additional details
        """
        try:
            with self._db_lock:
                def _do():
                    conn = self._get_connection()
                    try:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO resolutions(paper_trade_id, checked_at, status, details)
                            VALUES (?, ?, ?, ?)
                        """, (paper_trade_id, datetime.utcnow().isoformat(), status, details))
                        conn.commit()
                    finally:
                        conn.close()
                
                self._retry_db(_do)
        except Exception as e:
            logger.exception(
                "write_resolution_failed",
                extra={
                    "event": "write_resolution_failed",
                    "paper_trade_id": paper_trade_id,
                }
            )
    
    def write_equity_snapshot(self, snapshot: Dict):
        """
        Write an equity curve snapshot (optional).
        
        Args:
            snapshot: Dictionary with equity metrics
        """
        try:
            with self._db_lock:
                def _do():
                    conn = self._get_connection()
                    try:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO equity_curve(
                                snapshot_at, total_trades, open_trades, resolved_trades,
                                total_pnl_usd, win_rate, equity_usd
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            snapshot.get("snapshot_at", datetime.utcnow().isoformat()),
                            snapshot.get("total_trades", 0),
                            snapshot.get("open_trades", 0),
                            snapshot.get("resolved_trades", 0),
                            snapshot.get("total_pnl_usd", 0.0),
                            snapshot.get("win_rate", 0.0),
                            snapshot.get("equity_usd", 0.0)
                        ))
                        conn.commit()
                    finally:
                        conn.close()
                
                self._retry_db(_do)
        except Exception as e:
            logger.exception(
                "write_equity_snapshot_failed",
                extra={
                    "event": "write_equity_snapshot_failed",
                }
            )

