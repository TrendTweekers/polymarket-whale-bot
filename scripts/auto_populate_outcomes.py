#!/usr/bin/env python3
"""
Automated script to populate KNOWN_OUTCOMES_BY_CONDITION by searching web for game results.

This script:
1. Queries database for open trades with market names, condition_ids, outcome_index
2. Uses web search to find game results (e.g., "exact score Bulls vs Hawks December 21 2025")
3. Parses results to determine winning_outcome_index (0 for YES/first team/home/cover, 1 for NO/second/away/didn't cover)
4. Adds to KNOWN_OUTCOMES_BY_CONDITION dict in manual_resolve_trades.py
5. Handles batches (limit 50 per run) and errors gracefully
"""

import sys
import os
import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import time
import random

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from src.polymarket.storage import SignalStore

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Try to import web search capability
try:
    from googlesearch import search as google_search
    WEB_SEARCH_AVAILABLE = True
except ImportError:
    WEB_SEARCH_AVAILABLE = False
    print("Warning: googlesearch not available. Install with: pip install googlesearch-python")

try:
    import requests
    from bs4 import BeautifulSoup
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("Warning: requests/BeautifulSoup not available. Install with: pip install requests beautifulsoup4")


def extract_market_info(market_name: str) -> Dict[str, any]:
    """
    Extract market type and teams from market name.
    Enhanced to handle multiple formats including spreads without "vs", esports, etc.
    
    Returns:
        {
            "type": "moneyline" | "spread" | "total" | "unknown",
            "team1": str,
            "team2": str,
            "spread": float | None,
            "total": float | None
        }
    """
    market_lower = market_name.lower()
    info = {
        "type": "unknown",
        "team1": None,
        "team2": None,
        "spread": None,
        "total": None
    }
    
    # First, try to extract teams using "vs" pattern (most common)
    vs_match = re.search(r'(.+?)\s+vs\.?\s+(.+)', market_name, re.IGNORECASE)
    team1_candidate = None
    team2_candidate = None
    
    if vs_match:
        team1_candidate = vs_match.group(1).strip()
        team2_candidate = vs_match.group(2).strip()
        # Clean up team names (remove trailing colons, parentheses, etc.)
        team1_candidate = re.sub(r'[:]\s*$', '', team1_candidate).strip()
        team2_candidate = re.sub(r'[:]\s*$', '', team2_candidate).strip()
        # Remove market type suffixes from team2
        team2_candidate = re.sub(r'\s*(?:spread|o/u|total|over|under|moneyline|winner|game\s+\d+|bo\d+).*$', '', team2_candidate, flags=re.IGNORECASE).strip()
    
    # Detect spread market (e.g., "Spread: Texans (-14.5)" or "Texans -14.5" or "1H Spread: Spurs (-9.5)")
    spread_match = re.search(r'(?:1h\s+)?spread[:\s]+(.+?)\s*\(?([+-]?\d+\.?\d*)\)?', market_lower)
    if not spread_match:
        # Try pattern like "Team (-X.X)" or "Team -X.X"
        spread_match = re.search(r'(.+?)\s*\(?([+-]\d+\.?\d*)\)?', market_lower)
        # Verify it's actually a spread (has +/- sign)
        if spread_match and ('+' in spread_match.group(2) or '-' in spread_match.group(2)):
            pass  # Valid spread
        else:
            spread_match = None
    
    if spread_match:
        info["type"] = "spread"
        favorite = spread_match.group(1).strip()
        spread = float(spread_match.group(2))
        info["spread"] = spread
        
        # If we found teams via "vs", use them
        if team1_candidate and team2_candidate:
            info["team1"] = team1_candidate
            info["team2"] = team2_candidate
        else:
            # Try to extract teams from spread market name
            # Pattern: "Spread: Team1 vs Team2" or "Team1 vs Team2: Spread"
            parts = market_name.split(":")
            for part in parts:
                vs_in_part = re.search(r'(.+?)\s+vs\.?\s+(.+)', part, re.IGNORECASE)
                if vs_in_part:
                    info["team1"] = vs_in_part.group(1).strip()
                    info["team2"] = vs_in_part.group(2).strip()
                    break
    
    # Detect total/over-under market (e.g., "O/U 226.5" or "Total: 224.5" or "1H O/U 122.5")
    elif "o/u" in market_lower or ("over" in market_lower and "under" in market_lower) or "total" in market_lower:
        info["type"] = "total"
        # Try multiple patterns for total
        total_match = re.search(r'(?:1h\s+)?(?:o/u|total)[:\s]+(\d+\.?\d*)', market_lower)
        if not total_match:
            total_match = re.search(r'(\d+\.?\d*)\s*(?:o/u|total)', market_lower)
        if total_match:
            info["total"] = float(total_match.group(1))
        
        # If we found teams via "vs", use them
        if team1_candidate and team2_candidate:
            info["team1"] = team1_candidate
            info["team2"] = team2_candidate
        else:
            # Try to extract teams from total market name
            vs_match = re.search(r'(.+?)\s+vs\.?\s+(.+?)(?:\s*[:]?\s*(?:o/u|total|over|under))', market_name, re.IGNORECASE)
            if vs_match:
                info["team1"] = vs_match.group(1).strip()
                info["team2"] = vs_match.group(2).strip()
    
    # Detect moneyline (simple "Team1 vs Team2" or esports formats)
    else:
        if team1_candidate and team2_candidate:
            info["type"] = "moneyline"
            info["team1"] = team1_candidate
            info["team2"] = team2_candidate
        else:
            # Try esports format: "Game: Team1 vs Team2" or "Team1 vs Team2 - Game X Winner"
            esports_match = re.search(r'(?:game\s+\d+|bo\d+)[:\s]+(.+?)\s+vs\.?\s+(.+)', market_name, re.IGNORECASE)
            if not esports_match:
                esports_match = re.search(r'(.+?)\s+vs\.?\s+(.+?)\s*[-]\s*(?:game|winner)', market_name, re.IGNORECASE)
            if esports_match:
                info["type"] = "moneyline"
                info["team1"] = esports_match.group(1).strip()
                info["team2"] = esports_match.group(2).strip()
            else:
                # Last resort: try to find any "vs" pattern
                vs_match = re.search(r'(.+?)\s+vs\.?\s+(.+)', market_name, re.IGNORECASE)
                if vs_match:
                    info["type"] = "moneyline"
                    info["team1"] = vs_match.group(1).strip()
                    info["team2"] = vs_match.group(2).strip()
    
    # Clean up team names (remove common suffixes/prefixes)
    if info["team1"]:
        info["team1"] = re.sub(r'\s*(?:spread|o/u|total|over|under|moneyline|winner|game\s+\d+|bo\d+|map\s+\d+).*$', '', info["team1"], flags=re.IGNORECASE).strip()
        info["team1"] = re.sub(r'^.*?:\s*', '', info["team1"]).strip()  # Remove prefix like "LoL:"
    if info["team2"]:
        info["team2"] = re.sub(r'\s*(?:spread|o/u|total|over|under|moneyline|winner|game\s+\d+|bo\d+|map\s+\d+).*$', '', info["team2"], flags=re.IGNORECASE).strip()
        info["team2"] = re.sub(r'^.*?:\s*', '', info["team2"]).strip()  # Remove prefix
    
    return info


