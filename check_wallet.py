import asyncio
import sys
sys.path.append("backend")

from backend.services.okx_service import okx_service

async def main():
    try:
        balance = await okx_service.get_wallet_balance()
        print(f"WALLET BALANCE: {balance}")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())
