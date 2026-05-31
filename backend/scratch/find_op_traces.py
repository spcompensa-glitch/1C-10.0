# -*- coding: utf-8 -*-
import asyncio
import asyncpg

async def inspect_trade_history():
    db_url = "postgresql://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"
    conn = await asyncpg.connect(db_url)
    try:
        print("🔍 --- INSPECIONANDO TABELA trade_history ---")
        
        # 1. Pega as colunas da tabela trade_history
        columns = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'trade_history'
        """)
        print("\nColunas em 'trade_history':")
        for col in columns:
            print(f"  - {col['column_name']} ({col['data_type']})")
            
        # 2. Pega todos os registros de trade_history
        print("\nRegistros em 'trade_history':")
        rows = await conn.fetch("SELECT * FROM trade_history ORDER BY id DESC LIMIT 50")
        if rows:
            for r in rows:
                print(dict(r))
        else:
            print("Nenhum registro encontrado em 'trade_history'.")

        # 3. Pega os registros de moonbags
        print("\nRegistros em 'moonbags':")
        moons = await conn.fetch("SELECT * FROM moonbags")
        if moons:
            for m in moons:
                print(dict(m))
        else:
            print("Nenhum registro encontrado em 'moonbags'.")

    except Exception as e:
        print(f"❌ Erro na inspeção: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(inspect_trade_history())
