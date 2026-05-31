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

# Configura o diretório de trabalho do Firebase para ser dentro do backend/
os.chdir(os.path.join(root_dir, 'backend'))

try:
    from services.firebase_service import firebase_service
    from services.okx_rest import okx_rest_service
except ImportError:
    from backend.services.firebase_service import firebase_service
    from backend.services.okx_rest import okx_rest_service

async def main():
    try:
        await firebase_service.initialize()
        print("Firebase inicializado com sucesso.")
        
        banca = await firebase_service.get_banca_status()
        print(f"\n=== BANCA STATUS ===")
        print(banca)
        
        state = await firebase_service.get_paper_state()
        print(f"\n=== ESTADO PAPER DO FIRESTORE ===")
        if not state:
            print("Nenhum estado paper encontrado.")
        else:
            print(f"Saldo: {state.get('balance')}")
            print(f"Posições ({len(state.get('positions', []))}):")
            for p in state.get('positions', []):
                print(f"  - {p.get('symbol')} | {p.get('side')} | Qty={p.get('size')} | Entry={p.get('avgPrice')} | Stop={p.get('stopLoss')} | Status={p.get('status')}")
            
            print(f"Moonbags ({len(state.get('moonbags', []))}):")
            for m in state.get('moonbags', []):
                print(f"  - {m.get('symbol')} | {m.get('side')} | Qty={m.get('size')} | Entry={m.get('avgPrice')} | Stop={m.get('stopLoss')} | Status={m.get('status')}")
                
            print(f"Histórico ({len(state.get('history', []))}):")
            for h in state.get('history', [])[:5]:
                print(f"  - {h.get('symbol')} | PnL={h.get('pnl')} | Status={h.get('status')}")
                
    except Exception as e:
        print(f"Erro ao conectar ao Firebase: {e}")

if __name__ == "__main__":
    asyncio.run(main())
