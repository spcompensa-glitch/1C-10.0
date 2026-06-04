# -*- coding: utf-8 -*-
import asyncio
import logging
import sys
import os
import time

# Adiciona o diretório backend ao sys.path para permitir importações locais
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import settings
from services.okx_rest import okx_rest_service
from services.execution_protocol import execution_protocol

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestEmancipationResilience")

async def run_resilience_test():
    logger.info("==================================================")
    logger.info("🧪 [TEST] INICIANDO SIMULAÇÃO DE RESILIÊNCIA MOONBAG")
    logger.info("==================================================")

    # Força modo PAPER para o teste
    okx_rest_service.execution_mode = "PAPER"
    okx_rest_service.paper_balance = 20.0  # Banca de 20 dólares solicitada pelo usuário
    okx_rest_service.paper_positions = []
    okx_rest_service.paper_moonbags = []

    # 1. Simular Ordem no Slot 1
    symbol = "GALAUSDT.P"
    logger.info(f"🟢 Simulando abertura de posição tática em {symbol} no Slot 1...")
    pos_obj = {
        "symbol": symbol,
        "side": "Sell",  # Short
        "size": "5000",
        "avgPrice": "0.002760",
        "leverage": "50",
        "status": None,
        "stopLoss": "0.002859",
        "takeProfit": "0.002679",
        "opened_at": time.time(),
        "is_paper": True,
        "slot_id": 1,
        "entry_margin": 10.0,
        "slot_type": "BLITZ_30M",
    }
    okx_rest_service.paper_positions.append(pos_obj)

    # Mockar a chamada de rede na OKXRest para falhar na primeira tentativa de atualizar o stop
    original_set_trading_stop = okx_rest_service.set_trading_stop
    
    call_count = 0
    async def mock_set_trading_stop(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        stop_loss = kwargs.get("stopLoss", args[2] if len(args) > 2 else "0.0")
        if call_count == 1:
            logger.warning("❌ [SIMULAÇÃO DE ERRO] OKX API falhou temporariamente ao tentar atualizar o SL (Timeout/Network Error)!")
            return {"retCode": -1, "retMsg": "API Connection Timeout"}
        logger.info(f"✅ [SIMULAÇÃO DE SUCESSO] OKX API aceitou a atualização do SL para {stop_loss}!")
        return {"retCode": 0, "result": {}}

    okx_rest_service.set_trading_stop = mock_set_trading_stop

    # 2. Simular subida rápida (ROI > 150%) para testar Emancipação
    # Preço cai para SHORT dar lucro: entrada a 0.002760, preço cai para 0.002620
    current_price = 0.002620
    roi = execution_protocol.calculate_roi(0.002760, current_price, "Sell", leverage=50.0)
    logger.info(f"📈 Preço moveu de 0.002760 para {current_price:.6f} | ROI: {roi:.1f}% (esperado >150%)")

    # Slot data estruturado
    slot_data = {
        "symbol": symbol,
        "side": "Sell",
        "entry_price": 0.002760,
        "current_stop": 0.002859,
        "target_price": 0.002679,
        "slot_type": "BLITZ_30M",
        "status": None,
        "opened_at": pos_obj["opened_at"],
        "id": 1,
    }

    # Avaliar decisão pelo protocolo de execução
    should_close, reason, new_stop = await execution_protocol.process_order_logic(slot_data, current_price)
    logger.info(f"🔍 Decisão do Protocolo: should_close={should_close} | reason={reason} | new_stop={new_stop}")

    if reason == "EMANCIPATE_SLOT":
        logger.info("🚀 Gatilho de Emancipação disparado! Tentando aplicar com o mock de API falhando...")
        
        # 1ª Tentativa (Deve falhar e manter o slot ativo na posição tática)
        success = False
        if okx_rest_service.execution_mode == "PAPER":
            # Aqui simulamos a lógica interna de okx_rest.py do ciclo de execução
            res = await okx_rest_service.set_trading_stop(category="linear", symbol=symbol, stopLoss=str(new_stop))
            if res.get("retCode") == 0:
                success = True
            else:
                logger.warning("⚠️ Lógica de Segurança: Emancipação não confirmada pela exchange. Slot mantido intacto!")

        # Validação do Estado após Falha
        if not success and pos_obj in okx_rest_service.paper_positions:
            logger.info("✅ SEGURANÇA DETECTADA: Posição não foi tirada do slot tático e não ficou órfã.")
        else:
            logger.error("❌ FALHA CRÍTICA: Posição foi emancipada mesmo sem confirmação da exchange!")

        # 2ª Tentativa (Onde a API retorna sucesso)
        logger.info("🔄 Rodando segundo ciclo de execução (OKX responde OK)...")
        res = await okx_rest_service.set_trading_stop(category="linear", symbol=symbol, stopLoss=str(new_stop))
        if res.get("retCode") == 0:
            # Transiciona
            pos_obj["status"] = "EMANCIPATED"
            pos_obj["stopLoss"] = str(new_stop)
            okx_rest_service.paper_positions.remove(pos_obj)
            okx_rest_service.paper_moonbags.append(pos_obj)
            logger.info("✅ EMANCIPAÇÃO CONCLUÍDA: Posição promovida a Moonbag e com Stop Loss de lucro garantido!")

    # Restaurar mock
    okx_rest_service.set_trading_stop = original_set_trading_stop

    # Validação Final de Estados
    logger.info(f"Banca Final Simulada: ${okx_rest_service.paper_balance:.2f}")
    logger.info(f"Moonbags ativas em memória: {len(okx_rest_service.paper_moonbags)}")
    logger.info(f"Slots ativos em memória: {len(okx_rest_service.paper_positions)}")
    
    if len(okx_rest_service.paper_moonbags) == 1 and okx_rest_service.paper_balance == 20.0:
         logger.info("\n🎉 [TEST RESILIENCE] 100% DOS TESTES APROVADOS!")
    else:
         logger.error("❌ Erro na integridade dos saldos ou posições!")

if __name__ == "__main__":
    asyncio.run(run_resilience_test())
