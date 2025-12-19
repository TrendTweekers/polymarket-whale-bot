"""Test WebSocket connection to see if it's receiving trades"""
import asyncio
import json
import websockets
from datetime import datetime

async def test_connection():
    """Test WebSocket connection and see if trades are coming through"""
    ws_url = "wss://ws-live-data.polymarket.com"
    
    print("="*80)
    print("🔍 TESTING WEBSOCKET CONNECTION")
    print("="*80)
    print()
    print(f"Connecting to: {ws_url}")
    print()
    
    try:
        async with websockets.connect(
            ws_url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=10
        ) as websocket:
            print("✅ WebSocket connected!")
            
            # Subscribe to trades
            subscribe_msg = {
                "action": "subscribe",
                "subscriptions": [
                    {
                        "topic": "activity",
                        "type": "trades"
                    }
                ]
            }
            
            await websocket.send(json.dumps(subscribe_msg))
            print("✅ Subscribed to trade activity!")
            print()
            print("Listening for trades (30 seconds)...")
            print("="*80)
            print()
            
            trade_count = 0
            start_time = datetime.now()
            
            try:
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        
                        # Check if it's a trade message
                        if data.get('topic') == 'activity' and data.get('type') == 'trades':
                            payload = data.get('payload', {})
                            if payload:
                                trade_count += 1
                                wallet = payload.get('proxyWallet', '')[:16]
                                market = payload.get('slug', 'Unknown')[:40]
                                size = float(payload.get('size', 0))
                                price = float(payload.get('price', 0))
                                value = size * price
                                
                                print(f"[{trade_count}] Trade detected:")
                                print(f"  Wallet: {wallet}...")
                                print(f"  Market: {market}")
                                print(f"  Value: ${value:,.2f}")
                                print()
                        
                        # Stop after 30 seconds
                        elapsed = (datetime.now() - start_time).total_seconds()
                        if elapsed >= 30:
                            break
                            
                    except json.JSONDecodeError:
                        # Not JSON, skip
                        pass
                    except Exception as e:
                        print(f"⚠️ Error processing message: {e}")
                        
            except asyncio.TimeoutError:
                print("⏰ Timeout waiting for messages")
            except Exception as e:
                print(f"❌ Error receiving messages: {e}")
            
            elapsed = (datetime.now() - start_time).total_seconds()
            print("="*80)
            print(f"RESULTS:")
            print(f"  Trades received: {trade_count}")
            print(f"  Time elapsed: {elapsed:.1f} seconds")
            print(f"  Rate: {trade_count / elapsed * 60:.1f} trades/minute")
            print()
            
            if trade_count == 0:
                print("⚠️ WARNING: No trades received!")
                print("   Possible issues:")
                print("   • WebSocket connected but not receiving data")
                print("   • Markets are quiet")
                print("   • Subscription not working")
            else:
                print("✅ WebSocket is working! Trades are flowing.")
                
    except websockets.exceptions.ConnectionClosed as e:
        print(f"❌ Connection closed: {e}")
    except websockets.exceptions.WebSocketException as e:
        print(f"❌ WebSocket error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_connection())
