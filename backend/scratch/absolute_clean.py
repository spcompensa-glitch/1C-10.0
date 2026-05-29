import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def absolute_clean():
    db_url = "postgresql+asyncpg://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"
    print("Conectando ao banco de dados Postgres de producao no Railway...")
    engine = create_async_engine(db_url)
    try:
        async with engine.connect() as conn:
            # 1. Deleta o estado persistente do Motor Paper
            print("Removendo estado salvo do motor Paper na tabela system_state...")
            await conn.execute(text("DELETE FROM system_state WHERE key = 'paper_engine_state'"))
            
            # 2. Reseta a Banca para $100.00 e Slots Disponiveis para 4
            print("Resetando status da banca para $100.00 no Postgres de producao...")
            await conn.execute(text("""
                UPDATE banca_status 
                SET saldo_total = 100.0, risco_real_percent = 0.0, slots_disponiveis = 4, status = 'ONLINE' 
                WHERE id = 1
            """))

            # 3. Zera os 4 slots taticos
            print("Zerando os 4 slots no banco Postgres de producao...")
            for i in range(1, 5):
                await conn.execute(text("""
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
                """), {"slot_id": i})
            
            await conn.commit()
            print("[SUCESSO] Todo o estado persistente de slots, banca e motor paper foi purificado no Postgres de producao.")
            print("\nATENCAO: Para efetivar este reset, voce deve REINICIAR (ou dar REDEPLOY) no servico de backend do Railway.")
            print("Isso limpara as posicoes ativas na memoria RAM do processo que esta rodando agora na nuvem.")
            
    except Exception as e:
        print(f"[ERRO] Falha durante a limpeza do Postgres: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(absolute_clean())
