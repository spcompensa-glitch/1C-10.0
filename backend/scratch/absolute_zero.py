import asyncio
import os
import sys

# Add backend to path
backend_dir = r"c:\Users\spcom\Desktop\10D REAL 4.0\1CRYPTEN_SPACE_V4.0\backend"
sys.path.append(backend_dir)

from services.database_service import database_service
from services.sovereign_service import sovereign_service
from services.okx_rest import okx_rest_service

async def absolute_zero_reset():
    print("Starting ABSOLUTE ZERO RESET...")
    
    # Initialize services
    await database_service.initialize()
    await sovereign_service.initialize()
    await okx_rest_service.initialize()
    
    # 1. Close ALL positions (Real or Paper)
    print("Closing all active positions...")
    positions = await okx_rest_service.get_active_positions()
    for pos in positions:
        symbol = pos.get("symbol")
        side = pos.get("side")
        size = float(pos.get("size", 0))
        if size > 0:
            print(f"Closing {symbol} {side} Qty:{size}...")
            await okx_rest_service.close_position(symbol, side, size, reason="ABSOLUTE_ZERO_RESET")
    
    # 2. Cancel all open orders
    print("Canceling all pending orders...")
    try:
        if okx_rest_service.execution_mode == "REAL":
            await okx_rest_service.session.cancel_all_orders(category="linear", settleCoin="USDT")
        else:
            okx_rest_service.paper_orders_history = []
            await okx_rest_service._save_paper_state()
    except Exception as e:
        print(f"Cancel orders warning: {e}")

    # 3. Nuclear DB Wipe
    print("Wiping Postgres Data (Slots, History, Vault, Banca)...")
    await database_service.reset_system_data()
    
    # 4. Final Verification and Force Nulls
    async with database_service.AsyncSessionLocal() as session:
        from sqlalchemy import update
        from services.database_service import Slot, BancaStatus, TradeHistory
        
        # Ensure slots are completely empty
        await session.execute(update(Slot).values(
            symbol=None, side=None, qty=0.0, entry_price=0.0,
            entry_margin=0.0, status_risco="LIVRE", genesis_id=None,
            order_id=None, pnl_percent=0.0, current_stop=0.0, target_price=0.0
        ))
        
        # Ensure Banca is exactly 100.0
        await session.execute(update(BancaStatus).where(BancaStatus.id == 1).values(
            saldo_total=100.0, risco_real_percent=0.0, slots_disponiveis=4, status="ESTADO_ZERO"
        ))
        
        await session.commit()
    
    print("ESTADO ZERO CONCLUIDO: Banca 100.00 | Slots 0/4 | Historico Vazio.")

if __name__ == "__main__":
    asyncio.run(absolute_zero_reset())
