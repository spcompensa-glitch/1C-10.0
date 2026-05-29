import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def clean_slots():
    db_url = "postgresql+asyncpg://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"
    print("Conectando ao banco de dados Postgres de producao do Railway...")
    engine = create_async_engine(db_url)
    
    # 1. Tentativa de Query Completa (com as novas colunas mapeadas)
    query_completa = """
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
        WHERE id = :slot_id
    """

    # 2. Query de Fallback Minimalista (apenas colunas garantidas no banco de producao legado)
    query_fallback = """
        UPDATE slots SET
            symbol = NULL,
            side = NULL,
            qty = 0.0,
            entry_price = 0.0,
            order_id = NULL,
            status_risco = 'LIVRE',
            pnl_percent = 0.0,
            opened_at = NULL
        WHERE id = :slot_id
    """

    try:
        async with engine.connect() as conn:
            print("Tentando redefinir slots usando a query completa...")
            try:
                for i in range(1, 5):
                    await conn.execute(text(query_completa), {"slot_id": i})
                await conn.commit()
                print("[SUCESSO] Os 4 slots de producao foram limpos via Query Completa.")
            except Exception as e:
                print(f"[AVISO] Query completa falhou devido a colunas ausentes: {e}")
                print("Iniciando query de fallback minimalista...")
                for i in range(1, 5):
                    await conn.execute(text(query_fallback), {"slot_id": i})
                await conn.commit()
                print("[SUCESSO] Os 4 slots de producao foram limpos e redefinidos para LIVRE via Fallback Minimalista.")
                
    except Exception as e:
        print(f"[ERRO CRITICO] Erro ao limpar slots de producao: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(clean_slots())
