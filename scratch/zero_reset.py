"""
ZERO RESET - Purga total do sistema para novo ciclo limpo
Limpa: slots, moonbags, trade_history, vault_cycles, order_genesis
Reseta: banca para $100.00
"""
import asyncio
import asyncpg
import os
from datetime import datetime

_RAW_URL = os.getenv("DATABASE_URL", "")
if _RAW_URL and "<sua_url_do_postgres>" not in _RAW_URL and ("postgres://" in _RAW_URL or "postgresql://" in _RAW_URL):
    DATABASE_URL = _RAW_URL
else:
    DATABASE_URL = "postgresql://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"

async def zero_reset():
    print("=" * 60)
    print("ZERO RESET - Purga Total do Sistema")
    print("=" * 60)
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        # 0. Garantir que banca_status existe (id=1)
        banca_exists = await conn.fetchval("SELECT COUNT(*) FROM banca_status WHERE id = 1")
        if banca_exists == 0:
            print("\nCriando registro banca_status id=1...")
            await conn.execute("INSERT INTO banca_status (id, saldo_total, risco_real_percent, slots_disponiveis, status) VALUES (1, 100.0, 0.0, 4, 'INIT')")
        
        # 1. Ver estado atual
        banca = await conn.fetchrow("SELECT saldo_total, status FROM banca_status WHERE id = 1")
        slots = await conn.fetch("SELECT id, symbol, side, status_risco, pnl_percent FROM slots ORDER BY id")
        moonbags_count = await conn.fetchval("SELECT COUNT(*) FROM moonbags")
        trades_count = await conn.fetchval("SELECT COUNT(*) FROM trade_history")
        
        print(f"\nESTADO ANTES DO RESET:")
        print(f"  Banca: ${float(banca['saldo_total']):.2f} ({banca['status']})")
        for s in slots:
            if s['symbol']:
                print(f"  Slot {s['id']}: {s['symbol']} {s['side']} | {s['status_risco']} | PnL: {float(s['pnl_percent']):.1f}%")
            else:
                print(f"  Slot {s['id']}: LIVRE")
        print(f"  Moonbags registradas: {moonbags_count}")
        print(f"  Trade History registros: {trades_count}")
        
        print(f"\nEXECUTANDO PURGA...")
        
        # 2. Limpar Trade History
        print("  -> Apagando trade_history...")
        await conn.execute("DELETE FROM trade_history")
        
        # 3. Limpar Moonbags
        print("  -> Apagando moonbags...")
        await conn.execute("DELETE FROM moonbags")
        
        # 4. Limpar Order Genesis
        try:
            await conn.execute("DELETE FROM order_genesis")
            print("  -> Apagando order_genesis...")
        except:
            print("  -> Tabela order_genesis nao existe (ignorando)")
        
        # 5. Resetar Slots para LIVRE
        print("  -> Resetando slots para LIVRE...")
        now = datetime.utcnow()
        await conn.execute("""
            UPDATE slots 
            SET symbol = NULL, 
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
                vision_url = NULL,
                pensamento = 'ZERO RESET',
                score = 0,
                opened_at = NULL,
                updated_at = $1
        """, now)
        
        # 6. Resetar Banca para $100.00
        print("  -> Resetando banca para $100.00...")
        await conn.execute("""
            UPDATE banca_status 
            SET saldo_total = 100.0, 
                status = 'ZERO_RESET',
                risco_real_percent = 0.0,
                updated_at = $1
            WHERE id = 1
        """, now)
        
        # 7. Resetar Vault Cycles
        try:
            await conn.execute("""
                UPDATE vault_cycles 
                SET sniper_wins = 0, 
                    cycle_profit = 0.0, 
                    cycle_losses = 0, 
                    total_trades_cycle = 0, 
                    accumulated_vault = 0.0
                WHERE id = 1
            """)
            print("  -> Resetando vault_cycles...")
        except:
            print("  -> Tabela vault_cycles nao existe (ignorando)")
        
        # 8. Verificar estado final
        banca2 = await conn.fetchrow("SELECT saldo_total, status FROM banca_status WHERE id = 1")
        slots2 = await conn.fetch("SELECT id, symbol, status_risco FROM slots ORDER BY id")
        moons2 = await conn.fetchval("SELECT COUNT(*) FROM moonbags")
        trades2 = await conn.fetchval("SELECT COUNT(*) FROM trade_history")
        
        print(f"\nESTADO APOS RESET:")
        print(f"  Banca: ${float(banca2['saldo_total']):.2f} ({banca2['status']})")
        for s in slots2:
            if s['symbol']:
                print(f"  Slot {s['id']}: {s['symbol']} ({s['status_risco']})")
            else:
                print(f"  Slot {s['id']}: LIVRE ({s['status_risco']})")
        print(f"  Moonbags: {moons2}")
        print(f"  Trade History: {trades2}")
        print(f"\nSISTEMA PRONTO PARA NOVO CICLO!")
        
    except Exception as e:
        print(f"\nERRO: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(zero_reset())
