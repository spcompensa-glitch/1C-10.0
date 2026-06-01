import asyncio
import time
import logging
from typing import Dict, Any, List, Optional
from services.firebase_service import firebase_service
from services.okx_rest import okx_rest_service
from services.database_service import database_service
from services.bankroll import bankroll_manager
from config import settings

logger = logging.getLogger("SentinelAuditor")

class SentinelAuditor:
    def __init__(self):
        self.heartbeats: Dict[str, float] = {}
        self.last_reconciliation_at: float = 0.0
        self.divergences_detected: int = 0
        self.auto_healings: List[Dict[str, Any]] = []
        self.is_active: bool = True
        self._lock = asyncio.Lock()

    def record_heartbeat(self, module_name: str):
        """[V126] Registra o batimento cardíaco (liveness) de um loop operacional."""
        self.heartbeats[module_name] = time.time()
        # logger.debug(f"💓 [SENTINEL-HEARTBEAT] {module_name} está ativo.")

    def get_health_status(self) -> dict:
        """[V126] Retorna o status de integridade de todos os loops monitorados."""
        now = time.time()
        status_map = {}
        is_healthy = True

        expected_modules = ["signal_generator", "portfolio_guardian"]
        if okx_rest_service.execution_mode == "PAPER":
            expected_modules.append("paper_execution_loop")
        else:
            expected_modules.append("real_execution_loop")

        for module in expected_modules:
            last_ts = self.heartbeats.get(module, 0)
            if last_ts == 0:
                status_map[module] = {"status": "STANDBY", "last_heartbeat_seconds_ago": -1}
            elif now - last_ts > 45.0:
                status_map[module] = {"status": "INACTIVE", "last_heartbeat_seconds_ago": round(now - last_ts, 1)}
                is_healthy = False
            else:
                status_map[module] = {"status": "ACTIVE", "last_heartbeat_seconds_ago": round(now - last_ts, 1)}

        return {
            "status": "HEALTHY" if is_healthy else "DEGRADED",
            "timestamp": int(now),
            "monitors": status_map
        }

    async def start(self):
        """Inicia o loop assíncrono isolado do Sentinela."""
        logger.info("🛡️ [SENTINEL] Sentinel Auditor Core ativado e rodando...")
        asyncio.create_task(self._reconciliation_loop())

    async def _reconciliation_loop(self):
        """Loop de varredura tríplice a cada 20 segundos."""
        await asyncio.sleep(5)  # Delay inicial para o boot estável do sistema
        while self.is_active:
            try:
                self.record_heartbeat("sentinel_auditor")
                await self.reconcile()
            except Exception as e:
                logger.error(f"❌ [SENTINEL-RECONCILE-LOOP] Erro crítico no loop de reconciliação: {e}")
            await asyncio.sleep(20)

    async def reconcile(self):
        """Executa a reconciliação tríplice determinística."""
        async with self._lock:
            now = time.time()
            self.last_reconciliation_at = now

            # 1. Pega slots no banco (Firestore/Postgres)
            firestore_slots = await firebase_service.get_active_slots(force_refresh=True)
            if firestore_slots is None:
                firestore_slots = []

            # 2. Pega posições na exchange (real ou paper)
            exchange_positions = await okx_rest_service.get_active_positions()
            if exchange_positions is None:
                exchange_positions = []

            # 3. Mapeamentos por símbolo limpo (remover .P e formatar)
            slots_by_symbol = {}
            for s in firestore_slots:
                sym = s.get("symbol")
                if sym:
                    clean_sym = okx_rest_service._strip_p(sym).upper()
                    slots_by_symbol[clean_sym] = s

            positions_by_symbol = {}
            for p in exchange_positions:
                sym = p.get("symbol")
                if sym:
                    clean_sym = okx_rest_service._strip_p(sym).upper()
                    positions_by_symbol[clean_sym] = p

            # -----------------------------------------------------------------
            # FASE 1: CASO A - SLOT NO BANCO MAS NÃO NA EXCHANGE (POSICAO ÓRFÃ NO BANCO)
            # -----------------------------------------------------------------
            for clean_sym, slot in list(slots_by_symbol.items()):
                if clean_sym not in positions_by_symbol:
                    opened_at = slot.get("opened_at", 0)
                    from datetime import datetime
                    if isinstance(opened_at, datetime):
                        opened_at_ts = opened_at.timestamp()
                    elif isinstance(opened_at, (int, float)):
                        opened_at_ts = float(opened_at)
                    else:
                        opened_at_ts = 0.0

                    if 0 <= (now - opened_at_ts) < 15.0:
                        continue  # Dá um grace period de 15s para a criação se consolidar

                    slot_id = slot.get("id")
                    logger.warning(
                        f"🚑 [SENTINEL-AUTO-HEAL] Posição órfã no banco detectada: {clean_sym} (Slot {slot_id}). "
                        f"Encerrando slot deterministicamente e registrando no Vault..."
                    )

                    self.divergences_detected += 1
                    self.auto_healings.append({
                        "ts": now,
                        "type": "ORPHAN_BANK_HEAL",
                        "symbol": clean_sym,
                        "slot_id": slot_id,
                        "details": "Posição fechada na exchange/RAM. Slot de banco purgado e arquivado."
                    })

                    try:
                        # [V110.702] Corrigido com fallback robusto e PNL seguro
                        side = slot.get("side", "Buy")
                        entry_price = float(slot.get("entry_price") or 0)
                        qty = float(slot.get("qty") or 0)
                        entry_margin = float(slot.get("entry_margin") or 0)
                        leverage = float(slot.get("leverage") or 50)
                        
                        # Preserva metadados originais para auditoria
                        original_stop = float(slot.get("current_stop") or 0)
                        original_target = float(slot.get("target_price") or 0)
                        genesis_id = slot.get("genesis_id") or f"SNT-{int(now)}-{clean_sym[:4]}"

                        # Fallback robusto de preço com tratamento de falha
                        try:
                            exit_price = await slot_operator_price_fallback(clean_sym)
                            
                            # Validação de preço: se obtido, preserva SL/TP originais
                            if exit_price > 0:
                                logger.info(f"[SENTINEL-ORPHAN] Preço obtido: {clean_sym} = {exit_price:.6f}")
                                # Para posições órfãs, usa o preço de mercado como saída
                                pass
                            else:
                                raise ValueError("Preço inválido obtido do fallback")
                                
                        except Exception as price_error:
                            logger.warning(f"[SENTINEL-ORPHAN] Fallback de preço falhou para {clean_sym}: {price_error}")
                            # Lógica de fallback inteligente
                            if original_stop > 0:
                                exit_price = original_stop  # Usa SL original como preço de saída
                                logger.info(f"[SENTINEL-ORPHAN] Usando SL original: {exit_price:.6f}")
                            elif original_target > 0:
                                exit_price = original_target  # Usa TP original como preço de saída
                                logger.info(f"[SENTINEL-ORPHAN] Usando TP original: {exit_price:.6f}")
                            else:
                                # Último recurso: usa preço de entrada com pequena variação
                                exit_price = entry_price * 0.999 if side.lower() == "buy" else entry_price * 1.001
                                logger.warning(f"[SENTINEL-ORPHAN] Último recurso: preço calculado = {exit_price:.6f}")

                        # Cálculo seguro de PNL com proteção de margem
                        pnl_percent, pnl_val, validated_exit_price = await calculate_safe_pnl(
                            entry_price, exit_price, side, leverage, entry_margin
                        )
                        exit_price = validated_exit_price  # Usa preço validado

                        logger.info(f"[SENTINEL-ORPHAN] PNL calculado para {clean_sym}: ROI={pnl_percent:.2f}% PNL=${pnl_val:.4f}")

                        reason = f"Sentinel Auto-Cura: Posição órfã encerrada na corretora."

                        trade_data = {
                            "symbol": slot.get("symbol") or (clean_sym + ".P"),
                            "side": side,
                            "qty": qty,
                            "entry_price": entry_price,
                            "exit_price": exit_price,
                            "entry_margin": entry_margin,
                            "leverage": leverage,
                            "pnl": pnl_val,
                            "pnl_percent": pnl_percent,
                            "final_roi": pnl_percent,
                            "genesis_id": genesis_id,
                            "slot_id": slot_id,
                            "slot_type": slot.get("slot_type", "BLITZ_30M"),
                            "opened_at": slot.get("opened_at") or now,
                            "closed_at": now,
                            "close_reason": reason,
                            "pensamento": slot.get("pensamento", "🚑 Posição órfã encerrada e arquivada pelo Sentinel Auditor."),
                            "original_stop": original_stop,
                            "original_target": original_target
                        }

                        # Preserva SL/TP originais no histórico
                        if original_stop > 0:
                            trade_data["initial_stop"] = original_stop
                            trade_data["current_stop"] = original_stop
                        if original_target > 0:
                            trade_data["target_price"] = original_target

                        await firebase_service.hard_reset_slot(
                            slot_id,
                            reason=reason,
                            pnl=pnl_val,
                            trade_data=trade_data
                        )
                    except Exception as he:
                        logger.error(f"❌ [SENTINEL] Falha ao curar slot órfão {slot_id}: {he}")

    async def get_auto_healings(self):
        """Retorna histórico de auto-cura para auditoria."""
        return self.auto_healings

    async def clear_auto_healings(self):
        """Limpa histórico de auto-cura."""
        self.auto_healings = []

