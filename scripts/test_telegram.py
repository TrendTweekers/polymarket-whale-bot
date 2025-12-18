"""Test Telegram notification"""
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')

if not telegram_bot_token or not telegram_chat_id:
    print("❌ Telegram credentials not found in .env file")
    print("   Please add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env")
    exit(1)

print("="*80)
print("📱 TESTING TELEGRAM NOTIFICATION")
print("="*80)
print()
print(f"Bot Token: {telegram_bot_token[:10]}...")
print(f"Chat ID: {telegram_chat_id}")
print()

async def send_test():
    url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": telegram_chat_id,
        "text": (
            "🧪 <b>TEST NOTIFICATION</b>\n\n"
            "✅ Telegram notifications are working!\n\n"
            "This is a test message from your Polymarket whale watcher.\n\n"
            "<i>If you received this, Telegram integration is functioning correctly.</i>"
        ),
        "parse_mode": "HTML"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10.0)
            
            if response.status_code == 200:
                print("✅ Test notification sent successfully!")
                print("   Check your Telegram for the message.")
                return True
            else:
                print(f"❌ Failed to send notification")
                print(f"   Status code: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
    except Exception as e:
        print(f"❌ Error sending notification: {e}")
        return False

import asyncio
success = asyncio.run(send_test())

print()
print("="*80)
if success:
    print("✅ Telegram is working! You should receive notifications for:")
    print("   • Monitored whale trades")
    print("   • Large trades >$1000")
    print("   • Whale milestones (100, 250, 500, 750, 1000, etc.)")
else:
    print("❌ Telegram test failed. Please check:")
    print("   1. Bot token is correct")
    print("   2. Chat ID is correct")
    print("   3. Bot has permission to send messages")
    print("   4. Internet connection is working")
print("="*80)
