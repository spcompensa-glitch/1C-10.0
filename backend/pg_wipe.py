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

    # Forçar a inicialização manual e ativação do Firebase para o reset
    print("Inicializando credenciais do Firebase de Produção...")
    try:
        import firebase_admin
        from firebase_admin import credentials, db, firestore
        # Carrega credenciais do settings (.env) se disponíveis
        cred_path = getattr(settings, "FIREBASE_CREDENTIALS_PATH", None) or os.getenv("FIREBASE_CREDENTIALS_PATH")
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred, {
                    'databaseURL': settings.FIREBASE_DATABASE_URL
                })
            firebase_service.db = firestore.client()
            firebase_service.rtdb = db.reference()
            firebase_service.is_active = True
            print("🔥 Firebase SDK ativado com sucesso para reset de produção!")
    except Exception as fe:
        print(f"Aviso ao inicializar SDK Firebase (pode usar fallbacks): {fe}")

    # Reset do Firestore (Amnesia-Guard & paper_engine)
    if firebase_service.is_active:
        print("Limpando estado do paper_engine no Firestore...")
        try:
            clean_state = {
                "positions": [],
                "moonbags": [],
                "balance": 100.0,
                "history": []
            }
            await firebase_service.update_paper_state(clean_state)
            print("✅ Firestore 'paper_engine' zerado!")
        except Exception as e:
            print(f"Erro ao zerar paper_engine no Firestore: {e}")

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
