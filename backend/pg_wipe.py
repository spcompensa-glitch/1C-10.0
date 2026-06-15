import asyncio
import sys
import os
import logging
from sqlalchemy import text

os.environ["DATABASE_URL"] = "postgresql://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', '..', '..', 'Desktop', '1C-7.0', 'backend'))
sys.path.append('./backend')

from config import settings
from services.database_service import database_service
from services.firebase_service import firebase_service

async def main():
    print("Conectando ao PostgreSQL de Producao (Railway)...")
    
    # Executar comandos DDL no banco para truncar as tabelas
    async with database_service.engine.begin() as conn:
        print("Limpando a tabela 'slots'...")
        await conn.execute(text("DELETE FROM slots;"))
        print("Limpando a tabela 'moonbags' (se existir)...")
        try:
            await conn.execute(text("DELETE FROM moonbags;"))
        except Exception:
            pass
    
    print("PostgreSQL slots apagados com sucesso!")

    print("Conectando ao Firebase RTDB...")
    if firebase_service.rtdb:
        try:
            firebase_service.rtdb.child("active_slots").delete()
            print("Firebase 'active_slots' limpos.")
        except Exception as e:
            print(f"Erro ao deletar active_slots do Firebase: {e}")
            
        try:
            firebase_service.rtdb.child("vault_history").delete()
            print("Firebase 'vault_history' limpos.")
        except Exception as e:
            print(f"Erro ao deletar vault_history do Firebase: {e}")
            
        try:
            firebase_service.rtdb.child("banca").update({
                "configured_balance": 100.0,
                "pnl_realized": 0.0
            })
            print("Firebase 'banca' resetada para $100.00.")
        except Exception as e:
            print(f"Erro ao resetar banca no Firebase: {e}")

    print("=== NUCLEAR RESET CONCLUIDO NAS BASES DE DADOS ===")

if __name__ == '__main__':
    asyncio.run(main())
