import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from services.okx_service import okx_service
from services.signal_generator import signal_generator

async def main():
    print("=== MONITOR DE DIRETRIZES DO MERCADO ===")
    try:
        btc_macro = await signal_generator.get_daily_macro_filter("BTCUSDT")
        print(f"BTC Macro: {btc_macro}")
        
        # Obter ADX atual do BTC
        klines = await okx_service.get_klines("BTC-USDT-SWAP", "1H", 100)
        # Tentar obter do WS ou calcular
        price = float(klines[0][4])
        print(f"Último preço do BTC: ${price:,.2f}")
        
        above_200 = btc_macro.get("above_200sma", True)
        trend = "BULLISH" if above_200 else "BEARISH"
        
        print("\n=== REGRAS DE FILTRO ATUAIS ===")
        print(f"1. Direção Macro: {trend}")
        print(f"   -> Apenas sinais de {'LONG' if trend == 'BULLISH' else 'SHORT'} serão aceitos.")
        print(f"   -> Sinais de {'SHORT' if trend == 'BULLISH' else 'LONG'} serão bloqueados.")
        
    except Exception as e:
        print(f"Erro ao verificar: {e}")

if __name__ == "__main__":
    asyncio.run(main())
