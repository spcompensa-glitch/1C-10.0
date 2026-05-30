import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    db_url = "postgresql+asyncpg://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"
    print("Connecting to Postgres with a 3s timeout...")
    engine = create_async_engine(db_url, connect_args={"timeout": 3})
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1;"))
            print("Successfully connected! Result:", result.fetchall())
    except Exception as e:
        print("Failed to connect:", e)

if __name__ == "__main__":
    asyncio.run(main())
