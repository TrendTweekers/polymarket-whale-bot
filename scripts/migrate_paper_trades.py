#!/usr/bin/env python3
"""
Migration script to add confidence column to paper_trades table.
Run once: python scripts/migrate_paper_trades.py
"""
import sqlite3
from pathlib import Path

DB = Path("logs") / "paper_trading.sqlite"

def main():
    if not DB.exists():
        print(f"❌ Database not found: {DB}")
        print("   Run the engine first to create the database.")
        return
    
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    
    # Add confidence column if it doesn't exist (SQLite-safe)
    try:
        cur.execute("ALTER TABLE paper_trades ADD COLUMN confidence INTEGER")
        print("✅ Added confidence column to paper_trades")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("ℹ️  confidence column already exists")
        else:
            print(f"⚠️  Error adding confidence column: {e}")
    
    con.commit()
    con.close()
    print(f"✅ Migration complete: {DB}")

if __name__ == "__main__":
    main()

