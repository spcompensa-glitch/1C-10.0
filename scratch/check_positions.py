
import asyncio
import os
import sys

# Adiciona o caminho do projeto ao sys.path
sys.path.append(os.path.join(os.getcwd(), "1CRYPTEN_SPACE_V4.0", "backend"))

from services.okx_rest import okx_rest_service
from services.sovereign_service import sovereign_service
from config import settings

async def check_positions():
    print(f"Modo: {settings.OKX_EXECUTION_MODE}")
    if settings.OKX_EXECUTION_MODE == "PAPER":
        # Simulate loading paper positions
        await okx_rest_service.get_wallet_balance() # Usually triggers loading
        print(f"Paper Positions: {okx_rest_service.paper_positions}")
    else:
        # Real positions
        positions = await okx_rest_service.get_positions()
        print(f"Real Positions: {positions}")
        
    slots = await sovereign_service.get_active_slots()
    print(f"Slots in DB: {[s.get('symbol') for s in slots if s.get('symbol')]}")

if __name__ == "__main__":
    asyncio.run(check_positions())
