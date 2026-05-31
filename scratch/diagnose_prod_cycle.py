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
except ImportError:
    from backend.services.firebase_service import firebase_service

async def main():
    try:
        await firebase_service.initialize()
        print("Firebase inicializado com sucesso.")
        
        # 1. Busca o status da banca
        banca = await firebase_service.get_banca_status()
        print(f"\n=== BANCA STATUS ===")
        print(banca)
        
        # 2. Busca o documento de gerenciamento do ciclo do Almirante (vault_management/current_cycle)
        def _get():
            doc = firebase_service.db.collection("vault_management").document("current_cycle").get()
            return doc.to_dict() if doc.exists else None
            
        cycle = await asyncio.to_thread(_get)
        print(f"\n=== STATUS DO CICLO DO ALMIRANTE ===")
        if not cycle:
            print("Nenhum ciclo encontrado no Firestore de produção.")
        else:
            for k, v in cycle.items():
                print(f"{k}: {v}")
                
    except Exception as e:
        print(f"Erro ao conectar ao Firebase de produção: {e}")

if __name__ == "__main__":
    asyncio.run(main())
