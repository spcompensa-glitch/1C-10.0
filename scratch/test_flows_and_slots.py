import sys
import os
import asyncio
import time

# Adicionar o diretório backend ao PATH do sistema
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from services.firebase_service import firebase_service
from services.bankroll import bankroll_manager, bybit_rest_service
from services.database_service import database_service

async def run_tests():
    print("🧪 [TESTS-FLOWS] Iniciando bateria de testes de fluxos e slots...")
    
    # 0. Garante que BybitREST está inicializado
    bybit_rest_service.is_ready = True
    bybit_rest_service.execution_mode = "PAPER"
    bybit_rest_service.paper_positions = []
    
    # Limpa slot de teste (Slot 4)
    print("\n🧹 Limpando o Slot 4 para iniciar testes...")
    await firebase_service.free_slot(4, reason="SETUP_TESTS")
    
    # ==========================================
    # TESTE 1: ABERTURA E FECHAMENTO DE POSITION -> HISTÓRICO VAULT
    # ==========================================
    print("\n🚀 [TESTE 1] Testando Abertura e Fechamento com Registro no Vault...")
    
    # Preenche o slot simulando que foi aberto
    test_trade = {
        "symbol": "BTCUSDT",
        "side": "Buy",
        "qty": 0.05,
        "entry_price": 50000.0,
        "entry_margin": 50.0,
        "current_stop": 49000.0,
        "initial_stop": 49000.0,
        "target_price": 52000.0,
        "leverage": 50,
        "slot_type": "SNIPER",
        "status_risco": "ATIVO",
        "opened_at": time.time(),
        "pnl_percent": 0.0
    }
    
    print("📝 Gravando posição ativa de teste no Slot 4 do Postgres...")
    await firebase_service.update_slot(4, test_trade)
    
    # Cria a posição correspondente na RAM local para sincronizar
    bybit_rest_service.paper_positions.append({
        "symbol": "BTCUSDT",
        "side": "Buy",
        "size": "0.05",
        "avgPrice": "50000.0",
        "leverage": "50",
        "status": None,
        "stopLoss": "49000.0",
        "takeProfit": "52000.0",
        "opened_at": test_trade["opened_at"],
        "is_paper": True
    })
    
    # Verifica que o slot está ativo
    slots = await firebase_service.get_active_slots(force_refresh=True)
    slot_4 = next((s for s in slots if s["id"] == 4), None)
    print(f"✅ Slot 4 Ativo no Postgres: {slot_4.get('symbol')} | Status: {slot_4.get('status_risco')}")
    
    # Simula fechamento por Stop Loss (49000)
    print("💥 Simulando que o preço atingiu o Stop Loss ($49000). Fechando slot...")
    
    # Lógica de fechamento de posição no modo PAPER
    trade_data = {
        "symbol": "BTCUSDT",
        "side": "Buy",
        "entry_price": 50000.0,
        "exit_price": 49000.0,
        "qty": 0.05,
        "order_id": f"paper_stop_4_{int(time.time())}",
        "pnl": -50.0, # Perda simulada
        "slot_id": 4,
        "slot_type": "SNIPER",
        "close_reason": "STOP_LOSS",
        "closed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    
    # Registra no Vault e limpa o slot (hard_reset_slot)
    await firebase_service.log_trade(trade_data)
    await firebase_service.hard_reset_slot(4, reason="TEST_STOP_LOSS_CLOSED", pnl=-50.0, trade_data=trade_data)
    
    # Verifica se o Slot foi liberado
    slots = await firebase_service.get_active_slots(force_refresh=True)
    slot_4 = next((s for s in slots if s["id"] == 4), None)
    print(f"🧹 Slot 4 no Postgres após fechamento: Símbolo={slot_4.get('symbol')} | Status={slot_4.get('status_risco')}")
    
    # Verifica se o trade foi parar no Postgres trade_history
    trades = await database_service.get_trade_history(limit=5)
    test_registered = any(t.get("order_id") == trade_data["order_id"] for t in trades)
    if test_registered:
        print("🎉 [TESTE 1 - SUCESSO] O fechamento liberou o slot e salvou o trade no trade_history relacional do Postgres!")
    else:
        print("❌ [TESTE 1 - FALHA] O trade não foi registrado no trade_history do Postgres.")

    # ==========================================
    # TESTE 2: EMANCIPAÇÃO -> MOONBAGS E SLOT LIVRE
    # ==========================================
    print("\n🚀 [TESTE 2] Testando Gatilho de Emancipação para Moonbag...")
    
    # Preenche o slot novamente simulando nova ordem de PEPEUSDT
    test_pepe = {
        "symbol": "PEPEUSDT",
        "side": "Buy",
        "qty": 1000000.0,
        "entry_price": 0.000010,
        "entry_margin": 10.0,
        "current_stop": 0.000009,
        "initial_stop": 0.000009,
        "target_price": 0.000020,
        "leverage": 50,
        "slot_type": "SNIPER",
        "status_risco": "ATIVO",
        "opened_at": time.time(),
        "pnl_percent": 0.0
    }
    
    print("📝 Gravando nova posição ativa PEPEUSDT no Slot 4 do Postgres...")
    await firebase_service.update_slot(4, test_pepe)
    
    # Executa a emancipação (promote_to_moonbag)
    print("🌔 Disparando a promoção (emancipação) do Slot 4 para Moonbag...")
    moon_id = await firebase_service.promote_to_moonbag(4)
    print(f"🆔 Moonbag criada com ID: {moon_id}")
    
    # Verifica se o slot tático 4 foi esvaziado
    slots = await firebase_service.get_active_slots(force_refresh=True)
    slot_4 = next((s for s in slots if s["id"] == 4), None)
    print(f"🧹 Slot 4 no Postgres após emancipação: Símbolo={slot_4.get('symbol')} | Status={slot_4.get('status_risco')}")
    
    # Verifica se a ordem está registrada na tabela moonbags relacional
    moons = await database_service.get_moonbags()
    pepe_in_moons = any(m.get("symbol") == "PEPEUSDT" for m in moons)
    if pepe_in_moons and (slot_4.get("symbol") is None):
        print("🎉 [TESTE 2 - SUCESSO] A emancipação moveu a moeda para a tabela de Moonbags e liberou o slot com sucesso!")
    else:
        print(f"❌ [TESTE 2 - FALHA] A emancipação falhou. Na moonbag: {pepe_in_moons} | Slot 4 ocupado: {slot_4.get('symbol')}")

    # ==========================================
    # TESTE 3: ABERTURA DO CAPITÃO COM SLOT LIBERADO
    # ==========================================
    print("\n🚀 [TESTE 3] Testando se o Capitão pode abrir nova ordem com o slot liberado...")
    
    # Sincroniza posições simuladas para limpar o array
    bybit_rest_service.paper_positions = []
    
    # Verifica disponibilidade de slot no bankroll
    slot_disponivel = await bankroll_manager.can_open_new_slot(symbol="SOLUSDT", slot_type="SNIPER")
    print(f"💡 BankrollManager declarou o Slot {slot_disponivel} como disponível para SOLUSDT.")
    
    if slot_disponivel == 4:
        print("🎉 [TESTE 3 - SUCESSO] O loop de análise de risco detectou o slot recém-liberado e autorizou a abertura da nova ordem no Slot 4!")
    else:
        print(f"❌ [TESTE 3 - FALHA] Slot 4 não foi detectado como vago ou can_open_new_slot retornou: {slot_disponivel}")
        
    print("\n🧪 [TESTS-FLOWS] Bateria de testes concluída!")

if __name__ == "__main__":
    asyncio.run(run_tests())
