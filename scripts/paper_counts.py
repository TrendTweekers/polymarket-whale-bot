import os
import sqlite3

DB_PATH = os.path.join("logs", "paper_trading.sqlite")

def one(conn, sql, params=()):
    cur = conn.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else 0

def main():
    if not os.path.exists(DB_PATH):
        print(f"DB not found: {DB_PATH}")
        raise SystemExit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    signals = one(conn, "SELECT COUNT(*) FROM signals")
    paper_total = one(conn, "SELECT COUNT(*) FROM paper_trades")
    paper_open = one(conn, "SELECT COUNT(*) FROM paper_trades WHERE status='OPEN'")
    paper_resolved = one(conn, "SELECT COUNT(*) FROM paper_trades WHERE status='RESOLVED'")
    wins = one(conn, "SELECT COUNT(*) FROM paper_trades WHERE status='RESOLVED' AND won=1")
    losses = one(conn, "SELECT COUNT(*) FROM paper_trades WHERE status='RESOLVED' AND won=0")
    pnl = conn.execute("SELECT COALESCE(SUM(pnl_usd), 0.0) AS s FROM paper_trades WHERE status='RESOLVED'").fetchone()["s"]

    print("=== PAPER COUNTS ===")
    print(f"DB: {DB_PATH}")
    print(f"Signals stored: {signals}")
    print(f"Paper trades: {paper_total} (OPEN {paper_open}, RESOLVED {paper_resolved})")
    if paper_resolved > 0:
        winrate = (wins / paper_resolved) * 100.0
        print(f"Resolved: W {wins} / L {losses} = {winrate:.2f}% win rate")
        print(f"Total realized PnL (USD): {pnl:.4f}")
    else:
        print("Resolved: 0 (wait for markets to close)")

    conn.close()

if __name__ == "__main__":
    main()

