import asyncio
import httpx
import sys
sys.path.append("backend")

from backend.services.okx_service import okx_service

async def main():
    try:
        request_path = "/api/v5/asset/balances"
        url = okx_service.base_url + request_path
        headers = okx_service._get_headers("GET", request_path)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            print("FUNDING ACCOUNT RES:", response.json())

    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())
