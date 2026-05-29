import asyncio
import sys
sys.path.append('c:\\Users\\spcom\\Desktop\\1C-7.0\\backend')
from services.firebase_service import firebase_service
async def main():
    await firebase_service.initialize()
    print(await firebase_service.get_active_slots(force_refresh=True))
asyncio.run(main())
