import asyncio
import logging
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "1CRYPTEN_SPACE_V4.0", "backend"))

from services.okx_rest import okx_rest_service
from config import settings

async def diag():
    print("Testing AVAXUSDT.P klines...")
    # Test with .P
    res_p = await okx_rest_service.get_klines("AVAXUSDT.P", "30", limit=10)
    print(f"AVAXUSDT.P result length: {len(res_p)}")
    
    # Test with AVAXUSDT
    res = await okx_rest_service.get_klines("AVAXUSDT", "30", limit=10)
    print(f"AVAXUSDT result length: {len(res)}")
    
    if not res:
        print("Fallback test with raw HTTP...")
        import urllib.request
        import json
        url = "https://www.okx.com/api/v5/market/candles?instId=AVAX-USDT-SWAP&bar=30m&limit=10"
        try:
            with urllib.request.urlopen(url) as response:
                data = json.loads(response.read().decode())
                print(f"Raw API RetCode: {data.get('retCode')}")
                print(f"Raw API List Length: {len(data.get('result', {}).get('list', []))}")
        except Exception as e:
            print(f"Raw API Error: {e}")

if __name__ == "__main__":
    asyncio.run(diag())
