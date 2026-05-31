# -*- coding: utf-8 -*-
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def clean_moons():
    db_url = "postgresql+asyncpg://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"
    print("Conectando ao banco de dados Postgres de producao do Railway para limpar Moonbags...")
    engine = create_async_engine(db_url)
    
    query = "DELETE FROM moonbags"
    
    try:
        async with engine.connect() as conn:
            await conn.execute(text(query))
            await conn.commit()
            print("[SUCESSO] Todas as moonbags legadas foram removidas da tabela moonbags no Postgres.")
    except Exception as e:
        print(f"[ERRO CRITICO] Erro ao limpar moonbags: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(clean_moons())
