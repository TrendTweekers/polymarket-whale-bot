import asyncio
import aiohttp
import json

async def test():
    async with aiohttp.ClientSession() as session:
        url = "https://gamma-api.polymarket.com/markets?closed=false&limit=2"
        async with session.get(url) as response:
            data = await response.json()
            if isinstance(data, list) and len(data) > 0:
                print("Market structure:")
                print(json.dumps(data[0], indent=2)[:2000])
            else:
                print("Response:", type(data))
                print(json.dumps(data, indent=2)[:2000])

asyncio.run(test())
