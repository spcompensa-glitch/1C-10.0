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

try:
    from services.database_service import database_service
    from services.database_service import TradeHistory
except ImportError:
    from backend.services.database_service import database_service
    from backend.services.database_service import TradeHistory

from sqlalchemy import select, desc

async def main():
    try:
        await database_service.initialize()
        print("Conectado ao banco Postgres de produção com sucesso.")
        
        async with database_service.AsyncSessionLocal() as session:
            # 1. Busca os últimos 30 registros da tabela trade_history
            res = await session.execute(
                select(TradeHistory).order_by(desc(TradeHistory.timestamp)).limit(30)
            )
            history = res.scalars().all()
            
            print("\n=== ÚLTIMOS TRADES NO HISTÓRICO DE PRODUÇÃO ===")
            if not history:
                print("Nenhum histórico de trade encontrado no Postgres de produção.")
            for t in history:
                print(f"[{t.timestamp}] {t.symbol} | Lado={t.side} | PnL=${t.pnl:.2f} ({t.pnl_percent:.1f}%) | Entrada={t.entry_price} | Saída={t.exit_price} | Motivo={t.close_reason} | Estratégia={t.strategy}")
                
    except Exception as e:
        print(f"Erro ao ler histórico de trades de produção: {e}")

if __name__ == "__main__":
    asyncio.run(main())
