import asyncio
import asyncpg

DATABASE_URL = "postgresql://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"

async def check():
    print("=" * 60)
    print("🔎 COMPARAÇÃO E AUDITORIA PROFUNDA DO BANCO DE DADOS")
    print("=" * 60)
    
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # 1. Checar slots atuais
        slots = await conn.fetch("SELECT id, symbol, side, status_risco, updated_at, pensamento FROM slots ORDER BY id")
        print("\nSlots Atuais no Postgres:")
        for s in slots:
            print(f"  Slot {s['id']}: {s['symbol']} | Lado={s['side']} | Risco={s['status_risco']} | Atualizado={s['updated_at']} | Pensamento={s['pensamento'][:60]}")
            
        # 2. Checar moonbags
        moonbags = await conn.fetch("SELECT uuid, symbol, side, pnl_percent FROM moonbags")
        print("\nMoonbags Atuais no Postgres:")
        if not moonbags:
            print("  Nenhuma Moonbag ativa.")
        for m in moonbags:
            print(f"  Moonbag {m['uuid']}: {m['symbol']} | Lado={m['side']} | PnL={m['pnl_percent']}%")
            
        # 3. Checar trade_history
        trades = await conn.fetch("SELECT id, symbol, side, pnl, close_reason, timestamp FROM trade_history ORDER BY timestamp DESC")
        print("\nHistórico de Trades no Postgres:")
        if not trades:
            print("  Nenhum trade finalizado no histórico.")
        for t in trades:
            print(f"  Trade {t['id']}: {t['symbol']} | Lado={t['side']} | PnL=${t['pnl']} | Motivo={t['close_reason']} | Data={t['timestamp']}")
            
        # 4. Checar se existem outras tabelas ou registros órfãos
        try:
            genesis = await conn.fetch("SELECT id, symbol, side, opened_at FROM order_genesis ORDER BY opened_at DESC")
            print("\nOrder Genesis no Postgres:")
            if not genesis:
                print("  Nenhum registro de gênese encontrado.")
            for g in genesis:
                print(f"  Genesis {g['id']}: {g['symbol']} | Lado={g['side']} | Data={g['opened_at']}")
        except Exception as e:
            print(f"\nErro ao ler order_genesis: {e}")
            
    except Exception as e:
        print(f"\nErro geral na auditoria: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check())
