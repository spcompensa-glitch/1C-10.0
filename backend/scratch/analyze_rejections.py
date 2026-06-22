import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from services.database_service import database_service
from services.firebase_service import firebase_service

async def main():
    print("=== ANÁLISE DE REJEIÇÕES DO CAPTAIN ===")
    
    # 1. Carregar logs de eventos recentes do sentinela/captain
    try:
        # Puxar do Firestore ou Postgres os resultados dos sinais
        if firebase_service.is_active:
            print("Consultando sinal outcomes do Firestore...")
            docs = firebase_service.db.collection("signals_outcome").order_by("timestamp", direction="DESCENDING").limit(20).stream()
            count = 0
            for doc in docs:
                count += 1
                data = doc.to_dict()
                print(f"[{data.get('timestamp', 'N/A')}] Símbolo: {data.get('symbol')} | Estratégia: {data.get('strategy_class')} | Status: {data.get('outcome')} | Motivo: {data.get('reason', 'N/A')}")
            
            if count == 0:
                print("Nenhum resultado de sinal encontrado na tabela signals_outcome do Firestore.")
        else:
            print("Firebase inativo, pulando consulta.")
    except Exception as e:
        print(f"Erro ao consultar rejeições: {e}")

if __name__ == "__main__":
    asyncio.run(main())
