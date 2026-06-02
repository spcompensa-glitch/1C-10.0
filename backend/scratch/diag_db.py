
import asyncio
import os
import sys
from datetime import datetime

# Adiciona o diretório atual ao sys.path para importar os serviços
sys.path.append(os.getcwd())

async def run_diag():
    print("--- 1CRYPTEN DIAGNOSTIC TOOL ---")
    
    # 1. Check .env
    if os.path.exists(".env"):
        print("OK: .env file found.")
    else:
        print("ERROR: .env file NOT found!")
        return

    # 2. Load settings
    from config import settings
    print(f"DATABASE_URL: {os.getenv('DATABASE_URL')[:20]}...")
    print(f"OKX_EXECUTION_MODE: {settings.OKX_EXECUTION_MODE}")
    
    # 3. Initialize Database
    from services.database_service import database_service
    print("Connecting to database...")
    try:
        await asyncio.wait_for(database_service.initialize(), timeout=10.0)
        print("OK: Database connection successful.")
    except Exception as e:
        print(f"ERROR: Database connection FAILED: {e}")

        # Se falhou, vamos tentar ver se o SQLite local tem algo
        print("Falling back to check local SQLite if exists...")
        if os.path.exists("local_sniper.db"):
            print("Found local_sniper.db")
        else:
            print("local_sniper.db not found.")
        return

    # 4. Check Slots
    slots = await database_service.get_active_slots()
    print(f"\n--- ACTIVE SLOTS ({len(slots)}) ---")
    for s in slots:
        status = s.get('status_risco', 'UNKNOWN')
        symbol = s.get('symbol', 'FREE')
        print(f"Slot {s['id']}: {symbol} [{status}]")

    # 5. Check History
    history = await database_service.get_trade_history(limit=10)
    print(f"\n--- RECENT HISTORY ({len(history)}) ---")
    if not history:
        print("History is EMPTY in database.")
    for t in history:
        print(f"{t.get('timestamp')} | {t.get('symbol')} | PnL: {t.get('pnl')} | {t.get('close_reason')}")

    # 6. Check Vault Cycle
    vault = await database_service.get_vault_cycle()
    print("\n--- VAULT CYCLE ---")
    if vault:
        print(f"Cycle: {vault.get('cycle_number')}")
        print(f"Wins: {vault.get('sniper_wins')}/10")
        print(f"Profit: {vault.get('cycle_profit')}")
        print(f"Active: {vault.get('sniper_mode_active')}")
        print(f"Total Trades: {vault.get('total_trades_cycle')}/100")
    else:
        print("Vault cycle data NOT FOUND.")


if __name__ == "__main__":
    asyncio.run(run_diag())
