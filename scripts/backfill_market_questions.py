#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backfill script to fetch and store full market question texts for existing paper trades.

This script:
1. Queries database for open trades without market_question (status='OPEN' and market_question IS NULL)
2. For each condition_id, fetches full question from Gamma API
3. Updates database with the question text
4. Provides logging, error handling, and dry-run mode

Usage:
    python scripts/backfill_market_questions.py --dry-run  # Preview changes
    python scripts/backfill_market_questions.py --update  # Actually update database
"""

import sys
import os
import asyncio
import aiohttp
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env", override=True)
except Exception:
    pass

# Import SignalStore - use direct file import
import importlib.util
storage_path = project_root / "src" / "polymarket" / "storage.py"
spec = importlib.util.spec_from_file_location("storage_module", storage_path)
storage_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage_module)
SignalStore = storage_module.SignalStore

from src.polymarket.scraper import HEADERS, GAMMA_BASE
import re

# Try to import structlog for logging
try:
    import structlog
    logger = structlog.get_logger()
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


def generate_question_template(market_name: str, category: Optional[str] = None) -> Optional[str]:
    """
    Generate full question text template based on market name patterns.
    
    Args:
        market_name: The market name/title from database
        category: Market category (e.g., 'sports', 'politics')
        
    Returns:
        Full question text template or None if pattern not recognized
    """
    market_lower = market_name.lower()
    
    # NFL Spread markets (e.g., "Raiders vs. Texans spread: Texans -14.5")
    # Pattern: [Team1] vs [Team2] spread: [Favorite] [±]spread
    spread_pattern = re.search(
        r'(.+?)\s+vs\.?\s+(.+?)\s+spread:\s+(.+?)\s+([+-]?\d+\.?\d*)',
        market_name,
        re.IGNORECASE
    )
    if spread_pattern:
        team1 = spread_pattern.group(1).strip()
        team2 = spread_pattern.group(2).strip()
        favorite = spread_pattern.group(3).strip()
        spread = spread_pattern.group(4).strip()
        
        # Determine favorite and underdog
        if favorite.lower() in team1.lower():
            favorite_team = team1
            underdog_team = team2
        elif favorite.lower() in team2.lower():
            favorite_team = team2
            underdog_team = team1
        else:
            # Fallback: assume favorite is the team mentioned
            favorite_team = favorite
            underdog_team = team2 if favorite.lower() in team1.lower() else team1
        
        # Extract date if present in market name
        date_match = re.search(r'(\w+\s+\d{1,2},?\s+\d{4})', market_name)
        date_str = date_match.group(1) if date_match else "the specified date"
        
        # Build full question
        question = (
            f"Will {favorite_team} win by more than {spread.replace('+', '')} points against {underdog_team} on {date_str}? "
            f"This market will resolve to 'Yes' if {favorite_team} wins by more than {spread.replace('+', '')} points "
            f"according to the official NFL score at the end of regulation, including overtime if necessary. "
            f"Otherwise, it will resolve to 'No'. If the game is cancelled or postponed, the market will resolve to 'No'."
        )
        return question
    
    # NFL Moneyline (e.g., "Raiders vs. Texans moneyline: Texans")
    moneyline_pattern = re.search(
        r'(.+?)\s+vs\.?\s+(.+?)\s+moneyline:\s+(.+?)(?:\s+on\s+(\w+\s+\d{1,2},?\s+\d{4}))?',
        market_name,
        re.IGNORECASE
    )
    if moneyline_pattern:
        team1 = moneyline_pattern.group(1).strip()
        team2 = moneyline_pattern.group(2).strip()
        winner = moneyline_pattern.group(3).strip()
        date_str = moneyline_pattern.group(4) if moneyline_pattern.group(4) else "the specified date"
        
        question = (
            f"Will {winner} win against {team2 if winner.lower() in team1.lower() else team1} on {date_str}? "
            f"This market will resolve to 'Yes' if {winner} wins the game according to the official NFL score "
            f"at the end of regulation, including overtime if necessary. Otherwise, it will resolve to 'No'. "
            f"If the game is cancelled or postponed, the market will resolve to 'No'."
        )
        return question
    
    # Generic NFL game (e.g., "Raiders vs. Texans")
    if 'nfl' in market_lower or ('vs' in market_lower and any(team in market_lower for team in ['raiders', 'texans', 'chiefs', 'bills', 'cowboys', 'packers'])):
        vs_match = re.search(r'(.+?)\s+vs\.?\s+(.+?)(?:\s+on\s+(\w+\s+\d{1,2},?\s+\d{4}))?', market_name, re.IGNORECASE)
        if vs_match:
            team1 = vs_match.group(1).strip()
            team2 = vs_match.group(2).strip()
            date_str = vs_match.group(3) if vs_match.group(3) else "the specified date"
            
            question = (
                f"Will {team1} win against {team2} on {date_str}? "
                f"This market will resolve to 'Yes' if {team1} wins the game according to the official NFL score "
                f"at the end of regulation, including overtime if necessary. Otherwise, it will resolve to 'No'. "
                f"If the game is cancelled or postponed, the market will resolve to 'No'."
            )
            return question
    
    # NBA/Other sports spreads
    if 'spread' in market_lower and ('nba' in market_lower or 'basketball' in market_lower):
        spread_match = re.search(
            r'(.+?)\s+vs\.?\s+(.+?)\s+spread:\s+(.+?)\s+([+-]?\d+\.?\d*)',
            market_name,
            re.IGNORECASE
        )
        if spread_match:
            team1 = spread_match.group(1).strip()
            team2 = spread_match.group(2).strip()
            favorite = spread_match.group(3).strip()
            spread = spread_match.group(4).strip()
            
            date_match = re.search(r'(\w+\s+\d{1,2},?\s+\d{4})', market_name)
            date_str = date_match.group(1) if date_match else "the specified date"
            
            question = (
                f"Will {favorite} win by more than {spread.replace('+', '')} points against {team2 if favorite.lower() in team1.lower() else team1} on {date_str}? "
                f"This market will resolve to 'Yes' if {favorite} wins by more than {spread.replace('+', '')} points "
                f"according to the official NBA score at the end of regulation, including overtime if necessary. "
                f"Otherwise, it will resolve to 'No'. If the game is cancelled or postponed, the market will resolve to 'No'."
            )
            return question
    
    # Earnings markets (e.g., "Will General Mills (GIS) beat quarterly earnings?")
    if 'beat' in market_lower and 'earnings' in market_lower:
        earnings_match = re.search(
            r'will\s+(.+?)\s+beat\s+(.+?)\s+earnings',
            market_lower
        )
        if earnings_match:
            company = earnings_match.group(1).strip()
            period = earnings_match.group(2).strip() if earnings_match.group(2) else "quarterly"
            
            question = (
                f"Will {company} beat {period} earnings? "
                f"This market will resolve to 'Yes' if {company} reports earnings that exceed analyst expectations "
                f"for the {period} period. Otherwise, it will resolve to 'No'."
            )
            return question
    
    # Bitcoin/crypto price ranges
    if 'bitcoin' in market_lower or 'btc' in market_lower:
        price_match = re.search(
            r'price.*between\s+\$?([\d,]+)\s+and\s+\$?([\d,]+).*?(\w+\s+\d{1,2},?\s+\d{4})?',
            market_lower
        )
        if price_match:
            low = price_match.group(1).replace(',', '')
            high = price_match.group(2).replace(',', '')
            date_str = price_match.group(3) if price_match.group(3) else "the specified date"
            
            question = (
                f"Will the price of Bitcoin be between ${low} and ${high} on {date_str}? "
                f"This market will resolve to 'Yes' if Bitcoin's price is between ${low} and ${high} "
                f"(inclusive) at market close on {date_str} according to a major exchange. Otherwise, it will resolve to 'No'."
            )
            return question
    
    # Return None if no pattern matched
    return None


async def fetch_market_question_from_api(session: aiohttp.ClientSession, condition_id: str) -> Optional[str]:
    """
    Fetch full market question from Polymarket Gamma API.
    
    Args:
        session: aiohttp session
        condition_id: Market condition ID
        
    Returns:
        Full question text or None if not found/error
    """
    url = f"{GAMMA_BASE}/markets?conditionId={condition_id}"
    
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                logger.warning("api_fetch_failed",
                             condition_id=condition_id[:20],
                             status=resp.status)
                return None
            
            data = await resp.json()
            
            # Handle different response formats
            market = None
            if isinstance(data, list) and data:
                market = data[0]
            elif isinstance(data, dict):
                if "markets" in data and isinstance(data["markets"], list) and data["markets"]:
                    market = data["markets"][0]
                elif "id" in data:
                    market = data
            
            if not market:
                logger.debug("no_market_data",
                           condition_id=condition_id[:20])
                return None
            
            # Check if API returned wrong market (Biden/2020 issue)
            api_title = market.get("title") or market.get("question", "")
            api_looks_wrong = (
                api_title and (
                    "biden" in api_title.lower() or 
                    "coronavirus" in api_title.lower() or 
                    "2020" in str(market.get("endDate", ""))
                )
            )
            
            if api_looks_wrong:
                logger.warning("api_wrong_market",
                             condition_id=condition_id[:20],
                             returned_title=api_title[:60])
                return None
            
            # Try multiple fields for full question text
            question = (
                market.get("question") or
                market.get("description") or
                market.get("title") or
                None
            )
            
            if question:
                logger.debug("question_fetched",
                           condition_id=condition_id[:20],
                           question_len=len(question))
                return question
            
            logger.debug("no_question_field",
                       condition_id=condition_id[:20])
            return None
            
    except asyncio.TimeoutError:
        logger.warning("api_timeout",
                     condition_id=condition_id[:20])
        return None
    except Exception as e:
        logger.warning("api_exception",
                     condition_id=condition_id[:20],
                     error=str(e))
        return None


async def backfill_questions(dry_run: bool = True, limit: Optional[int] = None) -> Tuple[int, int, int]:
    """
    Backfill market_question for existing trades.
    
    Args:
        dry_run: If True, don't update database, just show what would be updated
        limit: Maximum number of trades to process (None = all)
        
    Returns:
        Tuple of (total_processed, updated_count, failed_count)
    """
    signal_store = SignalStore()
    
    # Get open trades without market_question
    try:
        conn = signal_store._get_connection()
        conn.row_factory = lambda cursor, row: {
            col[0]: row[idx] for idx, col in enumerate(cursor.description)
        }
        cursor = conn.cursor()
        
        query = """
            SELECT pt.id, pt.event_id, pt.market as market_name, s.market as signal_market, 
                   s.condition_id, s.category
            FROM paper_trades pt
            LEFT JOIN signals s ON pt.signal_id = s.id
            WHERE pt.status = 'OPEN' 
            AND (pt.market_question IS NULL OR pt.market_question = '' OR pt.market_question = pt.market)
        """
        
        if limit:
            query += f" LIMIT {limit}"
        
        cursor.execute(query)
        trades = cursor.fetchall()
        conn.close()
        
        total_trades = len(trades)
        print(f"\n{'='*80}")
        print(f"Found {total_trades} open trade(s) without market_question")
        print(f"{'='*80}\n")
        
        if total_trades == 0:
            print("✅ All open trades already have market_question stored!")
            return (0, 0, 0)
        
    except Exception as e:
        print(f"❌ Error querying database: {e}")
        import traceback
        traceback.print_exc()
        return (0, 0, 0)
    
    # Process trades
    updated_count = 0
    failed_count = 0
    
    async with aiohttp.ClientSession() as session:
        for idx, trade in enumerate(trades, 1):
            trade_id = trade["id"]
            # event_id is stored in paper_trades, condition_id might be in signals
            condition_id = trade.get("event_id") or trade.get("condition_id")
            # Prefer paper_trades.market over signals.market
            market_name = trade.get("market_name") or trade.get("signal_market", "Unknown")
            category = trade.get("category")
            
            print(f"[{idx}/{total_trades}] Trade ID {trade_id}: {market_name[:60]}...")
            print(f"  Condition ID: {condition_id[:66] if condition_id else 'N/A'}...")
            
            if not condition_id:
                print(f"  ⚠️  Skipping: No condition_id")
                failed_count += 1
                continue
            
            # Fetch question from API
            question = await fetch_market_question_from_api(session, condition_id)
            
            if question:
                print(f"  ✅ Found question: {question[:80]}...")
                
                if dry_run:
                    print(f"  [DRY RUN] Would update trade {trade_id} with question")
                else:
                    # Update database
                    try:
                        conn = signal_store._get_connection()
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE paper_trades
                            SET market_question = ?
                            WHERE id = ?
                        """, (question, trade_id))
                        conn.commit()
                        conn.close()
                        
                        print(f"  ✅ Updated trade {trade_id} in database")
                        updated_count += 1
                    except Exception as e:
                        print(f"  ❌ Failed to update database: {e}")
                        failed_count += 1
            else:
                # API failed or returned wrong market - try template generation
                template_question = generate_question_template(market_name, category=None)
                
                if template_question:
                    fallback_question = template_question
                    print(f"  ✅ Generated template question from market name")
                    print(f"     Template: {fallback_question[:80]}...")
                else:
                    # Use database name as last resort
                    fallback_question = market_name
                    print(f"  ⚠️  API failed/wrong market - using database name as fallback: {fallback_question[:60]}...")
                    print(f"     Note: This may be too abbreviated for UMA resolution. Manual entry recommended.")
                
                if dry_run:
                    print(f"  [DRY RUN] Would update trade {trade_id} with fallback question")
                else:
                    # Update database with fallback
                    try:
                        conn = signal_store._get_connection()
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE paper_trades
                            SET market_question = ?
                            WHERE id = ?
                        """, (fallback_question, trade_id))
                        conn.commit()
                        conn.close()
                        
                        print(f"  ⚠️  Updated trade {trade_id} with fallback question (may need manual correction)")
                        updated_count += 1
                    except Exception as e:
                        print(f"  ❌ Failed to update database: {e}")
                        failed_count += 1
            
            print()  # Blank line between trades
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)
    
    return (total_trades, updated_count, failed_count)


async def main():
    parser = argparse.ArgumentParser(
        description="Backfill market_question for existing paper trades"
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Actually update database (default is dry-run)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of trades to process (default: all)"
    )
    args = parser.parse_args()
    
    dry_run = not args.update
    
    print("=" * 80)
    if dry_run:
        print("🔍 DRY RUN MODE - No database changes will be made")
    else:
        print("⚠️  UPDATE MODE - Database will be modified")
    print("=" * 80)
    
    if not dry_run:
        # Skip confirmation if running non-interactively (e.g., from script)
        if sys.stdin.isatty():
            response = input("\n⚠️  Are you sure you want to update the database? (yes/no): ")
            if response.lower() != "yes":
                print("❌ Cancelled")
                return
        else:
            print("\n⚠️  Running in non-interactive mode - proceeding with database updates")
    
    total, updated, failed = await backfill_questions(dry_run=dry_run, limit=args.limit)
    
    print("\n" + "=" * 80)
    print("📊 Summary:")
    print(f"   Total processed: {total}")
    print(f"   ✅ Updated: {updated}")
    print(f"   ❌ Failed: {failed}")
    if dry_run:
        print(f"\n💡 Run with --update to actually update the database")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())

