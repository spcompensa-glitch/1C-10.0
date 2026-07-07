import asyncio
import httpx
import sys
import json
sys.path.append("backend")

from backend.services.okx_service import okx_service

async def main():
    try:
        request_path = "/api/v5/account/config"
        url = okx_service.base_url + request_path
        headers = okx_service._get_headers("GET", request_path)

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            print("ACCOUNT CONFIG:", json.dumps(response.json(), indent=2))

    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())
