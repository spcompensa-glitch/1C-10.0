# -*- coding: utf-8 -*-
"""
[V125] Agente Flash — Cérebro Unificado de Stops & Trailing (Scalping e Swing)
=============================================================================
Centraliza o monitoramento de stops (iniciais, escadinhas, trailing e timeframes)
tanto da conta real OKX (slots táticos) quanto do simulador autônomo Swing Lab (sandbox_swing_trades).

Garante que o comportamento no sandbox seja 100% idêntico ao real.

Regras unificadas:
  - Partial TP (50%): Apenas para Scalping. Desativado para Swing.
  - Alinhamento de Stops: Utiliza a mesma infraestrutura de ROI e projeção para ambos os escopos.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional

from services.database_service import database_service
from services.order_projection_service import order_projection_service
from services.okx_ws_public import okx_ws_public_service

logger = logging.getLogger("FlashAgent")


class FlashAgent:
    """
    Agente sentinela de ultra-velocidade (1s).
    Monitora de forma unificada os slots reais (OKX) e os trades virtuais (Swing Lab).
    """

    def __init__(self):
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self._slots_cache: List[Dict[str, Any]] = []
        self._last_slots_refresh = 0.0
        self._slots_cache_ttl = 3.0
        self._peak_roi_cache: Dict[str, float] = {}   # { slot_key: peak_roi }
        self._last_decor_check: Dict[str, float] = {}  # { symbol: timestamp }
        self._decor_check_interval = 30.0             # Verifica correlação a cada 30s
        self._last_price_cache: Dict[str, float] = {}  # { symbol: last_price }
        self._last_pnl_update: Dict[Any, float] = {}   # { slot_id/trade_id: last_update }
        self.leverage = 50.0                          # Fallback de alavancagem

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._flash_loop())
        logger.info("⚡ [FLASH] Agente Flash V2.0 ONLINE — Monitoramento Unificado (Scalping + Swing) ativo a cada 1s!")

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("⚡ [FLASH] Agente Flash DESLIGADO.")

    async def _flash_loop(self):
        """Loop principal: executa a cada 1 segundo."""
        while self.is_running:
            try:
                # Processa slots táticos (OKX Real/Simulado) e trades virtuais de Swing em paralelo
                tasks = [
                    self._scan_all_slots(),
                    self._scan_sandbox_swing_trades()
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for scope, result in zip(("SLOTS", "SWING_SANDBOX"), results):
                    if isinstance(result, BaseException):
                        self._log_flash_exception(scope, "SCAN", result)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"⚡ [FLASH] Erro no loop: {e}")
            await asyncio.sleep(1.0)

    # =========================================================================
    # SLOTS TÁTICOS (Real / OKX Paper)
    # =========================================================================

    async def _scan_all_slots(self):
        """Escaneia todos os slots ativos da conta principal."""
        now = time.time()
        if now - self._last_slots_refresh > self._slots_cache_ttl:
            self._slots_cache = await database_service.get_active_slots()
            self._last_slots_refresh = now

        slots = self._slots_cache
        if not slots:
            return

        tracked_tasks: List[tuple] = []
        for slot in slots:
            if slot.get("symbol") and float(slot.get("entry_price", 0)) > 0:
                tracked_tasks.append((str(slot.get("symbol")), self._process_slot(slot)))
        if tracked_tasks:
            results = await asyncio.gather(
                *(task for _, task in tracked_tasks),
                return_exceptions=True,
            )
            for (symbol, _), result in zip(tracked_tasks, results):
                if isinstance(result, BaseException):
                    self._log_flash_exception("SLOT", symbol, result)

    async def _process_slot(self, slot: Dict[str, Any]):
        """Processa um slot ativo: gerencia stops, parciais e trailing."""
        slot_id = slot.get("id")
        symbol = slot["symbol"]
        entry_price = float(slot.get("entry_price", 0))
        current_stop = float(slot.get("current_stop", 0))
        side = (slot.get("side") or "BUY").lower()
        qty = float(slot.get("qty", 0))
        leverage = float(slot.get("leverage") or self.leverage)
        slot_type = slot.get("slot_type", "")
        strategy = slot.get("strategy_class") or slot.get("strategy") or ""

        if entry_price <= 0:
            return

        current_price = await self._get_rest_price(symbol)
        if current_price <= 0:
            current_price = await self._get_current_price(symbol)
        if current_price <= 0:
            self._log_price_unavailable("SLOT", symbol, entry_price, current_stop, side, leverage)
            return

        is_ranging = True
        try:
            val = getattr(okx_ws_public_service, "btc_adx", 0.0)
            if val > 0.1:
                is_ranging = (val < 25)
        except Exception:
            pass

        # Constrói a projeção baseada nas regras unificadas
        projection = await order_projection_service.build_projection(
            slot,
            current_price=current_price,
            phase_hint="SLOT",
            is_ranging=is_ranging,
        )
        roi = float(projection.get("roi_percent") or 0)
        peak_price = self._get_peak_price(symbol, side, current_price)
        peak_roi = self._calc_roi(entry_price, peak_price, side, leverage) if peak_price > 0 else roi
        slot_key = slot.get("genesis_id") or f"slot:{slot_id}"
        cached_peak = float(self._peak_roi_cache.get(slot_key, 0.0) or 0.0)
        stored_peak = float(slot.get("pnl_percent") or 0.0)
        effective_roi = max(roi, peak_roi, cached_peak, stored_peak)
        self._peak_roi_cache[slot_key] = effective_roi

        # ─── Saída Parcial (Partial TP) ───
        # Apenas para SCALPING. Bloqueado explicitamente para Swing.
        is_swing = slot_type in ("BLITZ_30M", "SWING") or strategy in ("VELOCITY FLOW", "ALPHA SHIELD", "DECOR SHADOW")
        if False:  # [V125.3] Saída parcial desativada a pedido do usuário para manter 50x cheios
            partial_tp_threshold = 15.0  # Scalping parcial em 15% ROI
            audit = slot.get("execution_audit") or {}
            has_taken_partial = False
            if isinstance(audit, dict):
                has_taken_partial = audit.get("has_taken_partial", False)

            if is_ranging and effective_roi >= partial_tp_threshold and not has_taken_partial:
                partial_qty = qty * 0.5
                logger.warning(f"⚡ [FLASH-PARTIAL-TP] {symbol} atingiu +15% ROI lateral! Executando saida parcial de 50% (qty={partial_qty:.6f})")
                
                if not isinstance(audit, dict):
                    audit = {}
                audit["has_taken_partial"] = True
                
                entry_margin = float(slot.get("entry_margin") or 0)
                new_margin = entry_margin * 0.5
                
                await database_service.update_slot(slot_id, {
                    "qty": qty * 0.5,
                    "entry_margin": new_margin,
                    "execution_audit": audit
                })
                
                from services.okx_rest import okx_rest_service
                await okx_rest_service.close_position(
                    symbol,
                    side,
                    partial_qty,
                    reason=f"FLASH_PARTIAL_TP_{roi:.1f}%",
                    is_partial=True,
                    slot_id=slot_id
                )
                
                await self._sync_firebase_slot(slot_id, {
                    "qty": qty * 0.5,
                    "entry_margin": new_margin,
                    "execution_audit": audit
                })
                
                slot["qty"] = qty * 0.5
                slot["entry_margin"] = new_margin
                slot["execution_audit"] = audit
                qty = qty * 0.5

        # Projeção de decisão de trailing
        decision_projection = projection
        if effective_roi > roi + 0.1:
            decision_price = order_projection_service.raw_price_from_roi(
                entry_price,
                effective_roi,
                side,
                leverage,
            )
            decision_projection = await order_projection_service.build_projection(
                slot,
                current_price=decision_price,
                phase_hint="SLOT",
                is_ranging=is_ranging,
            )

        self._log_slot_tracking(
            slot_id,
            symbol,
            side,
            entry_price,
            current_price,
            current_stop,
            leverage,
            roi,
            effective_roi,
            decision_projection,
        )

        # Atualiza PnL
        self._update_pnl(slot_id, roi, slot)

        # ⚡ Violação de SL Inicial / Fixo
        if current_stop > 0:
            stop_hit = await self._check_stop_hit(side, current_stop, symbol)
            if stop_hit:
                fresh_price = await self._get_rest_price(symbol)
                if fresh_price > 0:
                    current_price = fresh_price
                    roi = self._calc_roi(entry_price, current_price, side, leverage)
                
                is_profit_stop = (side == "buy" and current_stop >= entry_price) or \
                                 (side == "sell" and current_stop <= entry_price)

                if is_profit_stop:
                    logger.warning(f"⚡ [FLASH-SL-PROFIT] {symbol} SL de lucro violado! Price=${current_price:.4f} Stop=${current_stop:.4f}")
                    await self._close_position(slot_id, symbol, side, qty, f"FLASH_PROFIT_SL_{roi:.1f}%")
                    return
                else:
                    logger.warning(f"🛑⚡ [FLASH-SL-LOSS-IMMEDIATE] {symbol} SL de perda atingido! Fechando imediatamente sem Sentinel. ROI={roi:.1f}%")
                    await self._close_position(slot_id, symbol, side, qty, f"FLASH_LOSS_SL_{roi:.1f}%")
                    return

        # ─── DECOR_HUNTER Re-correlação (se for o caso) ───
        if slot_type == "DECOR_HUNTER":
            now = time.time()
            last_check = self._last_decor_check.get(symbol, 0.0)
            if now - last_check >= self._decor_check_interval:
                self._last_decor_check[symbol] = now
                try:
                    corr = okx_ws_public_service.get_correlation(symbol, "BTCUSDT")
                    if abs(corr) > 0.5:
                        trailing_margin_pct = 0.05
                        tight_stop = current_price * (1 - trailing_margin_pct) if side == "buy" else current_price * (1 + trailing_margin_pct)
                        if self._stop_improves(side, current_stop, tight_stop):
                            logger.warning(f"[DECOR-HUNTER] {symbol} re-correlacionado (r={corr:.2f}) → trailing stop ${tight_stop:.4f}")
                            await self._update_slot_sl(slot_id, symbol, tight_stop, "MONITORANDO", side, qty)
                except Exception:
                    pass

        # ─── Atualização Progressiva da Escadinha / Trailing ───
        active_level = decision_projection.get("active_level")
        if not active_level or active_level.get("phase") not in ("ESCADINHA", "TRAILING"):
            return

        new_stop_roi = float(active_level.get("stop_roi") or 0)
        status_risco = active_level.get("status_risco") or "MONITORANDO"
        label = active_level.get("name") or "ESCADINHA"
        new_stop_price = float(decision_projection.get("recommended_stop") or 0)
        if new_stop_price <= 0 and new_stop_roi > 0:
            new_stop_price = await self._calc_stop_price(entry_price, new_stop_roi, side, leverage, symbol)
        if new_stop_price <= 0:
            return

        stop_improved = self._stop_improves(side, current_stop, new_stop_price)
        if not stop_improved:
            return

        logger.info(
            f"⚡ [FLASH-ESCADINHA] {symbol} peakROI={effective_roi:.1f}% "
            f"(atual {roi:.1f}%) → SL +{new_stop_roi:.0f}% (${new_stop_price:.4f}) | {label}"
        )
        await self._update_slot_sl(slot_id, symbol, new_stop_price, status_risco, side, qty)
        
        # Confirma se o stop recém-movido já foi violado imediatamente
        stop_hit = await self._check_stop_hit(side, new_stop_price, symbol)
        if stop_hit:
            logger.warning(f"[FLASH-TRAIL-SL] {symbol} voltou no stop conquistado ${new_stop_price:.4f}. Fechando.")
            await self._close_position(slot_id, symbol, side, qty, f"FLASH_TRAIL_SL_{roi:.1f}%")
            self._peak_roi_cache.pop(slot_key, None)

    # =========================================================================
    # SIMULADOR SWING LAB (sandbox_swing_trades)
    # =========================================================================

    async def _scan_sandbox_swing_trades(self):
        """Varre os trades virtuais ativos do Swing Lab a cada 1s e gerencia stops e saídas."""
        active_swings = await database_service.get_swing_trades(active_only=True)
        if not active_swings:
            return

        tasks = [self._process_sandbox_swing_trade(trade) for trade in active_swings]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_sandbox_swing_trade(self, trade):
        """Processa um trade virtual ativo do Swing Lab usando o motor unificado do FlashAgent."""
        trade_id = trade.id
        symbol = trade.symbol
        entry_price = float(trade.entry_price)
        current_stop = float(trade.stop_loss or 0)
        direction = trade.direction
        side = "buy" if direction == "LONG" else "sell"
        
        # A alavancagem para o Swing Sandbox é lida dinamicamente do config ou sandbox_swing_service
        from services.sandbox_swing_service import sandbox_swing_service
        leverage = float(sandbox_swing_service.leverage)
        margin = float(sandbox_swing_service.margin_per_trade)

        current_price = await self._get_current_price(symbol)
        if current_price <= 0:
            return

        # Calcula ROI
        roi = self._calc_roi(entry_price, current_price, side, leverage)
        
        # Peak ROI — sempre respeitar o maximo historico (cache + banco)
        peak_key = f"swing_sandbox:{trade_id}"
        peak_roi = max(self._peak_roi_cache.get(peak_key, 0.0), roi, float(trade.max_roi or 0.0))
        self._peak_roi_cache[peak_key] = peak_roi

        # Converte o trade em um payload compativel com o build_projection
        trade_dict = {
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "leverage": leverage,
            "current_stop": current_stop,
            "slot_type": "SWING",
            "strategy_class": trade.strategy,
        }

        projection = await order_projection_service.build_projection(
            trade_dict,
            current_price=current_price,
            phase_hint="SWING_SANDBOX",
            is_ranging=False,  # Swing usa a escadinha oficial progressiva independente
        )

        # Atualiza PnL e precos correntes no banco (a cada 2s)
        now = time.time()
        last_up = self._last_pnl_update.get(trade_id, 0)
        if now - last_up >= 2.0:
            self._last_pnl_update[trade_id] = now
            await database_service.update_swing_trade(trade_id, {
                "current_price": current_price,
                "current_roi": round(roi, 2),
                "pnl_pct": round(roi, 2),
                "max_roi": round(peak_roi, 2)
            })

        # ─────────────────────────────────────────────────────────────────────
        # [FIX #1] Helper de fechamento centralizado com status CORRETO.
        # Regra: stop em break-even ou lucro => CLOSED_TRAILING (nao CLOSED_SL).
        # Stop abaixo do entry (loss) => CLOSED_SL.
        # Confirmado pelo banco: ALGOUSDT fechou com stop=entry e status CLOSED_SL
        # incorretamente, distorcendo o Win Rate do Swing Lab.
        # ─────────────────────────────────────────────────────────────────────
        async def _close_swing(stop_triggered: float, reason: str):
            is_profit_stop = (
                (side == "buy"  and stop_triggered >= entry_price) or
                (side == "sell" and stop_triggered <= entry_price)
            )
            status = "CLOSED_TRAILING" if is_profit_stop else "CLOSED_SL"
            fs = dict(trade.flash_state or {})
            fs["history"] = fs.get("history", []) + [{
                "ts": time.time(), "event": status, "roi": round(roi, 2),
                "price": current_price, "stop_triggered": stop_triggered,
                "level": fs.get("active_level", "CLOSED")
            }]
            await database_service.update_swing_trade(trade_id, {
                "status": status,
                "current_price": current_price,
                "current_roi": round(roi, 2),
                "pnl_pct": round(roi, 2),
                "closed_at": time.time(),
                "flash_state": fs
            })
            self._peak_roi_cache.pop(peak_key, None)
            pnl_usd = (roi / 100.0) * margin
            logger.warning(
                f"[FLASH-SWING-SANDBOX] {symbol} {direction} {status} | "
                f"Motivo={reason} | ROI={roi:.1f}% | PnL=${pnl_usd:.2f} | "
                f"Stop=${stop_triggered:.6f} | Entry=${entry_price:.6f}"
            )

        # ─────────────────────────────────────────────────────────────────────
        # [FIX #2] Verificacao de Stop Loss com preco conservativo.
        # Usa get_conservative_price (bid/ask) para evitar falsos positivos
        # mas garantir que violacoes reais sejam capturadas na janela de 1s.
        # ─────────────────────────────────────────────────────────────────────
        if current_stop > 0:
            try:
                conservative_price = okx_ws_public_service.get_conservative_price(symbol, side)
                check_price = conservative_price if conservative_price > 0 else current_price
            except Exception:
                check_price = current_price

            stop_hit = (side == "buy" and check_price <= current_stop) or \
                       (side == "sell" and check_price >= current_stop)
            if stop_hit:
                await _close_swing(current_stop, f"STOP_HIT@{check_price:.6f}")
                return

        # ─────────────────────────────────────────────────────────────────────
        # Atualizacao Progressiva do Stop (Trailing / Escadinha).
        # Decisao baseada no PICO historico de ROI, nao no preco atual.
        # ─────────────────────────────────────────────────────────────────────
        decision_projection = projection
        if peak_roi > roi + 0.1:
            decision_price = order_projection_service.raw_price_from_roi(
                entry_price,
                peak_roi,
                side,
                leverage,
            )
            decision_projection = await order_projection_service.build_projection(
                trade_dict,
                current_price=decision_price,
                phase_hint="SWING_SANDBOX",
                is_ranging=False,
            )

        active_level = decision_projection.get("active_level")

        # ─────────────────────────────────────────────────────────────────────
        # [FIX #3] Fallback quando active_level e None ou fase invalida.
        # O stop do banco ainda existe e DEVE ser monitorado — nao abandonar.
        # Sem este fix, uma falha de projecao silencia o monitoramento do stop.
        # ─────────────────────────────────────────────────────────────────────
        if not active_level or active_level.get("phase") not in ("ESCADINHA", "TRAILING"):
            if current_stop > 0:
                stop_hit_fallback = (side == "buy" and current_price <= current_stop) or \
                                    (side == "sell" and current_price >= current_stop)
                if stop_hit_fallback:
                    logger.warning(
                        f"[FLASH-SWING-FALLBACK] {symbol} stop ${current_stop:.6f} atingido "
                        f"sem escadinha ativa (peakROI={peak_roi:.1f}%). Fechando."
                    )
                    await _close_swing(current_stop, "FALLBACK_NO_LADDER")
            return

        new_stop_roi = float(active_level.get("stop_roi") or 0)
        new_stop_price = float(decision_projection.get("recommended_stop") or 0)
        if new_stop_price <= 0 and new_stop_roi != 0:
            new_stop_price = await self._calc_stop_price(entry_price, new_stop_roi, side, leverage, symbol)
        if new_stop_price <= 0:
            return

        stop_improved = self._stop_improves(side, current_stop, new_stop_price)
        if stop_improved:
            flash_state = dict(trade.flash_state or {})
            flash_state["stop_roi"] = new_stop_roi
            flash_state["active_level"] = active_level.get("name") or "ESCADINHA"
            
            logger.info(
                f"[FLASH-SWING-SANDBOX-TRAIL] {symbol} peakROI={peak_roi:.1f}% "
                f"-> SL +{new_stop_roi:.0f}% (${new_stop_price:.6f}) | {flash_state['active_level']}"
            )
            
            await database_service.update_swing_trade(trade_id, {
                "stop_loss": new_stop_price,
                "flash_state": flash_state
            })

            # ─────────────────────────────────────────────────────────────────
            # [FIX #4] Verificar IMEDIATAMENTE apos mover o stop (mesmo ciclo).
            # Elimina a janela cega de 1s onde o preco poderia violar e recuperar
            # antes da proxima iteracao do loop sem ser detectado.
            # ─────────────────────────────────────────────────────────────────
            stop_hit_immediate = (side == "buy" and current_price <= new_stop_price) or \
                                 (side == "sell" and current_price >= new_stop_price)
            if stop_hit_immediate:
                await _close_swing(new_stop_price, "IMMEDIATE_POST_TRAIL")

    # =========================================================================
    # HELPERS
    # =========================================================================

    async def _get_current_price(self, symbol: str) -> float:
        """Preço via WS cache local com fallback para preço REST ou cache histórico."""
        try:
            price = okx_ws_public_service.get_current_price(symbol)
            if price and price > 0:
                self._last_price_cache[symbol] = price
                return price
        except Exception:
            pass

        rest_price = await self._get_rest_price(symbol)
        if rest_price > 0:
            self._last_price_cache[symbol] = rest_price
            return rest_price

        return self._last_price_cache.get(symbol, 0.0)

    async def _get_rest_price(self, symbol: str) -> float:
        """Preço REST fresco para confirmação de stops."""
        try:
            from services.okx_rest import okx_rest_service
            ticker = await okx_rest_service.get_tickers(symbol=symbol)
            if isinstance(ticker, list) and ticker:
                return float(ticker[0].get("lastPrice") or 0)
            if isinstance(ticker, dict):
                ticker_list = ticker.get("result", {}).get("list", [])
                if ticker_list:
                    return float(ticker_list[0].get("lastPrice") or 0)
        except Exception:
            pass
        return 0.0

    def _get_peak_price(self, symbol: str, side: str, current_price: float) -> float:
        """Obtém o melhor preço recente a favor da ordem para evitar perder picos rápidos."""
        try:
            if side == "buy":
                high_price = okx_ws_public_service.get_high_price(symbol)
                return max(current_price, high_price or 0.0)
            low_price = okx_ws_public_service.get_low_price(symbol)
            if low_price and low_price > 0:
                return min(current_price, low_price)
        except Exception:
            pass
        return current_price

    async def _check_stop_hit(self, side: str, stop_price: float, symbol: str) -> bool:
        """Verifica se o stop foi violado usando preço conservativo de 30s."""
        if stop_price <= 0:
            return False

        try:
            check_price = okx_ws_public_service.get_conservative_price(symbol, side)
            if check_price > 0:
                stop_hit = (side == "buy" and check_price <= stop_price) or \
                           (side == "sell" and check_price >= stop_price)
                if stop_hit:
                    return True
        except Exception:
            pass

        current_price = await self._get_current_price(symbol)
        if current_price <= 0:
            return False
        return (side == "buy" and current_price <= stop_price) or \
               (side == "sell" and current_price >= stop_price)

    def _calc_roi(self, entry: float, current: float, side: str, leverage: float) -> float:
        if entry <= 0:
            return 0.0
        price_diff = (current - entry) / entry if side == "buy" else (entry - current) / entry
        return price_diff * leverage * 100

    def _update_pnl(self, slot_id: int, roi: float, slot: Dict[str, Any]):
        now = time.time()
        last_up = self._last_pnl_update.get(slot_id, 0)
        if now - last_up >= 2.0:
            self._last_pnl_update[slot_id] = now
            pnl_diff = abs(roi - float(slot.get("pnl_percent") or 0))
            if pnl_diff > 1.0:
                asyncio.create_task(
                    database_service.update_slot(slot_id, {"pnl_percent": roi})
                )

    async def _calc_stop_price(self, entry_price: float, stop_roi: float, side: str,
                                leverage: float, symbol: str) -> float:
        price_offset_pct = stop_roi / (leverage * 100)
        new_stop = entry_price * (1 + price_offset_pct) if side == "buy" else entry_price * (1 - price_offset_pct)
        try:
            from services.okx_rest import okx_rest_service
            info = await okx_rest_service.get_instrument_info(symbol)
            tick_size = float(info.get("priceFilter", {}).get("tickSize") or 0)
            new_stop = self._round_stop_to_tick(new_stop, tick_size, side, stop_roi)
        except Exception:
            pass
        return new_stop

    def _round_stop_to_tick(self, price: float, tick_size: float, side: str, stop_roi: float) -> float:
        if price <= 0 or tick_size <= 0:
            return price
        from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

        price_dec = Decimal(str(price))
        tick_dec = Decimal(str(tick_size))
        side_norm = (side or "").lower()
        if stop_roi >= 0 and side_norm == "buy":
            rounding = ROUND_CEILING
        elif stop_roi >= 0 and side_norm in ("sell", "short"):
            rounding = ROUND_FLOOR
        else:
            rounding = ROUND_HALF_UP
        rounded = (price_dec / tick_dec).quantize(Decimal("1"), rounding=rounding) * tick_dec
        return float(rounded.normalize())

    def _stop_improves(self, side: str, current_stop: float, new_stop: float) -> bool:
        """Retorna True se o novo stop price melhora a proteção (sobe no LONG, desce no SHORT)."""
        if current_stop <= 0:
            return True
        if side.lower() == "buy":
            return new_stop > current_stop + 1e-9
        return new_stop < current_stop - 1e-9

    # =========================================================================
    # AÇÕES DO BANCO E DE REDE
    # =========================================================================

    async def _update_slot_sl(self, slot_id: int, symbol: str, sl_price: float,
                               status_risco: str, side: str, qty: float):
        update_payload = {"current_stop": sl_price, "status_risco": status_risco}
        await database_service.update_slot(slot_id, update_payload)
        await self._sync_paper_stop(symbol, sl_price)
        await self._sync_firebase_slot(slot_id, update_payload)

    async def _close_position(self, slot_id: int, symbol: str, side: str, qty: float, reason: str):
        try:
            from services.okx_rest import okx_rest_service
            current_slot = await database_service.get_slot(slot_id)
            await okx_rest_service.close_position(symbol, side, qty, reason=reason)
            
            if current_slot and current_slot.get("symbol"):
                try:
                    from services.firebase_service import firebase_service
                    await firebase_service.hard_reset_slot(
                        slot_id, 
                        reason=reason,
                        pnl=0.0,
                        trade_data=current_slot
                    )
                except Exception as log_err:
                    logger.error(f"⚡ [FLASH] Erro ao registrar trade no histórico: {log_err}")
            else:
                await database_service.update_slot(slot_id, {
                    "symbol": None, "entry_price": 0, "current_stop": 0,
                    "qty": 0, "pnl_percent": 0, "status_risco": "LIVRE"
                })
            logger.warning(f"🛑⚡ [FLASH] {symbol} FECHADO por SL. Motivo: {reason}")
        except Exception as e:
            logger.error(f"⚡ [FLASH] Erro ao fechar {symbol}: {e}")

    async def _sync_paper_stop(self, symbol: str, sl_price: float):
        try:
            from services.okx_rest import okx_rest_service
            if okx_rest_service.execution_mode == "PAPER":
                norm = okx_rest_service.normalize_symbol(symbol)
                pos = next(
                    (p for p in okx_rest_service.paper_positions if okx_rest_service.normalize_symbol(p.get("symbol", "")) == norm),
                    None
                )
                if pos:
                    pos["stopLoss"] = str(sl_price)
                    await okx_rest_service._save_paper_state()
        except Exception as e:
            logger.warning(f"⚡ [FLASH] Paper sync fail: {e}")

    async def _sync_firebase_slot(self, slot_id: int, payload: dict):
        try:
            from services.firebase_service import firebase_service
            slot_state = await firebase_service.get_slot(slot_id)
            if slot_state and slot_state.get("symbol"):
                await firebase_service.update_slot(slot_id, payload)
        except Exception:
            pass

    def _log_flash_exception(self, scope: str, symbol: str, exception: BaseException):
        logger.error(f"⚡ [FLASH] Exception in {scope} for {symbol}: {exception}", exc_info=exception)

    def _log_price_unavailable(self, scope: str, symbol: str, entry: float, stop: float, side: str, leverage: float):
        logger.warning(f"⚡ [FLASH-{scope}] Preço indisponível para {symbol} (Entry={entry:.4f} Stop={stop:.4f})")

    def _log_slot_tracking(self, slot_id: int, symbol: str, side: str, entry: float, current: float,
                            stop: float, leverage: float, roi: float, effective_roi: float, projection: dict):
        logger.debug(
            f"⚡ [FLASH] Tracking slot={slot_id} {symbol} {side.upper()} "
            f"Entry=${entry:.4f} Price=${current:.4f} Stop=${stop:.4f} "
            f"ROI={roi:.1f}% MaxROI={effective_roi:.1f}% Phase={projection.get('phase')}"
        )


flash_agent = FlashAgent()