def parse_score_from_text(text: str, team1: str, team2: str) -> Optional[Dict]:
    """
    Parse game score from text using multiple patterns.
    
    Returns:
        {
            "team1_score": int,
            "team2_score": int,
            "winner": str,  # team1 or team2
            "total_points": int,
            "spread_result": float
        }
    """
    if not text or not team1 or not team2:
        return None
    
    text_lower = text.lower()
    team1_lower = team1.lower()
    team2_lower = team2.lower()
    
    # Pattern 1: "Team1 won X-Y" or "Team1 beats Team2 X-Y"
    won_patterns = [
        rf'({re.escape(team1)}|{re.escape(team2)})\s+(?:won|beat|defeated)\s+(?:.{0,50}?)?(\d+)[-\s]+(\d+)',
        rf'({re.escape(team1)}|{re.escape(team2)})\s+(\d+)[-\s]+(\d+)',
        rf'(\d+)[-\s]+(\d+).*?(?:{re.escape(team1)}|{re.escape(team2)})',
    ]
    
    for pattern in won_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                if len(match.groups()) == 3:
                    winner_text = match.group(1)
                    score1 = int(match.group(2))
                    score2 = int(match.group(3))
                    
                    # Determine which team won
                    if team1_lower in winner_text.lower():
                        return {
                            "team1_score": score1,
                            "team2_score": score2,
                            "winner": team1,
                            "total_points": score1 + score2,
                            "spread_result": score1 - score2
                        }
                    elif team2_lower in winner_text.lower():
                        return {
                            "team1_score": score2,
                            "team2_score": score1,
                            "winner": team2,
                            "total_points": score1 + score2,
                            "spread_result": score2 - score1
                        }
                    else:
                        # Can't determine winner from text, use score order
                        return {
                            "team1_score": score1,
                            "team2_score": score2,
                            "winner": team1 if score1 > score2 else team2,
                            "total_points": score1 + score2,
                            "spread_result": score1 - score2
                        }
            except (ValueError, IndexError):
                continue
    
    # Pattern 2: "Team1 X Team2 Y" or "X-Y" near team names
    # Filter out unrealistic scores (e.g., >200 for most sports, >100 for football)
    score_pattern = re.search(r'\b(\d{1,3})[-\s]+(\d{1,3})\b', text)
    if score_pattern:
        try:
            score1 = int(score_pattern.group(1))
            score2 = int(score_pattern.group(2))
            
            # Filter out unrealistic scores
            # Basketball: typically 80-150 per team
            # Football: typically 0-50 per team
            # Hockey: typically 0-10 per team
            # Reject if either score > 200 (likely page number, timestamp, etc.)
            if score1 > 200 or score2 > 200:
                return None
            
            # Reject if scores are identical and very high (likely false positive)
            if score1 == score2 and score1 > 100:
                return None
            
            # Try to determine order based on team positions
            team1_pos = text_lower.find(team1_lower)
            team2_pos = text_lower.find(team2_lower)
            score_pos = score_pattern.start()
            
            # If team1 appears before score and team2 after, assume team1 has first score
            if team1_pos != -1 and team2_pos != -1:
                if team1_pos < score_pos < team2_pos:
                    return {
                        "team1_score": score1,
                        "team2_score": score2,
                        "winner": team1 if score1 > score2 else team2,
                        "total_points": score1 + score2,
                        "spread_result": score1 - score2
                    }
                elif team2_pos < score_pos < team1_pos:
                    return {
                        "team1_score": score2,
                        "team2_score": score1,
                        "winner": team1 if score2 > score1 else team2,
                        "total_points": score1 + score2,
                        "spread_result": score2 - score1
                    }
            
            # Default: assume first score is team1
            return {
                "team1_score": score1,
                "team2_score": score2,
                "winner": team1 if score1 > score2 else team2,
                "total_points": score1 + score2,
                "spread_result": score1 - score2
            }
        except (ValueError, IndexError):
            pass
    
    return None


