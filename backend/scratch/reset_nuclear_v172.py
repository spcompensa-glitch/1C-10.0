import asyncio
import os
import sys
from dotenv import load_dotenv

# Carregar variáveis do .env do backend
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)

# Adicionar backend ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text
from services.database_service import database_service

async def reset_full():
    print("🚨 RESET NUCLEAR V110.172 — Iniciando limpeza total...")
    
    # Inicializa engine
    await database_service.initialize()
    
    async with database_service.engine.begin() as conn:
        print("1. Limpando Histórico de Trades, Moonbags e Genesis...")
        try:
            await conn.execute(text("DELETE FROM trade_history"))
        except Exception as e:
            print(f"   (Ignorado) trade_history: {e}")
            
        try:
            await conn.execute(text("DELETE FROM moonbags"))
        except Exception as e:
            print(f"   (Ignorado) moonbags: {e}")
            
        try:
            await conn.execute(text("DELETE FROM order_genesis"))
        except Exception as e:
            print(f"   (Ignorado) order_genesis: {e}")
            
        try:
            await conn.execute(text("DELETE FROM vault_withdrawals"))
        except Exception as e:
            print(f"   (Ignorado) vault_withdrawals: {e}")
        
        print("2. Limpando Sandbox Lab (todos os trades simulados)...")
        try:
            await conn.execute(text("DELETE FROM sandbox_trades"))
        except Exception as e:
            print(f"   (Ignorado) sandbox_trades: {e}")
        
        print("3. Resetando Slots...")
        await conn.execute(text("""
            UPDATE slots SET 
                symbol = NULL, 
                side = NULL, 
                qty = 0.0, 
                entry_price = 0.0, 
                entry_margin = 0.0,
                current_stop = 0.0, 
                initial_stop = 0.0, 
                target_price = 0.0, 
                liq_price = 0.0, 
                pnl_percent = 0.0, 
                status_risco = 'LIVRE',
                order_id = NULL,
                genesis_id = NULL,
                market_regime = NULL,
                unified_confidence = 50,
                fleet_intel = NULL,
                pensamento = NULL,
                sentinel_first_hit_at = 0.0,
                opened_at = 0.0
        """))
        
        print("4. Resetando Banca para $100.00...")
        await conn.execute(text("""
            UPDATE banca_status SET 
                saldo_total = 100.0, 
                risco_real_percent = 0.0, 
                slots_disponiveis = 4, 
                status = 'FACTORY_RESET'
        """))
        
        print("5. Resetando Vault Cycles...")
        try:
            await conn.execute(text("""
                UPDATE vault_cycles SET 
                    sniper_wins = 0, 
                    cycle_number = 1, 
                    cycle_profit = 0.0, 
                    cycle_losses = 0.0,
                    vault_total = 0.0,
                    total_trades_cycle = 0,
                    cycle_gains_count = 0,
                    cycle_losses_count = 0,
                    accumulated_vault = 0.0,
                    used_symbols_in_cycle = '[]'::jsonb,
                    cycle_start_bankroll = 100.0,
                    next_entry_value = 0.0,
                    mega_cycle_wins = 0,
                    mega_cycle_total = 0,
                    mega_cycle_number = 1,
                    mega_cycle_profit = 0.0,
                    order_ids_processed = '[]'::jsonb
            """))
        except Exception as e:
            print(f"   (Ignorado) vault_cycles: {e}")
        
        print("6. Limpando System State (Paper Engine)...")
        try:
            await conn.execute(text("DELETE FROM system_state"))
        except Exception as e:
            print(f"   (Ignorado) system_state: {e}")

        print("7. Verificando estado final...")
        r = await conn.execute(text("SELECT COUNT(*) FROM sandbox_trades"))
        count_sandbox = r.fetchone()[0]
        
        r2 = await conn.execute(text("SELECT saldo_total, status FROM banca_status LIMIT 1"))
        banca = r2.fetchone()
        
        r3 = await conn.execute(text("SELECT COUNT(*) FROM trade_history"))
        count_hist = r3.fetchone()[0]
        
        print(f"\n✅ RESET NUCLEAR CONCLUÍDO!")
        print(f"   Sandbox Trades: {count_sandbox} (deve ser 0)")
        print(f"   Trade History:  {count_hist} (deve ser 0)")
        print(f"   Banca: ${banca[0] if banca else 'N/A'} | Status: {banca[1] if banca else 'N/A'}")
        print(f"\n🚀 Sistema zerado e pronto para novo ciclo com as correções V110.172!")

if __name__ == "__main__":
    asyncio.run(reset_full())
