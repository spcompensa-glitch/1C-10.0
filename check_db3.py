# coding: utf-8
import asyncio
import sys, os
import json

sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.services.database_service import database_service

async def main():
    try:
        await database_service.initialize()
        slots = await database_service.get_active_slots()
        
        # Filtrar campos e remover emojis problemáticos para exibição em ASCII
        clean_slots = []
        for s in slots:
            clean_s = {}
            for k, v in s.items():
                if isinstance(v, str):
                    # remove emojis ou caracteres estranhos para não quebrar o terminal
                    clean_s[k] = v.encode('ascii', 'ignore').decode('ascii')
                else:
                    clean_s[k] = v
            clean_slots.append(clean_s)
            
        print("=== SLOTS ATIVOS NO BANCO LOCAL ===")
        for s in clean_slots:
            print(f"Slot {s['id']}: {s['symbol']} | {s['side']} | Entry: {s['entry_price']} | Qty: {s['qty']} | Status: {s['status_risco']}")
            
    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    asyncio.run(main())
