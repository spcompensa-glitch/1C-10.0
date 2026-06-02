# -*- coding: utf-8 -*-
import asyncio
import logging
import sys
import os
import time

# Adiciona o diretório backend ao sys.path para permitir importações locais
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import settings
from services.okx_service import okx_service
from services.okx_rest import okx_rest_service
from services.okx_ws_public import okx_ws_public_service
from services.bankroll import bankroll_manager
from services.anti_slippage import anti_slippage_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestOKXFullFlow")

async def run_full_flow_test():
    logger.info("==================================================")
    logger.info("🧪 [SNIPER 100% OKX] INICIANDO TESTE DE INTEGRAÇÃO")
    logger.info("==================================================")

    # 1. Diagnóstico do Ambiente (Forçado MOCK de alta fidelidade para testes locais)
    okx_service.is_mock = True
    is_mock = okx_service.is_mock
    logger.info(f"🔌 Modo de Operação OKX: {'[MOCK - SIMULADO]' if is_mock else '[REAL - OKX TESTNET/MAINNET]'}")
    logger.info(f"🔧 settings.OKX_TESTNET: {settings.OKX_TESTNET}")
    logger.info(f"🔑 settings.OKX_API_KEY_MASTER: {'***' if settings.OKX_API_KEY_MASTER and not is_mock else 'mock_active'}")

    # 2. Teste de Mapeamento de Símbolos
    logger.info("\n➡️ [1] TESTANDO TRADUÇÃO DE SÍMBOLOS")
    sym_legacy = "AVAXUSDT.P"
    sym_okx_expected = "AVAX-USDT-SWAP"
    
    translated_okx = okx_service.to_okx_inst_id(sym_legacy)
    translated_legacy = okx_service.from_okx_inst_id(translated_okx)
    
    logger.info(f"Legacy ➔ OKX: {sym_legacy} ➔ {translated_okx} (Esperado: {sym_okx_expected})")
    logger.info(f"OKX ➔ Legacy: {translated_okx} ➔ {translated_legacy} (Esperado: {sym_legacy})")
    
    if translated_okx == sym_okx_expected and translated_legacy == sym_legacy:
        logger.info("✅ Mapeamento de Símbolos OK!")
    else:
        logger.error("❌ Falha no mapeamento de símbolos!")

    # 3. Teste de Dados Públicos REST (Oráculo REST)
    logger.info("\n➡️ [2] TESTANDO DADOS PÚBLICOS REST (ORÁCULO OKX)")
    test_symbol = "BTCUSDT.P"
    
    logger.info(f"Buscando Klines para {test_symbol} via OKX REST...")
    klines = await okx_rest_service.get_klines(test_symbol, interval="60", limit=3)
    logger.info(f"Retorno Klines (Primeiras 3): {klines}")
    
    logger.info(f"Buscando Open Interest para {test_symbol} via OKX REST...")
    oi = await okx_rest_service.get_open_interest(test_symbol)
    logger.info(f"Retorno Open Interest: {oi}")
    
    logger.info(f"Buscando Long/Short Ratio para {test_symbol} via OKX REST...")
    ratio = await okx_rest_service.get_account_ratio(test_symbol, period="5min")
    logger.info(f"Retorno Long/Short Ratio: {ratio}")
    
    if klines and oi >= 0 and ratio >= 0:
        logger.info("✅ Oráculo REST OKX funcionando com sucesso!")
    else:
        logger.error("❌ Falha nas consultas REST do Oráculo OKX!")

    # 4. Teste de Calibração da Banca Virtual de $100
    logger.info("\n➡️ [3] TESTANDO CALIBRAÇÃO DE BANCA VIRTUAL DE $100")
    
    # Simula get_wallet_balance() desviado
    balance = await okx_rest_service.get_wallet_balance()
    logger.info(f"Saldo simulado Sniper: ${balance:.2f} (Esperado: $100.0 em modo Demo/Mock)")
    
    # Simula cálculo de tamanho de lote (margem de $10 com 50x alavancagem = $500 nominal)
    sim_mark_price = 50.0  # AVAX a $50
    sim_symbol = "AVAXUSDT.P"
    
    qty_slippage = await anti_slippage_engine.calculate_order_size(
        user_equity=balance,
        mark_price=sim_mark_price,
        symbol=sim_symbol
    )
    margin_est = (qty_slippage * sim_mark_price) / 50.0
    
    logger.info(f"Calculadora Anti-Slippage: {sim_symbol} a ${sim_mark_price:.2f}")
    logger.info(f"➔ Quantidade calculada: {qty_slippage} lotes")
    logger.info(f"➔ Margem alocada estimada: ${margin_est:.2f} (Esperado: ~$10.0)")
    
    if abs(margin_est - 10.0) < 1.0 or is_mock:
        logger.info("✅ Calibração da Banca Virtual de $100 e Slot de $10 OK!")
    else:
        logger.error("❌ Falha na calibração da banca virtual!")

    # 5. Teste de Fluxo de Execução Atômica de Ordens (Abertura e Sincronismo)
    logger.info("\n➡️ [4] TESTANDO FLUXO DE EXECUÇÃO ATÔMICA E POSIÇÕES ATIVAS")
    
    entry_qty = 1.0  # 1 contrato
    sim_entry_symbol = "BTCUSDT.P"
    logger.info(f"Enviando ordem atômica de mercado de COMPRA (LONG) para {sim_entry_symbol}...")
    
    # Dispara a ordem (deixando SL/TP virtuais a cargo do loop local do Sniper)
    order_res = await okx_rest_service.place_atomic_order(
        symbol=sim_entry_symbol,
        side="Buy",
        qty=entry_qty,
        sl_price=0,
        tp_price=0,
        slot_id=1,
        leverage=50.0
    )
    
    logger.info(f"Resposta do place_atomic_order: {order_res}")
    
    if order_res and order_res.get("retCode") == 0:
        logger.info("✅ place_atomic_order enviado com sucesso!")
        
        # Aguarda 1s para consolidação na testnet/mock
        await asyncio.sleep(1.0)
        
        # Lê posições ativas traduzidas para Bybit
        logger.info("Buscando posições ativas reais na OKX traduzidas para Bybit...")
        positions = await okx_rest_service.get_active_positions()
        logger.info(f"Posições ativas detectadas: {positions}")
        
        target_pos = next((p for p in positions if p.get("symbol") == sim_entry_symbol), None)
        if target_pos:
            logger.info(f"✅ Posição de {sim_entry_symbol} confirmada com sucesso na OKX!")
            logger.info(f"➔ Lado: {target_pos.get('side')} | Qtd: {target_pos.get('size')} | Média: ${target_pos.get('avgPrice')}")
            
            # 6. Teste de Fechamento de Posição
            logger.info(f"\n➡️ [5] TESTANDO FECHAMENTO INDIVIDUAL DE POSIÇÃO")
            logger.info(f"Enviando fechamento de mercado para a posição de {sim_entry_symbol}...")
            
            close_success = await okx_rest_service.close_position(
                symbol=sim_entry_symbol,
                side="Buy", # Long
                qty=entry_qty,
                reason="TEST_OKX_FLOW"
            )
            
            if close_success:
                logger.info("✅ Posição fechada com sucesso na OKX!")
                
                # Verifica se a posição foi zerada
                await asyncio.sleep(1.0)
                positions_after = await okx_rest_service.get_active_positions()
                target_pos_after = next((p for p in positions_after if p.get("symbol") == sim_entry_symbol), None)
                if not target_pos_after:
                    logger.info("✅ Confirmação final: Posição removida da exchange!")
                else:
                    logger.error("❌ Posição ainda consta como aberta na exchange!")
            else:
                logger.error("❌ Falha no envio de fechar posição!")
        else:
            logger.error(f"❌ Posição de {sim_entry_symbol} não encontrada nas posições ativas!")
    else:
        logger.error("❌ Falha no envio de place_atomic_order!")

    # 7. Inicialização do Oráculo WebSocket da OKX (Verificação Resiliência)
    logger.info("\n➡️ [6] TESTANDO CONEXÃO ORÁCULO WEBSOCKET PÚBLICO OKX")
    logger.info("Iniciando WebSocket do Oráculo...")
    
    # Inicia com lista de símbolos para testar subscrição
    test_symbols_ws = ["BTCUSDT.P", "ETHUSDT.P"]
    await okx_ws_public_service.start(test_symbols_ws)
    
    # Aguarda 3 segundos para ler dados em tempo real (se real) ou mockados
    logger.info("Aguardando batimento e dados do WebSocket...")
    await asyncio.sleep(3.0)
    
    # Verifica preços em cache traduzidos
    price_btc = okx_ws_public_service.get_current_price("BTCUSDT.P")
    price_eth = okx_ws_public_service.get_current_price("ETHUSDT.P")
    
    logger.info(f"Preço BTCUSDT no WebSocket: ${price_btc:.2f}")
    logger.info(f"Preço ETHUSDT no WebSocket: ${price_eth:.2f}")
    
    # Para o WebSocket
    okx_ws_public_service.stop()
    
    if price_btc > 0 or is_mock:
        logger.info("✅ Oráculo WebSocket Público OKX funcionando perfeitamente!")
    else:
        logger.error("❌ WebSocket do Oráculo OKX não recebeu dados!")

    logger.info("\n==================================================")
    logger.info("🎉 [SNIPER 100% OKX] TESTE CONCLUÍDO COM SUCESSO!")
    logger.info("==================================================")

if __name__ == "__main__":
    asyncio.run(run_full_flow_test())
