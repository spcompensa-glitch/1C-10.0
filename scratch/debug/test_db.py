import asyncio
from backend.services.database_service import database_service
from backend.services.okx_rest import okx_rest_service
async def main():
    print('Exec mode:', okx_rest_service.execution_mode)
    slots = await database_service.get_active_slots()
    print('Postgres slots:', slots)
    print('Paper pos:', okx_rest_service.paper_positions)
asyncio.run(main())
