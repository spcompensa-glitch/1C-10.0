import asyncio
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.append(os.path.abspath("c:/Users/spcom/Desktop/10D REAL 4.0/1CRYPTEN_SPACE_V4.0/backend"))

from services.database_service import database_service, Slot
from services.okx_rest import okx_rest_service
from services.sovereign_service import sovereign_service
from sqlalchemy import update, select

async def clear_orders():
    print("Iniciando limpeza das ordens (INJUSDT, ATOMUSDT)...")
    
    # Init DB
    await database_service.initialize()
    
    # 1. Limpar no DB
    async with database_service.AsyncSessionLocal() as session:
        result = await session.execute(select(Slot).where(Slot.symbol.in_(["INJUSDT.P", "INJUSDT", "ATOMUSDT.P", "ATOMUSDT"])))
        slots = result.scalars().all()
        
        for slot in slots:
            print(f"Limpando Slot {slot.id} ({slot.symbol})...")
            slot.symbol = None
            slot.side = None
            slot.qty = 0.0
            slot.entry_price = 0.0
            slot.entry_margin = 0.0
            slot.status_risco = "LIVRE"
            slot.genesis_id = None
            slot.order_id = None
            slot.pnl_percent = 0.0
            slot.current_stop = 0.0
            slot.target_price = 0.0
            slot.slot_type = None
            
        await session.commit()
        print("DB Slots resetados para LIVRE.")
    
    # 2. Limpar no PAPER do okx_rest
    await okx_rest_service._load_paper_state()
    
    positions_to_keep = []
    for pos in okx_rest_service.paper_positions:
        sym = pos.get("symbol", "").replace(".P", "").upper()
        if sym in ["INJUSDT", "ATOMUSDT"]:
            print(f"Removendo {sym} do okx_rest.paper_positions...")
        else:
            positions_to_keep.append(pos)
            
    okx_rest_service.paper_positions = positions_to_keep
    await okx_rest_service._save_paper_state()
    print("Paper state salvo.")
    
    # 3. Limpar no Sovereign / Firebase cache (força sync)
    await sovereign_service.initialize()
    print("Sync concluido.")

if __name__ == "__main__":
    asyncio.run(clear_orders())
