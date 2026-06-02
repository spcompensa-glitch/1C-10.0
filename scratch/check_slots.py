import asyncio
import os
import sys

# Adicionar o diretório atual ao path para importar os serviços
sys.path.append(os.path.join(os.getcwd(), "1CRYPTEN_SPACE_V4.0", "backend"))

async def diag_slots():
    print("--- Iniciando Diagnostico de Slots ---")
    try:
        from services.sovereign_service import sovereign_service
        from services.okx_rest import okx_rest_service
        
        print(f"Modo de Execucao: {okx_rest_service.execution_mode}")
        
        slots = await sovereign_service.get_active_slots(force_refresh=True)
        print("\n--- Estado dos Slots (Sovereign) ---")
        for slot in slots:
            symbol = slot.get('symbol')
            print(f"Slot {slot.get('id')}: {symbol if symbol else 'LIVRE'} | PnL: {slot.get('pnl_percent', 0):.2f}%")
            
        if okx_rest_service.execution_mode == "PAPER":
            print("\n--- Posicoes em Paper Mode ---")
            positions = okx_rest_service.paper_positions
            if not positions:
                print("Nenhuma posicao ativa em Paper.")
            for pos in positions:
                print(f"Ativo: {pos.get('symbol')} | Lado: {pos.get('side')} | Qtd: {pos.get('size')}")
                
        # Verificar se o trading está permitido
        from services.vault_service import vault_service
        allowed, reason = await vault_service.is_trading_allowed()
        print(f"\nTrading Permitido: {allowed} | Motivo: {reason}")

    except Exception as e:
        print(f"❌ Erro no diagnóstico: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(diag_slots())
