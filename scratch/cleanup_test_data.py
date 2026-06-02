import sys
import os
import asyncio

# Adicionar o diretório backend ao PATH do sistema
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from services.firebase_service import firebase_service
from services.database_service import database_service
from services.okx_rest import okx_rest_service

async def cleanup():
    print("🧹 [CLEANUP] Iniciando limpeza atômica de resíduos de teste...")
    
    # 0. Garante BybitREST pronto
    okx_rest_service.is_ready = True
    okx_rest_service.execution_mode = "PAPER"
    
    # 1. Limpar as Moonbags de teste (BTC e PEPE) no Postgres
    print("\n🌔 Removendo Moonbags de teste do Postgres...")
    moons = await database_service.get_moonbags()
    for m in moons:
        sym = m.get("symbol", "").upper()
        if sym in ["BTCUSDT", "PEPEUSDT", "BTC", "PEPE"]:
            print(f"❌ Deletando Moonbag {sym} do Postgres...")
            async with database_service.AsyncSessionLocal() as session:
                from services.database_service import Moonbag
                from sqlalchemy import delete
                await session.execute(delete(Moonbag).where(Moonbag.symbol == m.get("symbol")))
                await session.commit()
                
            # Tenta remover do Firebase também se o UUID existir
            uuid_val = m.get("uuid")
            if uuid_val:
                try:
                    await firebase_service.remove_moonbag(uuid_val, reason="PURGE_TEST_DATA")
                    print(f"🔥 Removida do Firebase Moonbag: {uuid_val}")
                except Exception as fe:
                    print(f"⚠️ Nota: Não foi possível deletar do Firebase (Firebase inativo ou sem chave): {fe}")

    # 2. Limpar o Slot 4 (BASEDUSDT com erro residual de ROI)
    print("\n🧹 Limpando o Slot 4 (BASEDUSDT) no Postgres e Firebase...")
    await firebase_service.free_slot(4, reason="PURGE_TEST_BASEDUSDT_ERROR")
    
    # Garante que removemos posições falsas da memória RAM local também
    okx_rest_service.paper_positions = [p for p in okx_rest_service.paper_positions if p.get("symbol", "").upper() not in ["BTCUSDT", "PEPEUSDT", "SOLUSDT", "BASEDUSDT", "BASEUSDT"]]
    
    # Salva o estado limpo
    if hasattr(okx_rest_service, "_save_paper_state"):
        await okx_rest_service._save_paper_state()
        
    print("\n✨ [CLEANUP] Limpeza concluída com sucesso absoluto!")

if __name__ == "__main__":
    asyncio.run(cleanup())
