# -*- coding: utf-8 -*-
import asyncio
import os
import sys
import json
import time
from datetime import datetime, timezone

# Add backend to path
sys.path.append(os.getcwd())

from services.database_service import database_service, Slot
from services.sovereign_service import sovereign_service
from sqlalchemy import text

# Config
BANKROLL = 100.0
LEVERAGE = 50.0

async def elite_nuclear_reset():
    print("INICIANDO RESET NUCLEAR ELITE V110.518...")
    
    try:
        # 1. POSTGRES (Source of Truth)
        print("\n--- [1/4] LIMPANDO POSTGRES (Railway) ---")
        await database_service.initialize()
        async with database_service.AsyncSessionLocal() as session:
            # A. Reset Banca e Vault
            print("Resetando Banca e Ciclos do Vault...")
            await session.execute(text("UPDATE banca_status SET saldo_total = :bal, risco_real_percent = 0.0, slots_disponiveis = 4, status = 'ONLINE' WHERE id = 1"), {"bal": BANKROLL})
            await session.execute(text("UPDATE vault_cycles SET sniper_wins = 0, cycle_number = 1, cycle_profit = 0.0, cycle_losses = 0.0, mega_cycle_wins = 0, mega_cycle_number = 1, accumulated_vault = 0.0, vault_total = 0.0, used_symbols_in_cycle = '[]', cycle_start_bankroll = :bal WHERE id = 1"), {"bal": BANKROLL})
            
            # B. Limpeza de Tabelas de Histórico
            print("Limpando historicos (Trade, Moonbags, Genesis, State)...")
            await session.execute(text("TRUNCATE TABLE trade_history RESTART IDENTITY CASCADE"))
            await session.execute(text("TRUNCATE TABLE moonbags RESTART IDENTITY CASCADE"))
            await session.execute(text("TRUNCATE TABLE order_genesis RESTART IDENTITY CASCADE"))
            await session.execute(text("TRUNCATE TABLE system_state RESTART IDENTITY CASCADE"))
            
            # C. Reset de Slots
            print("Limpando e recriando Slots taticos...")
            await session.execute(text("TRUNCATE TABLE slots RESTART IDENTITY"))
            for i in range(1, 5):
                session.add(Slot(id=i, status_risco="LIVRE", leverage=LEVERAGE))
            
            await session.commit()
            print("Postgres Purge Complete.")

        # 2. FIREBASE (Mirror Layer)
        print("\n--- [2/4] LIMPANDO FIREBASE (Firestore/RTDB) ---")
        await sovereign_service.initialize()
        
        # Reset Banca Firestore
        await sovereign_service.update_bankroll(BANKROLL)
        
        # Forçamos o reset dos slots no Firestore via sovereign_service
        for i in range(1, 5):
            await sovereign_service.update_slot(i, {
                "symbol": None, "side": None, "entry_price": 0, "current_stop": 0, 
                "status_risco": "LIVRE", "pnl_percent": 0, "vision_url": None
            })
        print("Firebase Mirror Resetted.")

        # 3. MEMORY & LOCAL FILES
        print("\n--- [3/4] LIMPANDO MEMORIA E ARQUIVOS LOCAIS ---")
        
        # Paper Storage
        if os.path.exists("paper_storage.json"):
            try:
                os.remove("paper_storage.json")
                print("paper_storage.json removido.")
            except: pass
            
        # Vision History
        if os.path.exists("vision_history.json"):
            try:
                with open("vision_history.json", "w") as f:
                    json.dump([], f)
                print("vision_history.json resetado.")
            except: pass
            
        # 4. OKX PAPER ENGINE
        from services.okx_rest import okx_rest_service
        if okx_rest_service:
            okx_rest_service.paper_positions = []
            okx_rest_service.paper_balance = BANKROLL
            print("Bybit Paper Engine resetado.")

        print("\nRESET NUCLEAR ELITE CONCLUIDO!")
        print("Sistema pronto para o Ciclo de Elite (Threshold 85%+).")

    except Exception as e:
        print(f"\nERRO DURANTE O RESET: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(elite_nuclear_reset())
