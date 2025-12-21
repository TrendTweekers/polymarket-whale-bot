# 📊 How Trade Filtering Works

## **What `fetch_recent_trades()` Returns:**

**500 trades = ALL recent trades from Polymarket** (not filtered by whales)

- ✅ Fetches ALL trades ≥ $150 from Polymarket API
- ✅ Includes trades from ANY wallet (not just target whales)
- ✅ Includes trades from ANY market
- ✅ This is GOOD - we see everything!

---

## **How Target Whale Filtering Works:**

### **Step 1: Fetch ALL Trades**
```python
recent_trades = await fetch_recent_trades(session, min_size_usd=API_MIN_SIZE_USD, limit=500)
# Returns: 500 trades from ALL wallets
```

### **Step 2: Process Each Trade**
```python
for trade in recent_trades:
    signal = await process_trade(session, trade, ...)
    # process_trade() checks if wallet is a target whale
```

### **Step 3: Target Whale Detection (Inside `process_trade()`)**
```python
# In process_trade():
target_whales = [
    "0x507e52ef684ca2dd91f90a9d26d149dd3288beae",
    "0x9a6e69c9b012030c668397d8346b4d55dd8335b4",
    "0xfc25f141ed27bb1787338d2c4e7f51e3a15e1f7f"
]

if trade_wallet_lower in target_whales:
    logger.info("target_whale_trade_detected", ...)
    # This trade is from a target whale!
```

### **Step 4: Paper Trade Creation**
- Only trades from target whales that pass all filters create paper trades
- Other trades are processed but don't create paper trades

---

## **What You'll See in Logs:**

### **All Trades:**
```
fetched_recent_trades count=500  # ALL trades from Polymarket
```

### **Target Whale Trades:**
```
target_whale_trade_detected wallet=0x507e52...  # Only target whale trades
```

### **Paper Trades:**
```
paper_trade_opened trade_id=...  # Only when target whale trades pass all filters
```

---

## **Why This Approach is Better:**

✅ **See ALL trades** - Don't miss any target whale activity  
✅ **Real-time detection** - Catch trades as soon as they happen  
✅ **No market filtering** - Target whales can trade in any market  
✅ **Same as Phase 2** - Uses same approach that worked before  

---

## **Summary:**

- **500 trades** = All recent Polymarket trades (not just whales)
- **Target whale detection** = Happens inside `process_trade()`
- **Paper trades** = Only created for target whale trades that pass filters

**The bot scans ALL trades, but only creates paper trades for your 3 target whales!** 🎯
