import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.getcwd())

from services.database_service import database_service
from services.sovereign_service import sovereign_service
from services.bankroll import bankroll_manager

async def force_sync():
    try:
        print("Starting Force Sync for Vision Intelligence...")
        await database_service.initialize()
        await sovereign_service.initialize()
        
        from services.okx_rest import okx_rest_service
        await okx_rest_service.initialize()
        
        print("Synchronizing slots...")
        # Aumentar timeout para Playwright
        await bankroll_manager.sync_slots_with_exchange()
        print("Sync complete. Check the Observatory/Vault.")
        
    except Exception as e:
        print(f"Error during force sync: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(force_sync())
