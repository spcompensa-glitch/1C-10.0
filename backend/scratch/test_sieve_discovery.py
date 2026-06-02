import asyncio
import logging
import sys
import os

# Adiciona o diretório backend ao path para importar os serviços
sys.path.append(os.path.join(os.getcwd(), "backend"))

from services.okx_rest import okx_rest_service

async def test_sieve_discovery():
    print("🚀 [TEST] Iniciando descoberta do Sniper Sieve (Tier 1)...")
    
    # Inicializa o serviço (necessário para o session)
    await okx_rest_service.initialize()
    
    candidates = await okx_rest_service.get_sieve_candidates()
    
    print(f"\n📊 Resultados:")
    print(f"Total de ativos qualificados: {len(candidates)}")
    print(f"Top 10 Amostra: {candidates[:10]}")
    
    # Verifica exclusão de BTC/ETH/SOL
    for forbidden in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        if forbidden in candidates:
            print(f"❌ ERRO: {forbidden} não deveria estar na lista!")
        else:
            print(f"✅ SUCESSO: {forbidden} excluído corretamente.")

if __name__ == "__main__":
    asyncio.run(test_sieve_discovery())
