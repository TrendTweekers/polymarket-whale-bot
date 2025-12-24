# src/polymarket/uma_resolver.py
"""
On-chain UMA OptimisticOracleV3 resolver for Polymarket markets.

Polymarket markets are resolved on-chain via UMA's Optimistic Oracle on Polygon.
This module queries the OptimisticOracleV3 contract directly to get resolution data.

Uses:
- OptimisticOracleV3: 0x5953f2538F613E05bAED8A5AeFa8e6622467AD3D (Polygon)
- Identifier: YES_OR_NO_QUERY (keccak256 hash)
- AncillaryData format: b'q:"market_title"' + requester params
"""
import os
import json
import structlog
from typing import Optional, Dict, Tuple
from web3 import Web3
from datetime import datetime

# Try to import POA middleware (may not be needed or available in all web3 versions)
try:
    from web3.middleware import geth_poa_middleware
    POA_MIDDLEWARE_AVAILABLE = True
except ImportError:
    try:
        from web3.middleware import ExtraDataToPOAMiddleware as geth_poa_middleware
        POA_MIDDLEWARE_AVAILABLE = True
    except ImportError:
        POA_MIDDLEWARE_AVAILABLE = False

logger = structlog.get_logger()

# UMA OptimisticOracleV3 contract address (Polygon mainnet - Chain ID 137)
# Source: UMA official network data for Polygon
# V3 (MOOV2) is current as of 2025
UMA_OO_V3_ADDRESS = "0x5953f2538F613E05bAED8A5AeFa8e6622467AD3D"  # OptimisticOracleV3 on Polygon

# Legacy V2 address (Ethereum mainnet) - kept for fallback
UMA_OO_V2_ADDRESS = "0xA0Ae660944944e720534d9D5135E5e22D7b5e8C7"  # OptimisticOracleV2 on Ethereum

# RPC endpoint (use Infura, Alchemy, or public RPC)
# Default to Polygon RPC (Polymarket uses Polygon)
POLYGON_RPC_URL = os.getenv("POLYGON_RPC_URL", os.getenv("ETH_RPC_URL", "https://polygon-rpc.com"))
ETH_RPC_URL = os.getenv("ETH_RPC_URL", "https://eth.llamarpc.com")  # Fallback for Ethereum

# Polymarket's UmaCtfAdapter (Requester)
POLYMARKET_REQUESTER = "0x2F5e3684cb1F318ec51b00Edba38d79Ac2c0aA9d"

