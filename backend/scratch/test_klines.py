import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.okx_rest import okx_rest_service
from config import settings

async def test():
    print("Testing get_klines for AVAXUSDT.P, interval 30...")
    symbol = "AVAXUSDT.P"
    interval = "30"
    limit = 10
    
    # Initialize settings if needed (usually done by import)
    # Mocking necessary parts if needed, but let's try direct call
    
    await okx_rest_service.initialize()
    klines = await okx_rest_service.get_klines(symbol, interval, limit=limit, kline_type="last")
    
    print(f"Result count: {len(klines)}")
    if klines:
        print(f"First kline: {klines[0]}")
    else:
        print("Empty result!")

if __name__ == "__main__":
    asyncio.run(test())
