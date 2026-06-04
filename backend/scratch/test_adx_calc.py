import asyncio
import sys
import os

# Adiciona o diretório do backend ao sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_dir)

# Carrega o .env manualmente para garantir as chaves e URL
env_path = os.path.join(backend_dir, ".env")
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                key, val = line.strip().split("=", 1)
                os.environ[key.strip()] = val.strip()

async def main():
    try:
        from services.okx_ws_public import okx_ws_public_service
        from services.okx_rest import okx_rest_service
        from services.database_service import database_service
        
        await database_service.initialize()
        await okx_rest_service.initialize()
        
        print("=== Testando Calculo do ADX e Indicadores do BTC ===")
        print("Buscando dados em tempo real da API publica da OKX...")
        
        # Executa a atualização do contexto do mercado (ADX, Variacoes, etc.)
        await okx_ws_public_service.update_market_context()
        
        print("\n--- Resultados Obtidos ---")
        print(f"Preco do BTC: ${okx_ws_public_service.btc_price:,.2f}")
        print(f"Variacao BTC 1h: {okx_ws_public_service.btc_variation_1h:+.2f}%")
        print(f"Variacao BTC 15m: {okx_ws_public_service.btc_variation_15m:+.2f}%")
        print(f"Variacao BTC 24h: {okx_ws_public_service.btc_variation_24h:+.2f}%")
        print(f"Calculo Master ADX (M-ADX): {okx_ws_public_service.btc_adx:.2f}")
        
        # Determinar regime e direcao baseado no novo ADX e nas variacoes
        adx = okx_ws_public_service.btc_adx
        if adx >= 30: regime = "ROARING"
        elif adx >= 25: regime = "TRENDING"
        else: regime = "RANGING"
        
        variation_1h = okx_ws_public_service.btc_variation_1h
        variation_15m = okx_ws_public_service.btc_variation_15m
        
        if adx >= 25:
            if variation_15m > 0 and variation_1h > 0:
                btc_direction = "UP"
            elif variation_15m < 0 and variation_1h < 0:
                btc_direction = "DOWN"
            else:
                btc_direction = "LATERAL"
        else:
            btc_direction = "LATERAL"
            
        print(f"Regime de Mercado Classificado: {regime}")
        print(f"Direcao do BTC Classificada: {btc_direction}")
        print("====================================================")

    except Exception as e:
        print(f"Erro no teste: {e}")

if __name__ == "__main__":
    asyncio.run(main())
