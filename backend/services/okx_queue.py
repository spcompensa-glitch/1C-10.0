# -*- coding: utf-8 -*-
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from config import settings
from services.okx_service import okx_service

logger = logging.getLogger("OKXCommandQueue")

class OKXCommandQueue:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.is_running = False
        self._processor_task: Optional[asyncio.Task] = None
        self.loop_interval = 0.25  # Roda a cada 250ms
        self.cooldown_until = 0.0
        self.error_streak = 0
        self.execution_mode = settings.OKX_EXECUTION_MODE

    def start(self):
        """Inicia a fila de processamento em segundo plano."""
        if self.is_running:
            return
        self.is_running = True
        self._processor_task = asyncio.create_task(self._process_queue_loop())
        logger.info("⚡ [OKX-QUEUE] Fila de Comandos OKX Iniciada.")

    async def stop(self):
        """Para a fila de processamento."""
        self.is_running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        logger.info("⚡ [OKX-QUEUE] Fila de Comandos OKX Parada.")

    async def enqueue_stop_update(
        self,
        symbol: str,
        side: str,
        sl_price: float,
        qty: float,
        slot_id: Optional[int] = None,
        moon_uuid: Optional[str] = None
    ):
        """Enfileira um comando de atualização de stop loss."""
        item = {
            "type": "STOP_UPDATE",
            "symbol": symbol,
            "side": side,
            "sl_price": sl_price,
            "qty": qty,
            "slot_id": slot_id,
            "moon_uuid": moon_uuid,
            "timestamp": time.time(),
            "retry_count": 0
        }
        await self.queue.put(item)
        logger.debug(f"[OKX-QUEUE] Enfileirado Stop para {symbol} em ${sl_price:.4f}")

    async def _process_queue_loop(self):
        while self.is_running:
            try:
                now = time.time()
                if now < self.cooldown_until:
                    await asyncio.sleep(self.loop_interval)
                    continue

                if self.queue.empty():
                    await asyncio.sleep(self.loop_interval)
                    continue

                # Consome os itens disponíveis na fila
                batch_items = []
                while not self.queue.empty() and len(batch_items) < 10:
                    batch_items.append(await self.queue.get())

                if not batch_items:
                    continue

                if self.execution_mode == "PAPER":
                    await self._process_paper_batch(batch_items)
                else:
                    await self._process_real_batch(batch_items)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[OKX-QUEUE] Erro no loop de processamento: {e}", exc_info=True)
                await asyncio.sleep(1.0)

    async def _process_paper_batch(self, items: List[Dict[str, Any]]):
        """Processamento em modo Simulação (PAPER) - apenas atualiza o estado local."""
        from services.okx_rest import okx_rest_service
        for item in items:
            symbol = item["symbol"]
            sl_price = item["sl_price"]
            # Apenas simula a chamada set_trading_stop local
            await okx_rest_service.set_trading_stop(
                category="linear",
                symbol=symbol,
                stopLoss=str(sl_price),
                side=item["side"]
            )
            self.queue.task_done()

    async def _process_real_batch(self, items: List[Dict[str, Any]]):
        """Processamento em modo Real (REAL) - interage diretamente com a OKX em lote."""
        # 1. Agrupar por símbolo (pegar sempre a atualização de stop mais recente para evitar requests redundantes)
        latest_updates = {}
        for item in items:
            key = (item["symbol"], item["side"])
            if key not in latest_updates or item["timestamp"] > latest_updates[key]["timestamp"]:
                latest_updates[key] = item

        # 2. Processar cada ativo
        amends_list = []
        places_list = []
        failed_items = []

        for key, item in latest_updates.items():
            symbol, side = key
            sl_price = item["sl_price"]
            qty = item["qty"]

            try:
                # Busca as algo ordens ativas para esse símbolo na OKX
                pending_algos = await okx_service.get_pending_algo_orders(symbol)
                
                # Procura a algo order de Stop Loss (geralmente ordType = conditional ou trigger)
                sl_algo = None
                for algo in pending_algos:
                    # Verifica se é uma conditional/trigger order relacionada à nossa posição
                    if algo.get("ordType") == "conditional" or "slTriggerPx" in algo:
                        sl_algo = algo
                        break

                inst_id = okx_service.to_okx_inst_id(symbol)

                if sl_algo:
                    algo_id = sl_algo["algoId"]
                    amends_list.append({
                        "algoId": algo_id,
                        "instId": inst_id,
                        "newSlTriggerPx": f"{sl_price:.8f}".rstrip('0').rstrip('.')
                    })
                else:
                    # Se não encontrou nenhuma algo order ativa, precisaremos colocar uma nova
                    places_list.append(item)

            except Exception as e:
                logger.error(f"[OKX-QUEUE] Falha ao auditar pendências para {symbol}: {e}")
                failed_items.append(item)

        # 3. Executa as modificações em lote (POST /api/v5/trade/amend-algos)
        if amends_list:
            try:
                response = await okx_service.amend_batch_algo_orders(amends_list)
                code = response.get("code")
                
                if code == "0":
                    logger.info(f"🛡️ [OKX-QUEUE] Modificados {len(amends_list)} stops com sucesso na OKX.")
                    self.error_streak = 0
                elif code == "429":
                    # Ativa cooldown 429
                    self.error_streak = min(self.error_streak + 1, 5)
                    cooldown = 2.0 * self.error_streak
                    self.cooldown_until = time.time() + cooldown
                    logger.warning(f"⚠️ [OKX-QUEUE] OKX limitou (429). Cooldown de {cooldown:.1f}s.")
                    
                    # Devolve para a fila os itens que estavam nesse lote
                    for item in latest_updates.values():
                        if any(a["instId"] == okx_service.to_okx_inst_id(item["symbol"]) for a in amends_list):
                            item["retry_count"] += 1
                            if item["retry_count"] < 5:
                                await self.queue.put(item)
                else:
                    logger.error(f"❌ [OKX-QUEUE] Erro no lote de modificações OKX: {response.get('msg')}")
                    # Para outros erros, tentamos colocar novos stops individuais (pode ser que as algo orders expiraram)
                    for item in latest_updates.values():
                        if any(a["instId"] == okx_service.to_okx_inst_id(item["symbol"]) for a in amends_list):
                            places_list.append(item)

            except Exception as e:
                logger.error(f"[OKX-QUEUE] Falha crítica no envio do lote amend: {e}")
                # Devolve para fila
                for item in latest_updates.values():
                    if any(a["instId"] == okx_service.to_okx_inst_id(item["symbol"]) for a in amends_list):
                        await self.queue.put(item)

        # 4. Executa novas colocações de algo orders pendentes (individuais para evitar misturar fluxo)
        for item in places_list:
            symbol = item["symbol"]
            side = item["side"]
            sl_price = item["sl_price"]
            qty = item["qty"]

            try:
                response = await okx_service.place_algo_order(
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    sl_price=sl_price
                )
                if response.get("code") == "0":
                    logger.info(f"🛡️ [OKX-QUEUE] Colocado novo stop loss condicional para {symbol} a ${sl_price:.4f}.")
                else:
                    logger.error(f"❌ [OKX-QUEUE] Falha ao colocar stop condicional para {symbol}: {response.get('msg')}")
            except Exception as e:
                logger.error(f"[OKX-QUEUE] Falha crítica ao colocar stop para {symbol}: {e}")

        # Finaliza o lote na fila principal
        for _ in range(len(items)):
            self.queue.task_done()

# Instanciação global
okx_command_queue = OKXCommandQueue()
