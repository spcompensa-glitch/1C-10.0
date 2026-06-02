# coding: utf-8
import asyncio
import sys, os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.services.database_service import database_service

async def main():
    slots = await database_service.get_active_slots()
    print(slots)

if __name__ == "__main__":
    asyncio.run(main())
