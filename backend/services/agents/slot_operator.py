import asyncio
import logging
import time
from typing import Optional, Dict, Any

from config import settings
from services.agents.aios_adapter import AIOSAgent
from services.database_service import database_service
from services.okx_rest import OKXRest as OKXRest
from services.okx_ws_public import okx_ws_public_service

logger = logging.getLogger("SlotOperator")

class SlotOperatorAgent(AIOSAgent):
    """
    Agente Autônomo responsável pela gestão do ciclo de vida de UM slot tático.
    Implementa a lógica de Stop Loss dinâmico (Escadinha) e emancipação para Moonbag.
    """
    def __init__(self, slot_id: int):
        super().__init__(
            agent_id=f"slot_operator_{slot_id}",
            role="slot_operator",
            capabilities=["slot_lifecycle_management", "stop_loss_escalation", "emancipation"]
        )
        self.slot_id = slot_id
        self.okx_rest = OKXRest()
        self.loop_interval = 3.0  # Executar a cada 3 segundos
        self._task = None
        self.is_running = False

    async def on_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        try:
            msg_type = message.get("type")
            data = message.get("data", {})
            if msg_type == "GET_STATUS":
                slot = await database_service.get_slot(self.slot_id)
                return {"status": "SUCCESS", "data": slot}
            return {"status": "ERROR", "message": f"Unknown message type: {msg_type}"}
        except Exception as e:
            logger.error(f"SlotOperator-{self.slot_id} on_message Error: {e}")
            return {"status": "ERROR", "message": str(e)}

    async def start(self):
        """Inicia o loop principal do SlotOperator."""
        if self.is_running:
            return
        
        # Garante a inicialização da OKXRest e Database
        if not self.okx_rest.is_initialized:
            await self.okx_rest.initialize()
        if not database_service.is_active:
            await database_service.initialize()
            
        self.is_running = True
        self._task = asyncio.create_task(self._main_loop())

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
        logger.info(f"🤖 [SlotOperator-{self.slot_id}] Parado.")

    async def _main_loop(self):
        while self.is_running:
            try:
                await self._process_slot()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [SlotOperator-{self.slot_id}] Erro no main loop: {e}")
            await asyncio.sleep(self.loop_interval)

    async def _process_slot(self):
        # 1. Leitura do slot no Postgres
        slot = await database_service.get_slot(self.slot_id)
        if not slot or not slot.get("symbol"):
            return  # Slot livre

        symbol = slot["symbol"]
        entry_price = float(slot.get("entry_price", 0))
        current_stop = float(slot.get("current_stop", 0))
        side = slot.get("side", "BUY")
        qty = float(slot.get("qty", 0))
        
        if entry_price <= 0:
            return

        # 2. Obter preço atual em tempo real (WS com fallback REST)
        current_price = await self._get_current_price(symbol)
        if current_price <= 0:
            return

        # [OKX-TESTNET] Failsafe: Stop Loss Virtual Ativo
        # Se o stop estiver configurado no banco e o preço violar esse limite,
        # fechamos imediatamente a mercado para garantir a proteção da banca.
        if settings.OKX_API_KEY_MASTER and current_stop > 0:
            is_stop_violated = False
            if side.upper() == "BUY" and current_price <= current_stop:
                is_stop_violated = True
                reason_sl = "STOP_LOSS_VIRTUAL_BUY"
            elif side.upper() == "SELL" and current_price >= current_stop:
                is_stop_violated = True
                reason_sl = "STOP_LOSS_VIRTUAL_SELL"
                
            if is_stop_violated:
                logger.critical(f"💥 [STOP-VIRTUAL-{self.slot_id}] {symbol} violou Stop Loss ({current_stop:.4f}) a {current_price:.4f}! Disparando fechamento imediato na OKX...")
                # Fecha a posição na OKX via okx_rest
                await self.okx_rest.close_position(symbol, side, qty, reason=reason_sl)
                
                # [HERMES TELEGRAM] Alerta de Fechamento (SL)
                try:
                    from services.telegram_service import telegram_service
                    await telegram_service.send_message(f"🔒 <b>ORDEM FECHADA</b>\nPar: {symbol}\nMotivo: {reason_sl}\nPnL: {self.current_pnl:.2f}%")
                except:
                    pass
                # Reseta o slot local no banco
                await database_service.update_slot(self.slot_id, {
                    "symbol": None, "entry_price": 0, "current_stop": 0, "qty": 0, "pnl_percent": 0
                })
                return

        # 3. Calcular ROI em tempo real (assumindo alavancagem 50x padrão para sniper)
        leverage = 50.0
        if side.upper() == "BUY":
            price_diff_pct = (current_price - entry_price) / entry_price
        else:
            price_diff_pct = (entry_price - current_price) / entry_price
            
        roi_percent = price_diff_pct * leverage * 100

        # Atualiza o PNL do slot no banco
        if abs((slot.get("pnl_percent") or 0) - roi_percent) > 1.0:
             await database_service.update_slot(self.slot_id, {"pnl_percent": roi_percent})

        # Flash is now the single writer for stop progression and emancipation.
        # SlotOperator keeps slot observation/failsafe behavior only.
        return

        # 4. Escadinha de Stop Loss (Smart SL)
        new_stop_roi = self._calculate_escadinha_stop(roi_percent)

        # [V123] Mapeamento de status_risco para a UI (badge do card)
        status_risco = self._get_status_risco(roi_percent)

        if new_stop_roi is not None:
            # Calcular novo preço de stop
            price_offset_pct = new_stop_roi / (leverage * 100)
            if side.upper() == "BUY":
                new_stop_price = entry_price * (1 + price_offset_pct)
            else:
                new_stop_price = entry_price * (1 - price_offset_pct)

            # Formatar precisão (evitar erro de API OKX)
            new_stop_price = await self.okx_rest.format_precision(symbol, new_stop_price)

            # Só atualiza se o stop melhorou
            should_update = False
            if side.upper() == "BUY" and (current_stop == 0 or new_stop_price > current_stop):
                should_update = True
            elif side.upper() == "SELL" and (current_stop == 0 or new_stop_price < current_stop):
                should_update = True

            if should_update:
                logger.info(f"🛡️ [SlotOperator-{self.slot_id}] {symbol} ROI={roi_percent:.1f}% -> SL: +{new_stop_roi}% (${new_stop_price:.4f}) | Status: {status_risco}")
                await self._update_stop_loss(symbol, side, new_stop_price, self.slot_id, qty)
                # [V123] Atualiza current_stop + status_risco juntos (Postgres + Firebase)
                update_payload = {"current_stop": new_stop_price, "status_risco": status_risco}
                await database_service.update_slot(self.slot_id, update_payload)
                try:
                    from services.firebase_service import firebase_service
                    slot_state = await firebase_service.get_slot(self.slot_id)
                    if slot_state and slot_state.get("symbol"):
                        await firebase_service.update_slot(self.slot_id, {"current_stop": new_stop_price, "status_risco": status_risco})
                except Exception as fb_err:
                    logger.warning(f"⚠️ [SlotOperator-{self.slot_id}] Firebase update falhou (não crítico): {fb_err}")
        else:
            # Mesmo sem avanço de escadinha, sincroniza o status_risco se necessário
            current_status = slot.get("status_risco", "MONITORANDO")
            if current_status != status_risco and status_risco == "MONITORANDO":
                pass  # Não regride o status se já avançou

        # 5. Verificação de Emancipação para Moonbag (ROI >= 150%)
        if roi_percent >= 150.0:
            logger.warning(f"🚀 [SlotOperator-{self.slot_id}] {symbol} EMANCIPADO! ROI atingiu {roi_percent:.1f}%. Movendo para Moonbag...")
            try:
                # Disparar evidência visual (se disponível)
                from services.agents.vision_agent import vision_agent
                if vision_agent:
                    asyncio.create_task(vision_agent.capture_evidence(symbol, "EMANCIPATION", f"ROI: {roi_percent:.1f}%"))
            except Exception as e:
                logger.warning(f"⚠️ [SlotOperator-{self.slot_id}] Erro no vision_agent: {e}")
                
            # Promover para Moonbag e liberar o slot
            await database_service.promote_to_moonbag(self.slot_id)
            await database_service.update_slot(self.slot_id, {
                "symbol": None, "entry_price": 0, "current_stop": 0, "qty": 0, "pnl_percent": 0
            })

    async def _get_current_price(self, symbol: str) -> float:
        """Obtém o preço do WS, com fallback para REST."""
        try:
            price = getattr(okx_ws_public_service, 'get_current_price', lambda s: 0.0)(symbol)
            if price > 0:
                return price
        except Exception:
            pass
            
        # Fallback para REST
        try:
            ticker = await self.okx_rest.get_tickers(symbol)
            if ticker and ticker.get("result", {}).get("list"):
                return float(ticker["result"]["list"][0].get("lastPrice", 0))
        except Exception as e:
            logger.error(f"Erro obtendo preço REST para {symbol}: {e}")
        return 0.0

    def _calculate_escadinha_stop(self, roi: float) -> Optional[float]:
        """
        Calcula o novo nível de Stop Loss em ROI% baseado na Escadinha.
        - ROI >= 30% -> SL movido para +6% (Break-Even)
        - ROI >= 50% -> SL movido para +25% (Profit Bridge)
        - ROI >= 70% -> SL movido para +45% (Risk Zero)
        - ROI >= 110% -> SL movido para +80% (Profit Lock)
        - ROI >= 130% -> SL movido para +105% (Pré-Emancipação)
        - ROI >= 150% -> Emancipação
        """
        if roi >= 130.0: return 105.0
        if roi >= 110.0: return 80.0
        if roi >= 70.0: return 45.0
        if roi >= 50.0: return 25.0
        if roi >= 30.0: return 6.0
        return None

    def _get_status_risco(self, roi: float) -> str:
        """
        [V123] Mapeia o ROI atual ao status_risco exibido no badge da UI.
        Alinhado com a lógica do cockpit.html linha 5200-5207:
        - PROFIT_LOCK  -> badge 'LUCRO TRAVADO'  (âmbar)
        - RISCO_ZERO   -> badge 'RISCO ZERO'      (verde)
        - SL_0         -> badge 'SENTINELA ATIVO' (ciano)
        - MONITORANDO  -> badge 'STOP INICIAL'    (azul)
        """
        if roi >= 110.0: return "PROFIT_LOCK"        # SL em +80% → lucro garantido
        if roi >= 70.0:  return "RISCO_ZERO"         # SL em +45% → sem risco de perda
        if roi >= 50.0:  return "SL_0"               # SL em +25% → sentinela/break-even avançado
        if roi >= 30.0:  return "SL_0"               # SL em +6%  → sentinela break-even básico
        return "MONITORANDO"                         # Ainda no stop inicial

    async def _update_stop_loss(self, symbol: str, side: str, sl_price: float, slot_id: int, qty: float):
        """Atualiza o Stop Loss na OKX (Real) ou na memória (Paper)."""
        if settings.OKX_API_KEY_MASTER:
            # Em modo OKX Master, usamos o Stop Loss Virtual Ativo monitorado a cada ciclo.
            # O preço de stop atualizado já é persistido no banco local.
            logger.info(f"🛡️ [SlotOperator-{self.slot_id}] {symbol} Stop virtual atualizado no banco para {sl_price:.4f} (Failsafe OKX ativo).")
            return

        if self.okx_rest.execution_mode == "PAPER":
            # Atualização em memória
            pos = next((p for p in self.okx_rest.paper_positions if self.okx_rest.normalize_symbol(p["symbol"]) == self.okx_rest.normalize_symbol(symbol)), None)
            if pos:
                pos["stopLoss"] = str(sl_price)
                await self.okx_rest._save_paper_state()
            return
            
        # Execução Real
        try:
            position_idx = 1 if side.upper() == "BUY" else 2 # Assumindo Hedge Mode por padrão de segurança
            
            # Alguns motores precisam recuperar o mode:
            mode = self.okx_rest._position_mode_cache.get(self.okx_rest.normalize_symbol(symbol), "ONE_WAY")
            if mode == "ONE_WAY":
                position_idx = 0
                
            await asyncio.to_thread(
                self.okx_rest.session.set_trading_stop,
                category=self.okx_rest.category,
                symbol=self.okx_rest.normalize_symbol(symbol),
                stopLoss=str(sl_price),
                tpslMode="Full",
                positionIdx=position_idx
            )
        except Exception as e:
            logger.error(f"Erro ao definir Stop Loss na corretora para {symbol}: {e}")