def fetch_url_content(url: str) -> Optional[str]:
    """Fetch HTML content from URL with error handling."""
    if not REQUESTS_AVAILABLE:
        return None
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            # Ensure we have bytes before decoding
            if isinstance(response.content, bytes):
                return response.content.decode('utf-8', errors='ignore')
            return str(response.text)
    except Exception as e:
        pass
    
    return None


def search_game_result(market_name: str, market_info: Dict, date_str: str = "December 21 2025") -> Optional[Dict]:
    """
    Search web for game result and parse it.
    
    Returns:
        {
            "team1_score": int,
            "team2_score": int,
            "winner": str,
            "total_points": int,
            "spread_result": float
        }
    """
    if not WEB_SEARCH_AVAILABLE and not REQUESTS_AVAILABLE:
        return None
    
    team1 = market_info.get("team1", "")
    team2 = market_info.get("team2", "")
    
    if not team1 or not team2:
        return None
    
    # Build search queries
    queries = [
        f"{team1} vs {team2} {date_str} final score",
        f"{team1} vs {team2} {date_str} score result",
        f"exact score {team1} vs {team2} {date_str}",
        f"{team1} {team2} {date_str} game result",
    ]
    
    print(f"  Searching: {queries[0]}")
    
    # Try web search API
    if WEB_SEARCH_AVAILABLE:
        for query in queries:
            try:
                # Use num_results parameter (newer API)
                try:
                    results = list(google_search(query, num_results=5, pause=2))
                except TypeError:
                    # Fallback to older API
                    results = list(google_search(query, stop=5, pause=2))
                
                if results:
                    # Try to parse first few results
                    for url in results[:3]:
                        html_content = fetch_url_content(url)
                        if html_content:
                            result = parse_score_from_text(html_content, team1, team2)
                            if result:
                                return result
            except Exception:
                continue
    
    # Fallback: Try direct Google search page scraping
    if REQUESTS_AVAILABLE:
        try:
            query = queries[0].replace(' ', '+')
            search_url = f"https://www.google.com/search?q={query}"
            html_content = fetch_url_content(search_url)
            if html_content:
                result = parse_score_from_text(html_content, team1, team2)
                if result:
                    return result
        except Exception:
            pass
    
    return None


