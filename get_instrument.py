import asyncio
import httpx

async def main():
    try:
        url = "https://www.okx.com/api/v5/public/instruments?instType=SWAP&instId=BTC-USDT-SWAP"
        async with httpx.AsyncClient() as client:
            res = await client.get(url)
            data = res.json()["data"][0]
            print(f"BTC-USDT-SWAP:")
            print(f"ctVal (Contract Value): {data['ctVal']} BTC")
            print(f"minSz (Min Size): {data['minSz']} contract(s)")
            print(f"lotSz (Lot Size): {data['lotSz']} contract(s)")
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    asyncio.run(main())
