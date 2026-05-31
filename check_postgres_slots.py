# coding: utf-8
import asyncio
import os
import sys

sys.path.append(os.path.join(os.getcwd(), 'backend'))

from dotenv import load_dotenv
# Forçar override=True para ignorar a variável global inválida do Windows
load_dotenv('backend/.env', override=True)

from backend.services.database_service import database_service

async def main():
    try:
        # Forçar a inicialização com a URL do Postgres
        await database_service.initialize()
        slots = await database_service.get_active_slots()
        
        print("=== SLOTS NO POSTGRES DO RAILWAY ===")
        for s in slots:
            print(f"Slot {s['id']}: {s['symbol']} | {s['side']} | Entry: {s['entry_price']} | Qty: {s['qty']} | Status: {s['status_risco']} | Pensamento: {s['pensamento']}")
            
    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    asyncio.run(main())
