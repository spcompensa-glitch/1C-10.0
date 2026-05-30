import asyncio
import os
import sys
from sqlalchemy import create_async_engine, text

async def main():
    db_url = "postgresql+asyncpg://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"
    engine = create_async_engine(db_url)
    
    async with engine.connect() as conn:
        # Query column names for 'slots' table
        result = await conn.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'slots';"
        ))
        columns = result.fetchall()
        print("--- COLUMNS IN 'slots' ---")
        for col in columns:
            print(f"{col[0]}: {col[1]}")
            
        # Also let's check trade_history and moonbags
        result_th = await conn.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'trade_history';"
        ))
        print("\n--- COLUMNS IN 'trade_history' ---")
        for col in result_th.fetchall():
            print(f"{col[0]}: {col[1]}")
            
        result_mb = await conn.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'moonbags';"
        ))
        print("\n--- COLUMNS IN 'moonbags' ---")
        for col in result_mb.fetchall():
            print(f"{col[0]}: {col[1]}")

if __name__ == "__main__":
    asyncio.run(main())
