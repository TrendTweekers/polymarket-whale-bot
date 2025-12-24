# UMA On-Chain Resolver Implementation

## Summary

Implemented on-chain UMA OptimisticOracleV2 resolver for Polymarket markets. The resolver queries the blockchain directly instead of relying on Polymarket's API.

## Files Created/Modified

1. **`src/polymarket/uma_resolver.py`** - New module for UMA on-chain resolution
2. **`src/polymarket/resolver.py`** - Updated to try UMA first, then fall back to API
3. **`scripts/resolve_paper_trades.py`** - Updated to use UMA resolver
4. **`requirements.txt`** - Added `web3>=6.0.0`

## Implementation Details

### UMA Contract Addresses
- **OptimisticOracleV2**: `0xA0Ae660944944e720534d9D5135E5e22D7b5e8C7` (Ethereum mainnet)
- **CTF (ConditionalTokenFramework)**: `0x4D97DCd97eC945f40CF65B8703ACB7d0dc4a97C4` (Ethereum mainnet)

### Resolution Flow

1. **Get AncillaryData**: 
   - Try to get `questionId` from Polymarket API
   - Fallback: Query CTF contract for `questionId`
   - Fallback: Use `condition_id` directly as ancillaryData

2. **Query UMA OptimisticOracleV2**:
   - Identifier: `keccak256("YES_OR_NO_QUERY")`
   - Timestamp: `0` (latest resolution)
   - AncillaryData: `questionId` address (32 bytes, padded)

3. **Parse Resolution**:
   - Check `hasPrice()` - if false, market not resolved
   - Call `getRequest()` - get request data
   - Check `settled` field - if false, market not resolved
   - Read `resolvedPrice`:
     - `1e18` (1.0) = YES wins (outcome index 0)
     - `0` = NO wins (outcome index 1)

## Current Status

✅ **Code implemented and integrated**  
⚠️ **RPC/Contract calls failing** - Needs verification:
- RPC endpoint may be incorrect or rate-limited
- Contract addresses may need verification
- Identifier format may need adjustment

## Configuration

Set RPC endpoint via environment variable:
```bash
export ETH_RPC_URL="https://eth.llamarpc.com"  # Default public RPC
# Or use Infura/Alchemy:
export ETH_RPC_URL="https://mainnet.infura.io/v3/YOUR_PROJECT_ID"
```

## Testing

Run test script:
```bash
python scripts/test_uma_resolver.py
```

Run manual resolution script:
```bash
python scripts/resolve_paper_trades.py --condition-id 0x0e4ccd69c581deb1aad6f587083a4800d458d6a12f3d202418a53e0c40b18c5a --verbose
```

## Next Steps

1. **Verify RPC endpoint** - Test with different providers (Infura, Alchemy, public RPCs)
2. **Verify contract addresses** - Confirm UMA OO V2 and CTF addresses are correct
3. **Verify identifier** - Confirm "YES_OR_NO_QUERY" is correct for Polymarket
4. **Test with resolved market** - Try with a known resolved market to verify flow

## Fallback Behavior

If UMA resolution fails, the resolver automatically falls back to the API method, so the bot continues to function even if UMA is unavailable.