def determine_winning_outcome_index(market_info: Dict, result: Dict, outcome_name: str = "") -> Optional[int]:
    """
    Determine winning_outcome_index (0 or 1) based on market type and result.
    
    Returns:
        0 for YES/first team/home/cover
        1 for NO/second team/away/didn't cover
        None if cannot determine
    """
    market_type = market_info["type"]
    team1 = market_info.get("team1", "")
    team2 = market_info.get("team2", "")
    
    if market_type == "spread":
        # Spread market: 0 = cover, 1 = don't cover
        spread = market_info.get("spread", 0)
        spread_result = result.get("spread_result", 0)
        winner = result.get("winner", "")
        
        # Determine if favorite covered
        # If spread is negative (e.g., -14.5), favorite needs to win by more than 14.5
        # If spread is positive (e.g., +14.5), underdog needs to lose by less than 14.5
        
        if spread < 0:  # Favorite has negative spread
            # Favorite covers if they win by more than |spread|
            if winner.lower() in team1.lower():
                # Team1 is favorite, check if they covered
                return 0 if abs(spread_result) > abs(spread) else 1
            elif winner.lower() in team2.lower():
                # Team2 is favorite, check if they covered
                return 1 if abs(spread_result) > abs(spread) else 0
        else:  # Underdog has positive spread
            # Underdog covers if they lose by less than spread or win
            if abs(spread_result) < spread or spread_result > 0:
                return 1  # Underdog covered
            else:
                return 0  # Favorite covered
    
    elif market_type == "total":
        # Total market: 0 = Over, 1 = Under
        total = market_info.get("total", 0)
        total_points = result.get("total_points", 0)
        
        if total_points > total:
            return 0  # Over
        elif total_points < total:
            return 1  # Under
        else:
            # Push - return None or handle tie
            return None
    
    elif market_type == "moneyline":
        # Moneyline: 0 = team1 wins, 1 = team2 wins
        winner = result.get("winner", "")
        
        if winner.lower() in team1.lower():
            return 0  # Team1 wins
        elif winner.lower() in team2.lower():
            return 1  # Team2 wins
    
    return None


def get_open_trades_with_markets(limit: Optional[int] = None) -> List[Dict]:
    """Get open trades with market information."""
    store = SignalStore()
    conn = store._get_connection()
    conn.row_factory = lambda cursor, row: {
        col[0]: row[idx] for idx, col in enumerate(cursor.description)
    }
    cursor = conn.cursor()
    
    query = """
        SELECT DISTINCT
            pt.event_id,
            s.market as market_name,
            pt.outcome_name,
            pt.outcome_index,
            pt.opened_at,
            pt.stake_usd
        FROM paper_trades pt
        LEFT JOIN signals s ON pt.signal_id = s.id
        WHERE pt.status = 'OPEN'
        AND pt.event_id IS NOT NULL
        AND pt.event_id != ''
        AND pt.event_id != '0x'
        AND s.market IS NOT NULL
        ORDER BY pt.stake_usd DESC, pt.opened_at DESC
    """
    
    if limit:
        query += f" LIMIT {limit}"
    
    cursor.execute(query)
    trades = cursor.fetchall()
    conn.close()
    
    return trades


