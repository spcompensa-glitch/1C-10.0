import asyncio
import sys
import os

backend_dir = r"c:\Users\spcom\Desktop\10D REAL 5.0\1CRYPTEN_SPACE_V4.0\backend"
sys.path.append(backend_dir)

async def main():
    try:
        from services.database_service import database_service
        from services.sovereign_service import sovereign_service
        
        # Conecta se necessário
        # Nota: database_service geralmente inicializa no import se tiver env vars
        
        print("--- Slots no Postgres ---")
        slots = await database_service.get_active_slots()
        for s in slots:
            symbol = s.symbol if s.symbol else "LIVRE"
            print(f"Slot {s.id}: {symbol} | Status: {s.status_risco} | PnL: {s.pnl_percent}%")
            
        print("\n--- Moonbags no Postgres ---")
        moons = await database_service.get_moonbags()
        for m in moons:
            print(f"Moonbag: {m.symbol} | ROI: {m.pnl_percent}%")
            
        print("\n--- Paper Positions (Memory) ---")
        from services.okx_rest import okx_rest_service
        for p in okx_rest_service.paper_positions:
            print(f"Paper: {p.get('symbol')} | Entry: {p.get('entry_price')}")

    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    asyncio.run(main())