# [V110.702] Fallback de preços robusto com múltiplas fontes e validação
async def slot_operator_price_fallback(symbol: str) -> float:
    """
    [V110.702] Fallback de preços robusto com múltiplas fontes e validação.
    Retorna preço > 0.0 ou dispara exceção para tratamento de fallback externo.
    """
    
    # Fonte 1: WebSocket Bybit (mais rápido e atual)
    try:
        from services.bybit_ws import bybit_ws_service
        ws_price = getattr(bybit_ws_service, 'get_current_price', None)
        if ws_price:
            price = ws_price(symbol)
            if price and price > 0:
                logger.debug(f"[PRICE-FALLBACK] WebSocket Bybit: {symbol} = {price}")
                return price
    except Exception as e:
        logger.debug(f"[PRICE-FALLBACK] WebSocket falhou: {e}")
    
    # Fonte 2: OKX REST Ticker (fallback confiável)
    try:
        ticker = await okx_rest_service.get_tickers(symbol)
        if ticker and ticker.get("result", {}).get("list"):
            price = float(ticker["result"]["list"][0].get("lastPrice", 0))
            if price > 0:
                logger.debug(f"[PRICE-FALLBACK] OKX Ticker: {symbol} = {price}")
                return price
    except Exception as e:
        logger.debug(f"[PRICE-FALLBACK] OKX Ticker falhou: {e}")
    
    # Fonte 3: OHLCV recente do Bybit (último fechamento)
    try:
        ohlcv = await okx_rest_service.get_candlesticks(symbol, "1m", limit=1)
        if ohlcv and len(ohlcv) > 0:
            price = float(ohlcv[0][4])  # Fechamento (close)
            if price > 0:
                logger.debug(f"[PRICE-FALLBACK] OHLCV 1m: {symbol} = {price}")
                return price
    except Exception as e:
        logger.debug(f"[PRICE-FALLBACK] OHLCV falhou: {e}")
    
    # Se todas as fontes falharem, dispara exceção para tratamento externo
    logger.error(f"[PRICE-FALLBACK] FALHA CRÍTICA: Nenhuma fonte de preço válida para {symbol}")
    raise ValueError(f"PRICE_UNAVAILABLE: {symbol}")


