import sys
import os
import asyncio

# Adiciona o diretório backend ao path para que os imports funcionem perfeitamente
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from services.bankroll import bankroll_manager

async def main():
    print("=" * 60)
    print("🚀 INJETOR DE TESTE DE FOGO FORÇADO - SLOT 1")
    print("=" * 60)
    
    # AVAXUSDT, Buy, slot_type = BLITZ_30M
    print("\n[INFO] Solicitando abertura de posição simulada de AVAXUSDT no Slot 1...")
    
    order = await bankroll_manager.open_position(
        symbol="AVAXUSDT",
        side="Buy",
        pensamento="Teste de Fogo Forçado - Validando Cockpit e SlotOperatorAgent 1",
        slot_type="BLITZ_30M",
        target_slot_id=1
    )
    
    if order:
        print("\n✅ SUCESSO! A ordem simulada foi aberta com sucesso e vinculada ao Slot 1.")
        print(f"   Símbolo: {order.get('symbol')}")
        print(f"   Lado: {order.get('side')}")
        print(f"   Preço de Entrada: ${order.get('entry_price')}")
        print(f"   Quantidade: {order.get('qty')}")
        print(f"   Pensamento: {order.get('pensamento')}")
    else:
        print("\n❌ FALHA! Não foi possível abrir a ordem de teste.")

if __name__ == "__main__":
    asyncio.run(main())
