import asyncio
import sys
import os

backend_dir = r"c:\Users\spcom\Desktop\10D REAL 5.0\1CRYPTEN_SPACE_V4.0\backend"
sys.path.append(backend_dir)

async def main():
    try:
        from services.database_service import database_service
        from services.sovereign_service import sovereign_service
        from services.okx_rest import okx_rest_service
        
        print("--- INICIANDO LIMPEZA DE BTCUSDT ---")
        
        # 1. Limpar no Paper Engine (Memória)
        initial_pos_count = len(okx_rest_service.paper_positions)
        okx_rest_service.paper_positions = [p for p in okx_rest_service.paper_positions if p.get("symbol") != "BTCUSDT"]
        final_pos_count = len(okx_rest_service.paper_positions)
        if initial_pos_count > final_pos_count:
            print(f"✅ Removida posição de BTCUSDT da memória Paper.")
        
        # 2. Limpar no Postgres (Slots)
        slots = await database_service.get_active_slots()
        for s in slots:
            if s.symbol == "BTCUSDT":
                print(f"✅ Limpando Slot {s.id} (BTCUSDT) no Postgres.")
                await database_service.update_slot(s.id, symbol=None, side=None, qty=0, status_risco="LIVRE")
        
        # 3. Limpar Moonbags
        # (Não removemos do histórico, apenas do estado ativo)
        
        # 4. Sincronizar com Firestore/RTDB
        await okx_rest_service._save_paper_state()
        print("✅ Estado Paper sincronizado com Firestore.")
        
        # 5. Forçar reset de BTC no RTDB (Sovereign)
        # O BankrollManager deve cuidar disso no próximo ciclo, mas vamos forçar se puder.
        
        print("--- LIMPEZA CONCLUÍDA ---")

    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    asyncio.run(main())