def update_manual_resolve_script(outcomes: Dict[str, Dict]):
    """Update KNOWN_OUTCOMES_BY_CONDITION in manual_resolve_trades.py."""
    script_path = project_root / "scripts" / "manual_resolve_trades.py"
    
    if not script_path.exists():
        print(f"ERROR: {script_path} not found!")
        return
    
    # Read current file
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"ERROR: Could not read {script_path}: {e}")
        return
    
    # Find KNOWN_OUTCOMES_BY_CONDITION dict
    # Look for the dict definition - find the opening brace
    pattern = r'(KNOWN_OUTCOMES_BY_CONDITION\s*=\s*\{)'
    match = re.search(pattern, content)
    
    if not match:
        print("ERROR: Could not find KNOWN_OUTCOMES_BY_CONDITION dict in script")
        return
    
    # Find the insertion point (before the closing brace or comment "# Add more condition_ids")
    insert_marker = "# Add more condition_ids here as outcomes become known"
    insert_pos = content.find(insert_marker)
    
    if insert_pos == -1:
        # Try to find the closing brace of the dict
        dict_start = match.end()
        brace_count = 1
        insert_pos = dict_start
        for i in range(dict_start, len(content)):
            if content[i] == '{':
                brace_count += 1
            elif content[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    insert_pos = i
                    break
    
    if insert_pos == -1:
        print("ERROR: Could not find insertion point in dict")
        return
    
    # Build new entries
    new_entries = []
    for cond_id, outcome in outcomes.items():
        note = outcome["note"].replace('"', '\\"')  # Escape quotes
        new_entries.append(f'    "{cond_id}": {{  # Auto-populated')
        new_entries.append(f'        "winning_outcome_index": {outcome["winning_outcome_index"]},')
        new_entries.append(f'        "note": "{note}"')
        new_entries.append(f'    }},')
    
    if new_entries:
        # Insert before the marker or closing brace
        new_content = (
            content[:insert_pos] +
            '\n' + '\n'.join(new_entries) + '\n' +
            content[insert_pos:]
        )
        
        # Write back
        try:
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"   ✅ Added {len(outcomes)} new outcomes to script")
        except Exception as e:
            print(f"ERROR: Could not write to {script_path}: {e}")
    else:
        print("   No new outcomes to add")


