# -*- coding: utf-8 -*-
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def reset_banca_and_db():
    db_url = "postgresql+asyncpg://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"
    print("Conectando ao banco de dados Postgres de producao do Railway para reset total...")
    engine = create_async_engine(db_url)
    
    # 1. Query para redefinir todos os slots para LIVRE e limpar dados
    query_slots = """
        UPDATE slots SET
            symbol = NULL,
            side = NULL,
            qty = 0.0,
            entry_price = 0.0,
            entry_margin = 0.0,
            current_stop = 0.0,
            initial_stop = 0.0,
            order_id = NULL,
            target_price = 0.0,
            leverage = 50.0,
            slot_type = NULL,
            status_risco = 'LIVRE',
            pnl_percent = 0.0,
            strategy = NULL,
            genesis_id = NULL,
            opened_at = NULL,
            pensamento = 'Resetado para aguardar novos setups qualificados do funil de 5 etapas.',
            liq_price = 0.0,
            score = 0.0
    """

    # 2. Query para redefinir a banca status para 100 dólares
    query_banca = """
        UPDATE banca_status SET
            saldo_total = 100.0,
            risco_real_percent = 0.0,
            slots_disponiveis = 4
        WHERE id = 1
    """

    # 3. Queries para limpar tabelas
    query_history = "DELETE FROM trade_history"
    query_moons = "DELETE FROM moonbags"
    query_genesis = "DELETE FROM order_genesis"

    try:
        async with engine.connect() as conn:
            print("Limpando slots de producao...")
            await conn.execute(text(query_slots))
            
            print("Redefinindo banca para $100.00 de saldo inicial...")
            await conn.execute(text(query_banca))
            
            print("Limpando historico de trades...")
            await conn.execute(text(query_history))
            
            print("Limpando moonbags residuais...")
            await conn.execute(text(query_moons))
            
            print("Limpando tabela order_genesis...")
            await conn.execute(text(query_genesis))
            
            await conn.commit()
            print("[SUCESSO ABSOLUTO] O banco de dados Postgres do Railway foi completamente limpo e a banca foi resetada para $100.00!")
    except Exception as e:
        print(f"[ERRO CRITICO] Erro ao redefinir banco e banca: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(reset_banca_and_db())