# OptimisticOracleV3 ABI (minimal - only functions we need)
# V3 has same interface as V2 for our use case
OO_V3_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "identifier", "type": "bytes32"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
            {"internalType": "bytes", "name": "ancillaryData", "type": "bytes"}
        ],
        "name": "getRequest",
        "outputs": [
            {
                "components": [
                    {"internalType": "bytes32", "name": "proposer", "type": "bytes32"},
                    {"internalType": "address", "name": "proposerAddress", "type": "address"},
                    {"internalType": "address", "name": "disputer", "type": "address"},
                    {"internalType": "address", "name": "currency", "type": "address"},
                    {"internalType": "bool", "name": "settled", "type": "bool"},
                    {"internalType": "bool", "name": "refundOnDispute", "type": "bool"},
                    {"internalType": "int256", "name": "proposedPrice", "type": "int256"},
                    {"internalType": "int256", "name": "resolvedPrice", "type": "int256"},
                    {"internalType": "uint256", "name": "expirationTime", "type": "uint256"},
                    {"internalType": "uint256", "name": "reward", "type": "uint256"},
                    {"internalType": "uint256", "name": "finalFee", "type": "uint256"},
                    {"internalType": "uint256", "name": "bond", "type": "uint256"},
                    {"internalType": "uint256", "name": "customLiveness", "type": "uint256"}
                ],
                "internalType": "struct OptimisticOracleV2Interface.Request",
                "name": "",
                "type": "tuple"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "identifier", "type": "bytes32"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
            {"internalType": "bytes", "name": "ancillaryData", "type": "bytes"}
        ],
        "name": "hasPrice",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# ConditionalTokenFramework (CTF) ABI - to get ancillaryData from condition_id
CTF_ADDRESS_POLYGON = "0x4D97DCd97eC945f40CF65B8703ACB7d0dc4a97C4"  # CTF on Polygon
CTF_ADDRESS_ETH = "0x4D97DCd97eC945f40CF65B8703ACB7d0dc4a97C4"  # CTF on Ethereum
CTF_ABI = [
    {
        "inputs": [{"internalType": "bytes32", "name": "conditionId", "type": "bytes32"}],
        "name": "getCondition",
        "outputs": [
            {"internalType": "address", "name": "questionId", "type": "address"},
            {"internalType": "uint256", "name": "outcomeSlotCount", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

# UMA Identifier for Polymarket binary markets
UMA_IDENTIFIER = "YES_OR_NO_QUERY"  # bytes32 keccak256 hash

# Initialize Web3 connection
_w3_polygon = None
_w3_eth = None
_oo_v3_contract = None
_oo_v2_contract = None
_ctf_contract = None


def get_web3_polygon() -> Web3:
    """Get or create Web3 instance for Polygon."""
    global _w3_polygon
    if _w3_polygon is None:
        _w3_polygon = Web3(Web3.HTTPProvider(POLYGON_RPC_URL))
        # Add POA middleware for Polygon
        if POA_MIDDLEWARE_AVAILABLE:
            try:
                _w3_polygon.middleware_onion.inject(geth_poa_middleware, layer=0)
            except:
                pass
    return _w3_polygon


def get_web3_eth() -> Web3:
    """Get or create Web3 instance for Ethereum (fallback)."""
    global _w3_eth
    if _w3_eth is None:
        _w3_eth = Web3(Web3.HTTPProvider(ETH_RPC_URL))
    return _w3_eth


def get_web3() -> Web3:
    """Get Polygon Web3 instance (default for Polymarket)."""
    return get_web3_polygon()


def get_oo_v3_contract():
    """Get OptimisticOracleV3 contract instance (Polygon)."""
    global _oo_v3_contract
    if _oo_v3_contract is None:
        w3 = get_web3_polygon()
        _oo_v3_contract = w3.eth.contract(
            address=Web3.to_checksum_address(UMA_OO_V3_ADDRESS), 
            abi=OO_V3_ABI
        )
    return _oo_v3_contract


def get_oo_v2_contract():
    """Get OptimisticOracleV2 contract instance (Ethereum fallback)."""
    global _oo_v2_contract
    if _oo_v2_contract is None:
        w3 = get_web3_eth()
        _oo_v2_contract = w3.eth.contract(
            address=Web3.to_checksum_address(UMA_OO_V2_ADDRESS), 
            abi=OO_V3_ABI  # Same ABI
        )
    return _oo_v2_contract


def get_ctf_contract():
    """Get CTF contract instance (Polygon)."""
    global _ctf_contract
    if _ctf_contract is None:
        w3 = get_web3_polygon()
        _ctf_contract = w3.eth.contract(
            address=Web3.to_checksum_address(CTF_ADDRESS_POLYGON), 
            abi=CTF_ABI
        )
    return _ctf_contract


def condition_id_to_bytes32(condition_id: str) -> bytes:
    """Convert condition_id hex string to bytes32."""
    # Remove 0x prefix if present
    if condition_id.startswith("0x"):
        condition_id = condition_id[2:]
    # Pad to 64 hex chars (32 bytes)
    condition_id = condition_id.zfill(64)
    return bytes.fromhex(condition_id)


def get_ancillary_data_from_market(market_title: str, requester: Optional[str] = None) -> bytes:
    """
    Build ancillaryData from market title (Polymarket JSON format).
    
    Polymarket uses a JSON dict format with specific keys:
    {
        'q': 'full question text',
        'p1': 0,
        'p2': 1000000000000000000,  # 1e18
        'p3': 2,  # For binary markets
        'rebate': 0
    }
    
    The JSON must be sorted (sort_keys=True) for consistency.
    
    Args:
        market_title: Market title/question text
        requester: Optional requester address (not used in JSON format)
    
    Returns:
        AncillaryData bytes (JSON encoded)
    """
    # Build JSON dict with required fields
    ancillary_dict = {
        'q': market_title,
        'p1': 0,
        'p2': 1000000000000000000,  # 1e18 (wei)
        'p3': 2,  # For binary markets
        'rebate': 0
    }
    
    # Encode as JSON with sorted keys for consistency
    ancillary_data = json.dumps(ancillary_dict, sort_keys=True).encode('utf-8')
    
    return ancillary_data


def get_ancillary_data_from_condition(condition_id: str, market_title: Optional[str] = None, question_id_address: Optional[str] = None) -> Tuple[Optional[bytes], Optional[int], Optional[int]]:
    """
    Get ancillaryData and timestamp from condition_id or market title.
    
    For Polymarket:
    - Preferred: Use market_title to build ancillaryData in format: b'q:"title"'
    - Fallback: Use questionId from CTF or API
    - Timestamp: Market end time from metadata (or 0 for latest)
    
    Args:
        condition_id: Market condition ID
        market_title: Market title/question text (preferred for ancillaryData)
        question_id_address: Optional questionId address (if available from API)
    
    Returns:
        (ancillaryData, timestamp, chain_id) or (None, None, None) if not found
    """
    w3 = get_web3_polygon()
    timestamp = 0  # Default to latest
    
    # Preferred method: Use market_title to build proper ancillaryData
    if market_title:
        try:
            ancillary_data = get_ancillary_data_from_market(market_title, POLYMARKET_REQUESTER)
            logger.debug("uma_ancillary_data_from_title",
                        condition_id=condition_id[:20],
                        title_len=len(market_title),
                        ancillary_data_len=len(ancillary_data))
            return ancillary_data, timestamp, 137  # Polygon chain ID
        except Exception as e:
            logger.debug("uma_ancillary_data_from_title_failed",
                        condition_id=condition_id[:20],
                        error=str(e))
    
    # Fallback: Try to get questionId from CTF
    question_id = None
    if question_id_address:
        question_id = question_id_address
    else:
        try:
            ctf = get_ctf_contract()
            condition_bytes = condition_id_to_bytes32(condition_id)
            condition_data = ctf.functions.getCondition(condition_bytes).call()
            question_id = condition_data[0]
        except Exception as e:
            logger.debug("uma_ctf_lookup_failed",
                        condition_id=condition_id[:20],
                        error=str(e))
    
    # If we have a questionId, use it (legacy method)
    if question_id and question_id != "0x0000000000000000000000000000000000000000":
        try:
            question_id_clean = question_id.lower().replace("0x", "")
            question_id_bytes = bytes.fromhex(question_id_clean)
            ancillary_data = question_id_bytes.rjust(32, b'\x00')
            logger.debug("uma_ancillary_data_from_question_id",
                        condition_id=condition_id[:20],
                        question_id=question_id)
            return ancillary_data, timestamp, 137
        except Exception as e:
            logger.debug("uma_ancillary_data_encode_failed",
                        condition_id=condition_id[:20],
                        error=str(e))
    
    # Last resort: Use condition_id directly
    try:
        condition_bytes = condition_id_to_bytes32(condition_id)
        ancillary_data = condition_bytes[:32] if len(condition_bytes) >= 32 else condition_bytes.rjust(32, b'\x00')
        logger.debug("uma_using_condition_id_as_ancillary",
                    condition_id=condition_id[:20])
        return ancillary_data, timestamp, 137
    except Exception as e:
        logger.warning("uma_get_ancillary_data_failed",
                      condition_id=condition_id[:20],
                      error=str(e))
        return None, None, None


def check_uma_resolution(condition_id: str, market_title: Optional[str] = None, question_id_address: Optional[str] = None, end_date_iso: Optional[str] = None) -> Optional[Dict]:
    """
    Check if market is resolved on-chain via UMA OptimisticOracleV3 (Polygon).
    
    Args:
        condition_id: Market condition ID
        market_title: Market title/question text (preferred for ancillaryData)
        question_id_address: Optional questionId address (fallback)
        end_date_iso: Optional market end date (ISO format) for timestamp
    
    Returns:
        Dict with:
        - resolved: bool
        - winning_outcome_index: int or None
        - resolved_price: float (0.0 or 1.0 for binary markets)
        - resolution_time: str or None
        Or None on error
    """
    try:
        # Use V3 contract (Polygon)
        oo = get_oo_v3_contract()
        w3 = get_web3_polygon()
        
        # Calculate timestamp from end_date_iso if provided
        timestamp = 0  # Default to latest
        if end_date_iso:
            try:
                from datetime import datetime
                end_dt = datetime.fromisoformat(end_date_iso.replace('Z', '+00:00'))
                timestamp = int(end_dt.timestamp())
            except Exception as e:
                logger.debug("uma_timestamp_parse_failed",
                            condition_id=condition_id[:20],
                            end_date=end_date_iso,
                            error=str(e))
        
        # Get ancillaryData and timestamp from condition_id or market_title
        result = get_ancillary_data_from_condition(condition_id, market_title, question_id_address)
        if result[0] is None:
            logger.debug("uma_no_ancillary_data",
                        condition_id=condition_id[:20])
            return None
        
        ancillary_data, _, chain_id = result
        if timestamp == 0:
            timestamp = result[1]  # Use timestamp from function if not set
        
        # UMA identifier for Polymarket binary markets
        # Format: keccak256("YES_OR_NO_QUERY") as bytes32
        identifier_bytes = w3.keccak(text=UMA_IDENTIFIER)
        # Ensure it's exactly 32 bytes
        identifier = identifier_bytes[:32] if len(identifier_bytes) >= 32 else identifier_bytes.ljust(32, b'\x00')
        
        # Debug: Print request params before calling
        # Decode ancillary_data to show JSON structure
        try:
            ancillary_json = ancillary_data.decode('utf-8')
            logger.debug("uma_request_params",
                        condition_id=condition_id[:20],
                        identifier=identifier.hex()[:20] + "...",
                        timestamp=timestamp,
                        ancillary_data_json=ancillary_json,
                        ancillary_data_len=len(ancillary_data),
                        market_title=market_title[:60] if market_title else None)
        except:
            logger.debug("uma_request_params",
                        condition_id=condition_id[:20],
                        identifier=identifier.hex()[:20] + "...",
                        timestamp=timestamp,
                        ancillary_data_len=len(ancillary_data),
                        ancillary_data_preview=ancillary_data[:100].hex() if len(ancillary_data) > 0 else "")
        
        # Check if price exists
        try:
            has_price = oo.functions.hasPrice(identifier, timestamp, ancillary_data).call()
            logger.debug("uma_has_price_result",
                        condition_id=condition_id[:20],
                        has_price=has_price)
        except Exception as e:
            logger.warning("uma_has_price_check_failed",
                        condition_id=condition_id[:20],
                        error=str(e),
                        error_type=type(e).__name__)
            import traceback
            logger.debug("uma_has_price_traceback",
                        traceback=traceback.format_exc())
            return None
        
        if not has_price:
            logger.debug("uma_no_price_yet",
                        condition_id=condition_id[:20])
            return {
                "resolved": False,
                "winning_outcome_index": None,
                "resolved_price": None,
                "resolution_time": None
            }
        
        # Get request data
        try:
            request = oo.functions.getRequest(identifier, timestamp, ancillary_data).call()
            logger.debug("uma_get_request_success",
                        condition_id=condition_id[:20])
        except Exception as e:
            logger.warning("uma_get_request_failed",
                          condition_id=condition_id[:20],
                          error=str(e),
                          error_type=type(e).__name__)
            import traceback
            logger.debug("uma_get_request_traceback",
                        traceback=traceback.format_exc())
            return None
        
        # Parse request tuple
        # Request structure: (proposer, proposerAddress, disputer, currency, settled, 
        #                     refundOnDispute, proposedPrice, resolvedPrice, expirationTime, 
        #                     reward, finalFee, bond, customLiveness)
        settled = request[4]  # settled field (bool)
        resolved_price_int = request[7]  # resolvedPrice field (int256)
        
        logger.debug("uma_request_data",
                    condition_id=condition_id[:20],
                    settled=settled,
                    resolved_price_int=resolved_price_int)
        
        if not settled:
            return {
                "resolved": False,
                "winning_outcome_index": None,
                "resolved_price": None,
                "resolution_time": None
            }
        
        # Convert resolvedPrice to outcome index
        # For binary markets: 1e18 = YES (index 0), 0 = NO (index 1)
        resolved_price = float(resolved_price_int) / 1e18
        
        # Determine winning outcome
        # If resolvedPrice == 1e18 (1.0), outcome 0 (YES) wins
        # If resolvedPrice == 0, outcome 1 (NO) wins
        if resolved_price >= 0.5:
            winning_outcome_index = 0  # YES
        else:
            winning_outcome_index = 1  # NO
        
        # Get expiration time (resolution time)
        expiration_time = request[8]  # expirationTime
        resolution_time = datetime.fromtimestamp(expiration_time).isoformat() if expiration_time > 0 else None
        
        return {
            "resolved": True,
            "winning_outcome_index": winning_outcome_index,
            "resolved_price": resolved_price,
            "resolution_time": resolution_time
        }
        
    except Exception as e:
        logger.warning("uma_resolution_check_failed",
                      condition_id=condition_id[:20],
                      error=str(e))
        return None

