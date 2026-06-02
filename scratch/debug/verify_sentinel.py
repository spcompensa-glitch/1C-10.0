import sys
import codecs
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import asyncio
import time
import os

# Adiciona o diretório backend ao path do python
sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))

from services.sentinel_auditor import sentinel_auditor
from services.okx_rest import okx_rest_service
from services.firebase_service import firebase_service
from services.bankroll import bankroll_manager

async def run_tests():
    print("🛡️ [VERIFY-SENTINEL] Iniciando testes de Auto-Cura do Sentinel Auditor...")

    # Garante que o motor está em modo PAPER para os testes seguros
    okx_rest_service.execution_mode = "PAPER"
    print(f"📍 Modo de Execução: {okx_rest_service.execution_mode}")

    # Limpa estados anteriores
    okx_rest_service.paper_positions.clear()
    okx_rest_service.paper_moonbags.clear()
    for i in range(1, 5):
        await firebase_service.hard_reset_slot(i, reason="Sentinel Test Clean")

    print("\n--- 🔴 CENÁRIO A: POSIÇÃO ÓRFÃ NA EXCHANGE (Exchange Ativa, Banco Vazio) ---")
    # Registra sinal legítimo no buffer de sinais para simular órfão de robô
    await firebase_service.log_signal({
        "symbol": "BTCUSDT",
        "side": "Buy",
        "action": "ENTRY"
    })

    # Simula posição aberta na Exchange/RAM com o Genesis ID carimbado
    fake_pos_a = {
        "symbol": "BTCUSDT",
        "side": "Buy",
        "size": "0.05",
        "avgPrice": "68000.0",
        "leverage": "50",
        "stopLoss": "66000.0",
        "takeProfit": "72000.0",
        "status": "ATIVO",
        "genesis_id": "TEST-BTC-GENESIS",
        "opened_at": time.time() - 30.0 # Passou do grace period
    }
    okx_rest_service.paper_positions.append(fake_pos_a)
    print(f"Exchange/Paper RAM ativa: {fake_pos_a['symbol']} | Qty: {fake_pos_a['size']} | Entry: ${fake_pos_a['avgPrice']} | Genesis ID: TEST-BTC-GENESIS")

    # Verifica se os slots no banco estão limpos
    slots_antes = await firebase_service.get_active_slots(force_refresh=True)
    occupied_antes = [s for s in slots_antes if s.get("symbol")]
    print(f"Slots ativos no banco antes: {len(occupied_antes)}")

    # Executa a reconciliação do Sentinela
    print("⏳ Executando reconciliação...")
    await sentinel_auditor.reconcile()

    # Verifica se o Sentinela adotou a posição no banco
    slots_depois = await firebase_service.get_active_slots(force_refresh=True)
    occupied_depois = [s for s in slots_depois if s.get("symbol")]
    print(f"Slots ativos no banco depois: {len(occupied_depois)}")
    
    adopted_slot = next((s for s in slots_depois if okx_rest_service._strip_p(s.get("symbol")).upper() == "BTCUSDT"), None)
    if adopted_slot:
        print(f"✅ CENÁRIO A SUCESSO: Posição adotada no Slot {adopted_slot['id']} com entry_price=${adopted_slot['entry_price']}!")
    else:
        print("❌ CENÁRIO A FALHA: Posição órfã não foi adotada pelo Sentinela!")
        sys.exit(1)


    print("\n--- 🔴 CENÁRIO B: POSIÇÃO ÓRFÃ NO BANCO (Exchange Vazia, Banco com Slot Ativo) ---")
    # Limpa RAM e simula slot ativo no Firestore
    okx_rest_service.paper_positions.clear()
    okx_rest_service.paper_moonbags.clear()
    
    await firebase_service.update_slot(2, {
        "symbol": "ETHUSDT.P",
        "side": "Sell",
        "qty": 1.5,
        "entry_price": 3500.0,
        "entry_margin": 10.0,
        "current_stop": 3600.0,
        "genesis_id": "TEST-ORPHAN-BANK",
        "status_risco": "ATIVO",
        "opened_at": time.time() - 30.0 # Passou do grace period
    })
    print(f"Slot 2 ativo no banco: ETHUSDT.P | Entry: $3500.0 (Exchange vazia)")

    # Executa reconciliação
    print("⏳ Executando reconciliação...")
    await sentinel_auditor.reconcile()

    # Verifica se o Slot foi purgado pelo Sentinela
    slots_b_depois = await firebase_service.get_active_slots(force_refresh=True)
    slot_eth = slots_b_depois[1] # slot 2
    if not slot_eth.get("symbol"):
        print("✅ CENÁRIO B SUCESSO: Slot órfão no banco foi purgado e liberado deterministicamente!")
    else:
        print(f"❌ CENÁRIO B FALHA: Slot continua ativo: {slot_eth.get('symbol')}!")
        sys.exit(1)


    print("\n--- 🔴 CENÁRIO C: INCONSISTÊNCIA CRÍTICA - ORDEM FANTASMA NA OKX (Ativos Diferentes, Sem Gênese) ---")
    # Slot 3 tem SOL, mas RAM tem ADA associada ao Slot 3 (sem sinal histórico legítimo = Fantasma)
    await firebase_service.update_slot(3, {
        "symbol": "SOLUSDT.P",
        "side": "Buy",
        "qty": 10.0,
        "entry_price": 150.0,
        "entry_margin": 30.0,
        "current_stop": 140.0,
        "genesis_id": "TEST-SOL-GENESIS",
        "status_risco": "ATIVO",
        "opened_at": time.time() - 30.0
    })

    # Posição na RAM é ADA no slot 3
    ghost_pos = {
        "symbol": "ADAUSDT",
        "side": "Buy",
        "size": "100.0",
        "avgPrice": "0.50",
        "leverage": "50",
        "stopLoss": "0.45",
        "takeProfit": "0.60",
        "status": "ATIVO",
        "slot_id": 3,
        "opened_at": time.time() - 30.0
    }
    okx_rest_service.paper_positions.append(ghost_pos)
    print(f"Slot 3 no Banco: SOLUSDT.P")
    print(f"Posição física (RAM) no Slot 3: ADAUSDT (Sem carimbo de origem = FANTASMA)")

    # Executa reconciliação
    print("⏳ Executando reconciliação...")
    await sentinel_auditor.reconcile()

    # Verifica se o Slot 3 foi purgado do banco
    slots_c_depois = await firebase_service.get_active_slots(force_refresh=True)
    slot_sol = slots_c_depois[2] # slot 3
    
    # Verifica se o Stop Loss de proteção passiva na RAM foi ajustado para o Break Even ou preço atual
    # Como o preço atual de ADA (fallbacks) é mockado em 0.0 se não houver rede, ela colocaria o SL na entrada/Break Even
    ada_pos = next((p for p in okx_rest_service.paper_positions if p["symbol"] == "ADAUSDT"), None)
    
    if not slot_sol.get("symbol") and ada_pos and float(ada_pos["stopLoss"]) != 0.45:
        print(f"✅ CENÁRIO C SUCESSO: Slot fantasma purgado do banco e Stop Loss de ADA corrigido preventivamente na exchange (${ada_pos['stopLoss']})!")
    else:
        print(f"❌ CENÁRIO C FALHA: Slot={slot_sol.get('symbol')} | ADA SL={ada_pos['stopLoss'] if ada_pos else 'POS_MISSING'}")
        sys.exit(1)


    print("\n--- 🔴 CENÁRIO D: INCONSISTÊNCIA CRÍTICA - ORDEM LEGÍTIMA (Ativos Diferentes, Com Gênese) ---")
    # Slot 4 tem SOL, mas RAM tem XRP associado ao Slot 4 (com carimbo de sinal histórico legítimo)
    await firebase_service.update_slot(4, {
        "symbol": "SOLUSDT.P",
        "side": "Buy",
        "qty": 10.0,
        "entry_price": 150.0,
        "entry_margin": 30.0,
        "current_stop": 140.0,
        "genesis_id": "TEST-XRP-GENESIS",
        "status_risco": "ATIVO",
        "opened_at": time.time() - 30.0
    })

    # Registra o genesis legítimo no banco de dados para XRP
    legit_pos = {
        "symbol": "XRPUSDT",
        "side": "Buy",
        "size": "500.0",
        "avgPrice": "0.60",
        "leverage": "50",
        "stopLoss": "0.55",
        "takeProfit": "0.75",
        "status": "ATIVO",
        "slot_id": 4,
        "genesis_id": "TEST-XRP-GENESIS",
        "opened_at": time.time() - 30.0
    }
    okx_rest_service.paper_positions.append(legit_pos)
    
    # Adiciona XRP no buffer de sinais recentes legítimos do Firebase
    await firebase_service.log_signal({
        "symbol": "XRPUSDT",
        "side": "Buy",
        "action": "ENTRY"
    })
    
    print(f"Slot 4 no Banco: SOLUSDT.P")
    print(f"Posição física (RAM) no Slot 4: XRPUSDT (Genesis ID TEST-XRP-GENESIS = LEGÍTIMO)")

    # Executa reconciliação
    print("⏳ Executando reconciliação...")
    await sentinel_auditor.reconcile()

    # Verifica se o Slot 4 no banco foi corrigido para o ativo físico XRP de forma autônoma
    slots_d_depois = await firebase_service.get_active_slots(force_refresh=True)
    slot_xrp = slots_d_depois[3] # slot 4

    if slot_xrp.get("symbol") == "XRPUSDT.P" and slot_xrp.get("entry_price") == 0.60:
        print(f"✅ CENÁRIO D SUCESSO: Slot no banco corrigido de forma autônoma para XRPUSDT.P com entry_price de ${slot_xrp['entry_price']}!")
    else:
        print(f"❌ CENÁRIO D FALHA: Slot={slot_xrp.get('symbol')} | entry={slot_xrp.get('entry_price')}")
        sys.exit(1)

    print("\n🎉 [VERIFY-SENTINEL] TODOS OS TESTES OPERACIONAIS DE AUTO-CURA PASSARAM COM SUCESSO DE FORMA DETERMINÍSTICA! 🛡️")

if __name__ == "__main__":
    asyncio.run(run_tests())
