import asyncio
import sys
sys.path.append("backend")

from backend.services.okx_service import okx_service

async def main():
    try:
        res = await okx_service.place_atomic_order(
            symbol="BTCUSDT.P",
            side="Buy",
            qty=1.0,
            sl_price=50000.0,
            leverage=50.0
        )
        print("ORDER RESULT:", res)
    except Exception as e:
        print("ERROR:", e)

if __name__ == "__main__":
    asyncio.run(main())
