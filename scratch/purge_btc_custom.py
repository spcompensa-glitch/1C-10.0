import asyncio
import sys
import os
from dotenv import load_dotenv

# Carrega o .env do backend com override
load_dotenv(r"c:\Users\spcom\Desktop\1C-7.0\backend\.env", override=True)

# Ajusta sys.path para apontar para a pasta backend correta no workspace atual
sys.path.append(r"c:\Users\spcom\Desktop\1C-7.0\backend")

async def main():
    try:
        from services.database_service import database_service
        from services.firebase_service import firebase_service
        from services.okx_rest import okx_rest_service as bybit_rest_service
        
        print("--- INICIANDO PURGA CUSTOMIZADA DE BTCUSDT ---")
        
        # 1. Purgar posicoes de BTCUSDT da memoria Paper
        pos_antes = len(bybit_rest_service.paper_positions)
        bybit_rest_service.paper_positions = [p for p in bybit_rest_service.paper_positions if (p.get("symbol") or "").upper().replace(".P","") != "BTCUSDT"]
        pos_depois = len(bybit_rest_service.paper_positions)
        print(f"Paper positions: {pos_antes} -> {pos_depois} (residuos de BTC removidos)")
        
        # 2. Purgar moonbags de BTCUSDT da memoria Paper
        moon_antes = len(bybit_rest_service.paper_moonbags)
        bybit_rest_service.paper_moonbags = [p for p in bybit_rest_service.paper_moonbags if (p.get("symbol") or "").upper().replace(".P","") != "BTCUSDT"]
        moon_depois = len(bybit_rest_service.paper_moonbags)
        print(f"Paper moonbags: {moon_antes} -> {moon_depois} (residuos de BTC removidos)")
        
        # 3. Forcar persistencia do estado Paper limpo no Firestore
        await bybit_rest_service._save_paper_state()
        print("Estado Paper limpo sincronizado com o Firestore com sucesso.")
        
        # 4. Limpar slots do Postgres
        await database_service.initialize()
        slots = await database_service.get_active_slots()
        for s in slots:
            slot_id = s.get("id")
            symbol = s.get("symbol")
            if symbol and symbol.upper().replace(".P","") == "BTCUSDT":
                print(f"Limpando slot zumbi {slot_id} ({symbol}) no Postgres...")
                reset_data = {
                    "symbol": None,
                    "side": None,
                    "qty": 0,
                    "entry_margin": 0,
                    "opened_at": None,
                    "entry_price": 0,
                    "initial_stop": 0,
                    "current_stop": 0,
                    "target_price": 0,
                    "status_risco": "LIVRE",
                    "pnl_percent": 0,
                    "slot_type": None,
                    "pattern": None,
                    "pensamento": "Limpeza de BTCUSDT",
                    "rescue_activated": False,
                    "rescue_resolved": False,
                }
                await database_service.update_slot(slot_id, reset_data)
                
        # 5. Sincronizar slots livres com o Firebase RTDB
        print("Sincronizando slots livres com o Firebase...")
        for i in range(1, 5):
            slot_db = await database_service.get_slot(i)
            if slot_db and not slot_db.get("symbol"):
                await firebase_service.update_slot(i, {
                    "symbol": None,
                    "side": None,
                    "qty": 0,
                    "entry_price": 0,
                    "current_stop": 0,
                    "status_risco": "LIVRE",
                    "pnl_percent": 0
                })
        
        print("--- PURGA CONCLUIDA COM SUCESSO ---")
        
    except Exception as e:
        print(f"Erro durante a purga: {e}")

if __name__ == "__main__":
    asyncio.run(main())
