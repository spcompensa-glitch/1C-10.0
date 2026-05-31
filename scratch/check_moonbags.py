import asyncio
import os
import sys
from dotenv import load_dotenv

# Forçar override=True para carregar as credenciais corretas do .env do backend
load_dotenv('backend/.env', override=True)

# Ajusta sys.path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from services.database_service import database_service

async def main():
    try:
        await database_service.initialize()
        
        # Obter moonbags do Postgres
        async with database_service.AsyncSessionLocal() as session:
            from sqlalchemy import text
            result = await session.execute(text("SELECT * FROM moonbags"))
            rows = result.fetchall()
            
            print("=== MOONBAGS NO POSTGRES ===")
            if not rows:
                print("Nenhuma moonbag encontrada no Postgres.")
            for r in rows:
                print(r)
                
    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    asyncio.run(main())
