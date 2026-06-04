# -*- coding: utf-8 -*-
import asyncio
import logging
import time
from typing import List, Dict, Any, Optional
from config import settings
from services.okx_service import okx_service
from services.okx_ws import okx_ws_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PortfolioGuardian")

class PortfolioGuardian:
    def __init__(self):
        # Configurações carregadas do settings (.env)
        self.activation_trigger = settings.GUARDIAN_ACTIVATION_TRIGGER
        self.trailing_margin = settings.GUARDIAN_TRAILING_MARGIN
        
        # Estados da Máquina de Estados:
        # "OBSERVANDO": Monitorando PnL e margem aguardando o trigger de ativação.
        # "RASTREAMENTO_ATIVO": Trailing Stop ativado, rastreando pico máximo de ROI.
        # "EXECUTAR_CORTE": Disparado Knife-Drop emergencial.
        self.state = "OBSERVANDO"
        
        self.max_roi_registered = 0.0
        self.current_roi = 0.0
        self.last_pnl_sum = 0.0
        self.last_margin_sum = 0.0
        self.last_update_time = time.time()
        
        # Lock de concorrência para evitar chamadas duplas ao Knife-Drop
        self._lock = asyncio.Lock()
        
        logger.info(f"🛡️ [GUARDIAN] Inicializado. Gatilho de Ativação: {self.activation_trigger}% | Margem de Recuo: {self.trailing_margin}%")

    def start(self):
        """Registra o callback no WebSocket da OKX para receber atualizações automáticas."""
        okx_ws_service.register_callback(self.evaluate_master_state)
        logger.info("🛡️ [GUARDIAN] Escuta ativada no WebSocket privado da OKX Master.")
        # [V124] Inicia loop REST como fallback para garantir avaliação mesmo sem WS ativo
        asyncio.create_task(self._rest_fallback_loop())
        logger.info("🛡️ [GUARDIAN] Loop REST-Fallback iniciado (polling a cada 30s como redundância).")

    async def _rest_fallback_loop(self):
        """[V124] Loop de segurança: avalia posições via REST a cada 30s se o WS estiver silencioso."""
        await asyncio.sleep(60)  # Grace period inicial — aguarda WS conectar
        while True:
            try:
                from services.sentinel_auditor import sentinel_auditor
                sentinel_auditor.record_heartbeat("portfolio_guardian")

                # Só usa REST se o último update do WS foi há mais de 45s (WS silencioso)
                ws_lag = time.time() - self.last_update_time
                if ws_lag > 45:
                    logger.warning(f"🛡️ [GUARDIAN-FALLBACK] WS silencioso por {ws_lag:.0f}s. Consultando REST OKX...")
                    positions = await okx_service.get_positions()
                    if positions:
                        asyncio.create_task(self._process_evaluation(positions))
            except Exception as e:
                logger.error(f"❌ [GUARDIAN-FALLBACK] Erro no loop REST: {e}")
            await asyncio.sleep(30)

    def get_status(self) -> Dict[str, Any]:
        """Retorna o status atual do Guardian para diagnóstico ou APIs externas."""
        return {
            "estado": self.state,
            "roi_atual": round(self.current_roi, 2),
            "pico_roi_registrado": round(self.max_roi_registered, 2),
            "ultimo_pnl": round(self.last_pnl_sum, 2),
            "ultima_margem": round(self.last_margin_sum, 2),
            "gatilho_ativacao": self.activation_trigger,
            "margem_recuo": self.trailing_margin,
            "timestamp": self.last_update_time
        }

    def evaluate_master_state(self, positions: List[Dict[str, Any]]):
        """
        Callback que recebe as posições ativas do WebSocket privado da OKX e
        executa a avaliação atômica da máquina de estados do Trailing-Stop.
        """
        # Como o callback é síncrono no loop do WS, criamos uma tarefa assíncrona para rodar a avaliação.
        asyncio.create_task(self._process_evaluation(positions))

    async def _process_evaluation(self, positions: List[Dict[str, Any]]):
        async with self._lock:
            # [ANTI-FACÃO] Consulta Moonbags/Emancipados para blinda-los do corte
            from services.firebase_service import firebase_service
            try:
                moonbags = await firebase_service.get_moonbags(limit=200)
                emancipated_symbols = set()
                if moonbags:
                    for m in moonbags:
                        sym = m.get("symbol")
                        if sym:
                            emancipated_symbols.add(sym.upper().replace(".P", ""))
            except Exception as e:
                logger.error(f"🛡️ [GUARDIAN] Erro ao buscar Moonbags: {e}")
                emancipated_symbols = set()

            # Filtra posições, removendo as protegidas
            tactical_positions = []
            for pos in positions:
                inst_id = pos.get("instId", "").upper().replace(".P", "")
                # Se for Bybit, usa symbol
                if not inst_id:
                    inst_id = pos.get("symbol", "").upper().replace(".P", "")
                    
                if inst_id in emancipated_symbols:
                    # Não logar warning para não floodar o terminal, apenas ignorar
                    continue
                tactical_positions.append(pos)
                
            positions = tactical_positions

            if not positions:
                # Sem posições abertas, resetamos o estado para OBSERVANDO se necessário
                if self.state != "OBSERVANDO":
                    logger.info("🛡️ [GUARDIAN] Nenhuma posição aberta detectada na Conta Master. Retornando ao estado OBSERVANDO.")
                    self.state = "OBSERVANDO"
                    self.max_roi_registered = 0.0
                self.current_roi = 0.0
                self.last_pnl_sum = 0.0
                self.last_margin_sum = 0.0
                self.last_update_time = time.time()
                return

            pnl_sum = 0.0
            margin_sum = 0.0
            
            for pos in positions:
                try:
                    # upl = unrealized profit and loss
                    upl_val = pos.get("upl")
                    upl = float(upl_val) if upl_val and str(upl_val).strip() != "" else 0.0
                    
                    # margin ou mgnVal = margem alocada
                    margin_val = pos.get("margin", pos.get("mgnVal"))
                    if margin_val and str(margin_val).strip() != "":
                        margin = float(margin_val)
                    else:
                        margin = 0.0
                        
                    # Se margem for zero (comum em Portfolio Margin na OKX), calculamos a estimada via notionalUsd / lever
                    if margin <= 0.0:
                        notional_usd = abs(float(pos.get("notionalUsd") or 0.0))
                        lever = float(pos.get("lever") or 50.0)
                        if lever > 0:
                            margin = notional_usd / lever
                    
                    pnl_sum += upl
                    margin_sum += margin
                except Exception as e:
                    logger.error(f"🛡️ [GUARDIAN] Erro ao parsear valores da posição: {pos}. Erro: {e}")

            self.last_pnl_sum = pnl_sum
            self.last_margin_sum = margin_sum
            self.last_update_time = time.time()

            # Calcula o ROI unificado (%)
            if margin_sum > 0:
                self.current_roi = (pnl_sum / margin_sum) * 100.0
            else:
                self.current_roi = 0.0

            logger.info(f"📊 [GUARDIAN] ROI Master: {self.current_roi:.2f}% | PnL Total: ${pnl_sum:.2f} | Margem Total: ${margin_sum:.2f} | Estado: {self.state}")

            # MÁQUINA DE ESTADOS DO GUARDIAN
            if self.state == "OBSERVANDO":
                if self.current_roi >= self.activation_trigger:
                    self.state = "RASTREAMENTO_ATIVO"
                    self.max_roi_registered = self.current_roi
                    logger.warning(
                        f"🚀🚀🚀 [GUARDIAN] Trailing-Stop ATIVADO! ROI Master ({self.current_roi:.2f}%) "
                        f"atingiu o limite mínimo de ativação de {self.activation_trigger}%."
                    )
            
            elif self.state == "RASTREAMENTO_ATIVO":
                # Atualiza a máxima histórica registrada
                if self.current_roi > self.max_roi_registered:
                    self.max_roi_registered = self.current_roi
                    logger.info(f"📈 [GUARDIAN] Novo pico de ROI registrado: {self.max_roi_registered:.2f}%")

                # Verifica se houve recuo abaixo da margem tolerada
                threshold_corte = self.max_roi_registered - self.trailing_margin
                logger.info(f"🔍 [GUARDIAN] Análise: ROI Atual {self.current_roi:.2f}% | Gatilho de Corte {threshold_corte:.2f}% (Pico: {self.max_roi_registered:.2f}%)")
                
                if self.current_roi < threshold_corte:
                    self.state = "EXECUTAR_CORTE"
                    logger.critical(
                        f"💥💥💥 [GUARDIAN - KNIFE-DROP] GATILHO DISPARADO! "
                        f"ROI Master ({self.current_roi:.2f}%) recuou abaixo do limite tolerado ({threshold_corte:.2f}%)."
                    )
                    await self._execute_knife_drop(positions)

            elif self.state == "EXECUTAR_CORTE":
                # Proteção contra repetição se posições ainda existirem
                logger.warning("🛡️ [GUARDIAN] Já em estado de EXECUTAR_CORTE. Aguardando finalização das ordens.")

    async def _execute_knife_drop(self, positions: List[Dict[str, Any]]):
        """Executa o fechamento emergencial em lote da OKX e emite alerta de pânico."""
        try:
            # 1. Dispara fechamento em lote na corretora
            logger.critical("🔪 [GUARDIAN] Enviando ordem de fechamento imediato em Lote na OKX (Knife-Drop)...")
            res = await okx_service.batch_close_positions(positions)
            logger.info(f"🛡️ [GUARDIAN] Resposta do Knife-Drop: {res}")

            # 2. [V122] Registrar histórico no Vault para cada posição fechada pelo Facão
            try:
                from services.firebase_service import firebase_service
                from services.bankroll import bankroll_manager
                from services.okx_rest import okx_rest_service
                from services.time_utils import get_br_iso_str
                import asyncio as _asyncio

                # Aguarda breve para OKX sincronizar o PnL realizado
                await _asyncio.sleep(3)

                all_slots = await firebase_service.get_slots()

                for pos in positions:
                    try:
                        inst_id = pos.get("instId", "")
                        # Converte OKX (AVAX-USDT-SWAP) para padrão interno (AVAXUSDT)
                        norm_symbol = inst_id.upper().replace("-USDT-SWAP", "USDT").replace("-USDC-SWAP", "USDC").replace("-", "")

                        # Encontra o slot correspondente no Firebase
                        matched_slot = None
                        matched_slot_id = None
                        for s in all_slots:
                            s_sym = (s.get("symbol") or "").upper().replace(".P", "")
                            if s_sym == norm_symbol:
                                matched_slot = s
                                matched_slot_id = s.get("id") or s.get("slot_id")
                                break

                        # Busca PnL realizado na OKX
                        closed_list = []
                        for attempt in range(3):
                            closed_list = await okx_rest_service.get_closed_pnl(symbol=f"{norm_symbol}.P", limit=3)
                            if closed_list:
                                break
                            logger.info(f"⏳ [KNIFE-DROP] PnL para {norm_symbol} ainda não disponível (tentativa {attempt+1}/3)...")
                            await _asyncio.sleep(2)

                        pnl_val = 0.0
                        exit_price = 0.0
                        qty = float(pos.get("pos", 0))
                        order_id = f"KNIFE_DROP_{norm_symbol}_{int(time.time())}"

                        if closed_list:
                            last = closed_list[0]
                            pnl_val = float(last.get("closedPnl", 0))
                            exit_price = float(last.get("avgExitPrice", 0))
                            qty = float(last.get("qty", qty))
                            order_id = last.get("orderId", order_id)

                        entry_price = float(pos.get("avgPx", 0)) if matched_slot is None else float(matched_slot.get("entry_price", pos.get("avgPx", 0)))
                        side = "Buy" if pos.get("posSide", "long") == "long" else "Sell"
                        entry_margin = float(pos.get("margin") or pos.get("mgnVal", 0))
                        leverage = float(matched_slot.get("leverage", 50)) if matched_slot else 50.0
                        score = matched_slot.get("score", 0) if matched_slot else 0
                        pattern = matched_slot.get("pattern", "N/A") if matched_slot else "N/A"
                        fleet_intel = matched_slot.get("fleet_intel", {}) if matched_slot else {}
                        unified_conf = matched_slot.get("unified_confidence", 50) if matched_slot else 50
                        pensamento = matched_slot.get("pensamento", "") if matched_slot else ""
                        slot_type = matched_slot.get("slot_type", "SNIPER") if matched_slot else "SNIPER"

                        pnl_percent = round((pnl_val / entry_margin) * 100, 2) if entry_margin > 0 else 0
                        final_roi = round(((exit_price - entry_price) / entry_price) * 100 * leverage, 2) if entry_price > 0 and exit_price > 0 else pnl_percent
                        if side == "Sell":
                            final_roi = -final_roi

                        close_time_str = get_br_iso_str()
                        outcome_icon = "🔪 FACÃO" if pnl_val >= 0 else "🔪 FACÃO-LOSS"

                        report = f"--- RELATÓRIO KNIFE-DROP V122 ---\n"
                        report += f"GENESIS ID: {order_id}\n"
                        report += f"SÍMBOLO: {norm_symbol}\n"
                        report += f"MOTIVO: FACÃO AUTOMÁTICO (Trailing-Stop do Guardian)\n"
                        report += f"ROI Pico: {self.max_roi_registered:.1f}% | ROI no Corte: {self.current_roi:.1f}%\n"
                        report += f"\n📊 EXECUÇÃO:\n"
                        report += f"  Entrada: ${entry_price:.6f} | Saída: ${exit_price:.6f}\n"
                        report += f"  Qty: {qty} | Margem: ${entry_margin:.2f} | Lev: {leverage:.0f}x\n"
                        report += f"\n📈 RESULTADO:\n"
                        report += f"  {outcome_icon}\n"
                        report += f"  PnL: ${pnl_val:.2f} ({pnl_percent:.1f}%)\n"
                        report += f"  ROI Final: {final_roi:.1f}%\n"
                        report += f"\n⚓ INTELIGÊNCIA (V56.0):\n"
                        report += f"  Confiança Unificada: {unified_conf}%\n"
                        if pensamento:
                            report += f"\n💭 PENSAMENTO IA: {pensamento}\n"
                        report += f"\n⏰ Fechamento: {close_time_str}\n"
                        report += f"-----------------------------------"

                        trade_data = {
                            "symbol": f"{norm_symbol}.P",
                            "side": side,
                            "entry_price": entry_price,
                            "exit_price": exit_price,
                            "qty": qty,
                            "order_id": order_id,
                            "pnl": pnl_val,
                            "slot_id": matched_slot_id or 0,
                            "slot_type": slot_type,
                            "close_reason": "KNIFE_DROP_FACÃO",
                            "entry_margin": entry_margin,
                            "leverage": leverage,
                            "pnl_percent": pnl_percent,
                            "final_roi": final_roi,
                            "closed_at": close_time_str,
                            "reasoning_report": report,
                            "fleet_intel": fleet_intel,
                            "unified_confidence": unified_conf,
                            "pensamento": pensamento,
                            "score": score,
                            "pattern": pattern,
                        }

                        # Registra no Firebase (Firestore trade_history) e limpa o slot
                        if matched_slot_id:
                            await firebase_service.hard_reset_slot(
                                slot_id=matched_slot_id,
                                reason="KNIFE_DROP_FACÃO",
                                pnl=pnl_val,
                                trade_data=trade_data
                            )
                            logger.info(f"✅ [KNIFE-DROP] Slot {matched_slot_id} ({norm_symbol}) resetado e histórico salvo | PnL: ${pnl_val:.2f}")
                        else:
                            # Slot não encontrado: salva diretamente no trade_history
                            await firebase_service.log_trade(trade_data)
                            logger.info(f"✅ [KNIFE-DROP] Histórico salvo diretamente para {norm_symbol} (sem slot) | PnL: ${pnl_val:.2f}")

                        # Atualiza contadores do ciclo 1/10
                        await bankroll_manager.register_sniper_trade(trade_data)

                    except Exception as pos_err:
                        logger.error(f"❌ [KNIFE-DROP HISTORY] Falha ao registrar histórico para {pos.get('instId', '?')}: {pos_err}")

            except Exception as hist_err:
                logger.error(f"❌ [KNIFE-DROP HISTORY] Falha geral no registro de histórico: {hist_err}")

            # 3. Publica o sinal de pânico no broker MQTT do Hermes
            try:
                from services.hermes_broker import hermes_broker_service
                await hermes_broker_service.publish_panic_signal(positions)
            except Exception as mqtt_err:
                logger.error(f"❌ [GUARDIAN] Falha ao publicar sinal de pânico no Hermes MQTT: {mqtt_err}")

            # [HERMES TELEGRAM] Alerta de Facão
            try:
                from services.telegram_service import telegram_service
                await telegram_service.send_message("🔪 <b>FACÃO ACIONADO!</b>\nO Guardião detectou sangria na banca e fechou as posições de baixa performance para proteger a margem.")
            except:
                pass

            # Transiciona de volta para OBSERVANDO após limpar o portfólio
            self.state = "OBSERVANDO"
            self.max_roi_registered = 0.0
            logger.info("🛡️ [GUARDIAN] Execução de corte encerrada. Retornando ao estado de OBSERVANDO.")

        except Exception as e:
            logger.error(f"❌ [GUARDIAN] Erro crítico na execução do Knife-Drop: {e}", exc_info=True)
            self.state = "RASTREAMENTO_ATIVO"  # Tenta novamente na próxima atualização

# Instanciação Singleton
portfolio_guardian = PortfolioGuardian()
