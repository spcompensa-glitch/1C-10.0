
import asyncio
import os
import sys

# Adiciona o caminho do projeto ao sys.path
sys.path.append(os.path.join(os.getcwd(), "1CRYPTEN_SPACE_V4.0", "backend"))

from services.sovereign_service import sovereign_service
from services.execution_protocol import execution_protocol
from services.okx_rest import okx_rest_service

async def diag():
    print("--- DIAGNÓSTICO DE SLOTS ATIVOS ---")
    slots = await sovereign_service.get_active_slots()
    
    # Simula a captura de preços como no loop real
    resp = await okx_rest_service.get_tickers()
    ticker_list = resp.get("result", {}).get("list", [])
    price_map = {t["symbol"]: float(t.get("lastPrice", 0)) for t in ticker_list}

    for s in slots:
        symbol = s.get("symbol")
        if not symbol: continue
        
        entry = float(s.get("entry_price", 0))
        current_stop = float(s.get("current_stop", 0))
        side = s.get("side", "Buy")
        leverage = float(s.get("leverage", 50.0))
        slot_type = s.get("slot_type")
        
        price = price_map.get(symbol.replace(".P", ""))
        if not price:
            print(f"Erro: Preço para {symbol} não encontrado.")
            continue
            
        roi = execution_protocol.calculate_roi(entry, price, side, leverage=leverage)
        
        print(f"Ativo: {symbol}")
        print(f"  Slot Type: {slot_type}")
        print(f"  Entry: {entry} | Price: {price} | ROI: {roi:.2f}%")
        print(f"  Current SL: {current_stop}")
        
        # Simula a lógica de decisão
        slot_data = {
            "symbol": symbol,
            "side": side,
            "entry_price": entry,
            "current_stop": current_stop,
            "slot_type": slot_type,
            "leverage": leverage,
            "status": s.get("status")
        }
        
        should_close, reason, new_sl = await execution_protocol.process_order_logic(slot_data, price)
        print(f"  Decisão: Close={should_close} | Reason={reason} | New SL={new_sl}")
        print("-" * 30)

if __name__ == "__main__":
    asyncio.run(diag())
