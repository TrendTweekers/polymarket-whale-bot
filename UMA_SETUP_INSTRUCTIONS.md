# UMA On-Chain Resolver Setup Instructions

## ✅ Implementation Complete

The UMA on-chain resolver has been implemented with:
- OptimisticOracleV3 support (Polygon)
- Proper ancillaryData formatting (b'q:"market_title"')
- Market metadata extraction from API
- Fallback to API method if UMA fails

## 🔧 Required Setup Steps

### 1. Set Up Reliable RPC Endpoint (CRITICAL)

Public RPCs are throttled. You need a reliable provider:

#### Option A: Alchemy (Recommended)
1. Go to https://alchemy.com
2. Sign up and create a new app
3. Select "Polygon" network
4. Copy your API URL: `https://polygon-mainnet.g.alchemy.com/v2/YOUR_API_KEY`

#### Option B: Infura
1. Go to https://infura.io
2. Sign up and create a new project
3. Select "Polygon Mainnet"
4. Copy your project URL: `https://polygon-mainnet.infura.io/v3/YOUR_PROJECT_ID`

### 2. Update .env File

Add to your `.env` file:
```bash
# Polygon RPC (Polymarket uses Polygon)
POLYGON_RPC_URL=https://polygon-mainnet.g.alchemy.com/v2/YOUR_API_KEY

# Or use Infura:
# POLYGON_RPC_URL=https://polygon-mainnet.infura.io/v3/YOUR_PROJECT_ID
```

### 3. Test RPC Connection

Run this to verify your RPC works:
```python
from web3 import Web3
w3 = Web3(Web3.HTTPProvider('YOUR_RPC_URL'))
print('Connected:', w3.is_connected())
print('Chain ID:', w3.eth.chain_id)  # Should be 137 for Polygon
```

### 4. Test UMA Resolver

```bash
python scripts/test_uma_resolver.py
```

### 5. Run Manual Resolution

After RPC is configured:
```bash
python scripts/resolve_paper_trades.py --auto-update
```

## 📋 Contract Addresses (Polygon - Chain ID 137)

- **OptimisticOracleV3**: `0x5953f2538F613E05bAED8A5AeFa8e6622467AD3D`
- **CTF (ConditionalTokenFramework)**: `0x4D97DCd97eC945f40CF65B8703ACB7d0dc4a97C4`
- **Polymarket Requester**: `0x2F5e3684cb1F318ec51b00Edba38d79Ac2c0aA9d`

## 🔍 How It Works

1. **Fetch Market Metadata**: Gets market title, end date from Polymarket API
2. **Build AncillaryData**: Formats as `b'q:"market_title"'` + requester params
3. **Query UMA**: Calls `hasPrice()` and `getRequest()` on OptimisticOracleV3
4. **Parse Resolution**: Extracts `resolvedPrice` (1e18 = YES/0, 0 = NO/1)
5. **Update Database**: Marks trade as resolved with PnL

## 🐛 Troubleshooting

### "Could not transact with/call contract function"
- **Cause**: RPC endpoint issue or wrong contract address
- **Fix**: Verify RPC URL and test connection

### "Too many values to unpack"
- **Cause**: Code version mismatch
- **Fix**: Ensure all files are updated (run `git pull` or re-apply changes)

### "No price yet"
- **Cause**: Market not resolved on-chain yet
- **Fix**: Normal - market may still be in challenge period

## 📊 Expected Output

When working correctly, you should see:
```
🔗 Checking UMA on-chain resolution...
   Market Title: Raiders vs. Texans...
   End Date: 2025-12-21T23:59:59Z
✅ UMA RESOLUTION FOUND!
   Winning Outcome Index: 1
   Resolved Price: 0.0
```

## ⚠️ Important Notes

- UMA resolution may lag behind event end time (challenge period)
- Falls back to API method if UMA unavailable
- Requires reliable RPC for consistent operation
- Free tier RPCs may have rate limits