def populate_outcomes(limit: int = 50, dry_run: bool = False, date_str: str = "December 21 2025") -> Dict:
    """
    Main function to populate outcomes.
    
    Args:
        limit: Maximum number of trades to process
        dry_run: If True, don't update files
        date_str: Date string for search queries
    
    Returns:
        Dict with results summary
    """
    print("=" * 80)
    print("Auto-Populate Outcomes Script")
    print("=" * 80)
    
    if not WEB_SEARCH_AVAILABLE and not REQUESTS_AVAILABLE:
        print("\nERROR: No web search capability available!")
        print("Install: pip install googlesearch-python requests beautifulsoup4")
        return {"error": "No web search available"}
    
    # Get open trades
    print(f"\n1. Querying database for open trades (limit: {limit})...")
    trades = get_open_trades_with_markets(limit=limit)
    print(f"   Found {len(trades)} open trades")
    
    if not trades:
        print("   No open trades found!")
        return {"processed": 0, "found": 0, "added": 0}
    
    # Group by market name to avoid duplicate searches
    markets_dict = {}
    for trade in trades:
        market_name = trade.get("market_name", "Unknown")
        event_id = trade.get("event_id", "")
        
        if not event_id or event_id == "0x":
            continue
        
        # Use first 20 chars as key (matching manual_resolve_trades.py format)
        event_id_prefix = event_id[:20] if len(event_id) >= 20 else event_id
        
        if market_name not in markets_dict:
            markets_dict[market_name] = {
                "event_id": event_id_prefix,
                "full_event_id": event_id,
                "outcome_name": trade.get("outcome_name", ""),
                "outcome_index": trade.get("outcome_index"),
                "trades": []
            }
        markets_dict[market_name]["trades"].append(trade)
    
    print(f"   Unique markets: {len(markets_dict)}")
    
    # Process each market
    print(f"\n2. Searching for game results...")
    outcomes = {}
    found_count = 0
    error_count = 0
    
    for idx, (market_name, market_data) in enumerate(markets_dict.items(), 1):
        if idx > limit:
            break
        
        event_id_prefix = market_data["event_id"]
        if not event_id_prefix:
            continue
        
        print(f"\n[{idx}/{min(len(markets_dict), limit)}] {market_name[:60]}...")
        print(f"  Condition ID: {event_id_prefix}...")
        
        # Extract market info
        market_info = extract_market_info(market_name)
        print(f"  Market Type: {market_info['type']}")
        
        if market_info["type"] == "unknown" or not market_info.get("team1") or not market_info.get("team2"):
            print(f"  [SKIP] Cannot extract teams or market type")
            error_count += 1
            continue
        
        # Search for result
        result = search_game_result(market_name, market_info, date_str)
        
        if result:
            print(f"  ✅ Found result: {result.get('team1_score', '?')}-{result.get('team2_score', '?')}")
            print(f"     Winner: {result.get('winner', 'Unknown')}")
            
            # Determine winning outcome index
            outcome_name = market_data.get("outcome_name", "")
            winning_index = determine_winning_outcome_index(market_info, result, outcome_name)
            
            if winning_index is not None:
                # Build note
                if market_info["type"] == "spread":
                    cover_text = "covered" if winning_index == 0 else "didn't cover"
                    note = f"{result.get('winner', 'Unknown')} {cover_text} {market_info.get('spread', 0)} spread"
                elif market_info["type"] == "total":
                    over_under = "Over" if winning_index == 0 else "Under"
                    note = f"Total: {result.get('total_points', 0)} ({over_under} {market_info.get('total', 0)})"
                else:
                    note = f"{result.get('winner', 'Unknown')} won {result.get('team1_score', '?')}-{result.get('team2_score', '?')}"
                
                outcomes[event_id_prefix] = {
                    "winning_outcome_index": winning_index,
                    "note": note
                }
                found_count += 1
                print(f"  [OK] Added: winning_outcome_index={winning_index}")
            else:
                print(f"  [WARN] Could not determine winning outcome index")
                error_count += 1
        else:
            print(f"  [FAIL] No result found")
            error_count += 1
        
        # Rate limiting - random delay between 1-3 seconds
        if idx < len(markets_dict):
            delay = random.uniform(1, 3)
            time.sleep(delay)
    
    print(f"\n3. Results Summary:")
    print(f"   Found results: {found_count}")
    print(f"   Errors/Not found: {error_count}")
    print(f"   Total outcomes: {len(outcomes)}")
    
    # Output results
    if not dry_run and outcomes:
        update_manual_resolve_script(outcomes)
        print(f"\n4. ✅ Updated scripts/manual_resolve_trades.py")
    elif dry_run:
        print(f"\n4. [DRY RUN] Would add {len(outcomes)} outcomes")
        print("\nSample outcomes:")
        for cond_id, outcome in list(outcomes.items())[:5]:
            print(f"  {cond_id}: {outcome}")
    
    return {
        "processed": len(markets_dict),
        "found": found_count,
        "added": len(outcomes),
        "errors": error_count,
        "outcomes": outcomes
    }


def main():
    parser = argparse.ArgumentParser(
        description="Auto-populate outcomes by searching web for game results"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of markets to process (default: 50)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't update files, just show what would be added"
    )
    parser.add_argument(
        "--date",
        type=str,
        default="December 21 2025",
        help="Date string for search queries (default: 'December 21 2025')"
    )
    
    args = parser.parse_args()
    
    results = populate_outcomes(
        limit=args.limit,
        dry_run=args.dry_run,
        date_str=args.date
    )
    
    print("\n" + "=" * 80)
    print("Summary:")
    print(f"  Processed: {results.get('processed', 0)} markets")
    print(f"  Found results: {results.get('found', 0)}")
    print(f"  Added outcomes: {results.get('added', 0)}")
    print(f"  Errors: {results.get('errors', 0)}")
    print("=" * 80)
    
    if results.get('added', 0) > 0 and not args.dry_run:
        print("\n💡 Next step: Run 'python scripts/manual_resolve_trades.py --all-known' to resolve trades")


if __name__ == "__main__":
    main()