async def calculate_safe_pnl(entry_price: float, exit_price: float, side: str, 
                           leverage: float = 50.0, margin: float = 100.0) -> tuple:
    """
    [V110.702] Calcula PNL seguro com proteção contra perdas superiores à margem.
    Retorna (pnl_percent, pnl_val, exit_price_validated)
    """
    if entry_price <= 0 or exit_price <= 0:
        return 0.0, 0.0, exit_price
    
    # Cálculo padrão de ROI
    side_norm = side.lower()
    if side_norm in ["buy", "long"]:
        price_diff_pct = (exit_price - entry_price) / entry_price
    else:  # sell/short
        price_diff_pct = (entry_price - exit_price) / entry_price
    
    roi = price_diff_pct * leverage * 100
    pnl_val = (roi / 100.0) * margin
    
    # [ANTI-MASSACRE] Proteção contra PNL que excede a margem real
    max_loss = -margin  # Perda máxima = valor total da margem
    if pnl_val < max_loss:
        logger.warning(f"[PNL-PROTECTION] PNL corrigido de {pnl_val:.2f} para {max_loss:.2f} (margem de proteção)")
        pnl_val = max_loss
        
        # Recalcula preço de saída equivalente à perda máxima permitida
        if roi < -100:
            roi = -100  # Cap em -100% ROI para evitar "perdas fantasmas"
            if side_norm in ["buy", "long"]:
                exit_price = entry_price * (1 + roi / (leverage * 100))
            else:
                exit_price = entry_price * (1 - roi / (leverage * 100))
    
    pnl_percent = round(roi, 2)
    pnl_val = round(pnl_val, 4)
    
    return pnl_percent, pnl_val, exit_price

# Instanciação Singleton global do Sentinel Auditor
sentinel_auditor = SentinelAuditor()