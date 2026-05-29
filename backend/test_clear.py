import asyncio
import sys
sys.path.append('c:\\Users\\spcom\\Desktop\\1C-7.0\\backend')
from services.firebase_service import firebase_service
async def main():
    await firebase_service.initialize()
    await firebase_service.update_paper_state({'positions': [], 'moonbags': [], 'balance': 100.0, 'history': []})
    print('Paper state cleared.')
asyncio.run(main())
