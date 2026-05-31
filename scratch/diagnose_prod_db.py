# coding: utf-8
import sys
import os
import asyncio

# Adiciona o root e o backend ao sys.path
root_dir = os.getcwd()
sys.path.insert(0, root_dir)
sys.path.insert(0, os.path.join(root_dir, 'backend'))

# Lê o backend/.env manualmente e define as variáveis de ambiente
env_path = os.path.join(root_dir, 'backend', '.env')
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key.strip()] = val.strip()

# Importação robusta do database_service
try:
    from services.database_service import database_service
    from services.database_service import Moonbag
except ImportError:
    from backend.services.database_service import database_service
    from backend.services.database_service import Moonbag

from sqlalchemy import select

async def main():
    print(f"DATABASE_URL definida: {os.environ.get('DATABASE_URL')}")
    try:
        await database_service.initialize()
        slots = await database_service.get_active_slots()
        print("\n=== SLOTS ATIVOS NO POSTGRES DE PRODUÇÃO ===")
        for s in slots:
            print(f"Slot {s['id']}: Símbolo={s['symbol']} | Lado={s['side']} | Entrada={s['entry_price']} | Stop={s['current_stop']} | Risco={s['status_risco']}")
            
        print("\n=== VERIFICANDO MOONBAGS NO POSTGRES DE PRODUÇÃO ===")
        async with database_service.AsyncSessionLocal() as session:
            res = await session.execute(select(Moonbag))
            moons = res.scalars().all()
            if not moons:
                print("Nenhuma moonbag encontrada no Postgres de produção.")
            for m in moons:
                print(f"Moonbag: {m.symbol} | Lado={m.side} | Qty={m.qty} | Entrada={m.entry_price} | Stop={m.current_stop} | ROI={m.pnl_percent}%")
                
    except Exception as e:
        print(f"Erro ao conectar ao banco de produção: {e}")

if __name__ == "__main__":
    asyncio.run(main())
