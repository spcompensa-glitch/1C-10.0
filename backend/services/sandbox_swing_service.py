# -*- coding: utf-8 -*-
"""
[Swing Lab] SandboxSwingService — V1.0
Espelha as ordens reais do BlitzSniperAgent em uma banca virtual paralela de $100.

Doutrina das 10 Extracoes (mirror):
  - Unidade 1: >= 100% ROI -> SL em +95%
  - Unidade 2: >= 200% ROI -> SL em +180%
  - Unidade 3: >= 300% ROI -> SL em +270%
  - Emancipacao: >= 150% ROI -> SL em +110% (aguarda moonbag)

Cross-Block com SandboxService (Scalping Lab):
  - O mesmo ativo NAO pode estar ativo nas duas abas simultaneamente.
  - Isso simula uma conta real futura onde as duas estrategias compartilham capital.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger("SandboxSwingService")

SWING_VIRTUAL_BALANCE  = 100.0   # Banca virtual em USD
SWING_MARGIN_PER_TRADE = 1.0     # Margem por trade ($1 — igual ao Blitz real)
SWING_LEVERAGE         = 50.0    # Alavancagem

class SandboxSwingService:
    """
    Servico espelho do BlitzSniperAgent para o Swing Lab.
    Registra e monitora trades virtuais baseados nas ordens reais do Blitz.
    """

    def __init__(self):
        self._flash_loop_task: Optional[asyncio.Task] = None
        self._running = False
        self._peak_roi_cache: Dict[str, float] = {}  # { trade_id: max_roi }

    async def start(self):
        """Inicia o loop de monitoramento de stops (Flash loop)."""
        if self._running:
            return
        self._running = True
        self._flash_loop_task = asyncio.create_task(self._flash_loop())
        logger.info("[SWING-LAB] SandboxSwingService iniciado.")

    async def stop(self):
        self._running = False
        if self._flash_loop_task:
            self._flash_loop_task.cancel()
        logger.info("[SWING-LAB] SandboxSwingService parado.")

    # =========================================================================
    # ABERTURA — chamado pelo CaptainAgent ao abrir uma ordem Blitz real
    # =========================================================================

    async def on_blitz_signal(self, signal: Dict[str, Any], entry_price: float, stop_price: float):
        """
        Registra um novo trade Blitz no Swing Lab.
        Chamado pelo CaptainAgent imediatamente apos confirmar abertura real na OKX.

        Args:
            signal: Dicionario retornado pelo BlitzSniperAgent
            entry_price: Preco de entrada confirmado
            stop_price: Stop loss inicial calculado
        """
        try:
            from services.database_service import database_service
            from services.okx_ws_public import okx_ws_public_service

            symbol    = signal.get("symbol", "")
            side      = signal.get("side", "Buy")
            direction = "LONG" if side.upper() in ("BUY", "LONG") else "SHORT"

            # --- Cross-Block: verifica se o ativo esta no Scalping Lab ---
            scalp_active = await database_service.get_sandbox_trades(active_only=True)
            scalp_symbols = {t.symbol.replace(".P", "").upper() for t in scalp_active}
            if symbol.replace(".P", "").upper() in scalp_symbols:
                logger.info(
                    f"[SWING-CROSS-BLOCK] {symbol} esta ativo no Scalping Lab — "
                    f"Swing Lab nao pode abrir o mesmo ativo simultaneamente."
                )
                return

            # --- Evitar duplicata ---
            swing_active = await database_service.get_swing_trades(active_only=True)
            already = any(
                t.symbol.replace(".P", "").upper() == symbol.replace(".P", "").upper()
                and t.direction == direction
                for t in swing_active
            )
            if already:
                logger.debug(f"[SWING-LAB] {symbol} {direction} ja esta ativo no Swing Lab.")
                return

            # --- Obter preco atual ---
            current_price = entry_price
            if current_price <= 0:
                current_price = okx_ws_public_service.get_current_price(symbol)
            if current_price <= 0:
                logger.warning(f"[SWING-LAB] {symbol} sem preco — trade nao registrado.")
                return

            indicators = signal.get("indicators", {})
            fib_zone_raw = indicators.get("fib_zone")
            fib_zone_str = None
            if fib_zone_raw and isinstance(fib_zone_raw, (list, tuple)) and len(fib_zone_raw) == 2:
                fib_zone_str = f"{fib_zone_raw[0]:.3f}-{fib_zone_raw[1]:.3f}"
            elif isinstance(fib_zone_raw, str):
                fib_zone_str = fib_zone_raw

            trade_id = f"swing_{symbol.replace('.P','')}_{int(time.time())}"

            trade_data = {
                "id":            trade_id,
                "symbol":        symbol,
                "strategy":      "BLITZ_SNIPER",
                "direction":     direction,
                "entry_price":   entry_price,
                "current_price": current_price,
                "stop_loss":     stop_price,
                "target":        None,
                "max_roi":       0.0,
                "current_roi":   0.0,
                "pnl_pct":       0.0,
                "status":        "ACTIVE",
                "opened_at":     time.time(),
                "closed_at":     None,
                "flash_state": {
                    "phase":       "SWING_DOUTRINA",
                    "active_level": "INICIAL",
                    "stop_roi":    -50.0,   # Stop inicial Blitz (~-50% ROI com 50x e 1% no preco)
                    "blitz_unit":  0,
                    "history":     []
                },
                "contract_meta": signal.get("contract_meta"),
                "blitz_score":   float(signal.get("score", 0)),
                "fib_zone":      fib_zone_str,
                "sma_cross":     indicators.get("sma_cross", "NONE"),
                "cvd_value":     float(indicators.get("cvd", 0)),
                "volume_ratio":  float(indicators.get("volume_ratio", 0)),
                "pa_pattern":    indicators.get("pa_pattern"),
                "reasons":       signal.get("reasons", []),
                "blitz_unit":    0,
            }

            await database_service.save_swing_trade(trade_data)
            self._peak_roi_cache[trade_id] = 0.0

            logger.info(
                f"[SWING-LAB] Trade registrado: {symbol} {direction} | "
                f"Entry: {entry_price:.4f} | Stop: {stop_price:.4f} | Score: {signal.get('score', 0)}"
            )

        except Exception as e:
            logger.error(f"[SWING-LAB] Erro ao registrar trade: {e}")
            import traceback; traceback.print_exc()

    # =========================================================================
    # FLASH LOOP — atualiza ROI e stops a cada 1s (Doutrina das 10 Extracoes)
    # =========================================================================

    async def _flash_loop(self):
        """Loop principal de monitoramento de stops para o Swing Lab."""
        while self._running:
            try:
                from services.database_service import database_service
                from services.okx_ws_public import okx_ws_public_service

                active = await database_service.get_swing_trades(active_only=True)
                for trade in active:
                    try:
                        await self._update_swing_trade(trade, database_service, okx_ws_public_service)
                    except Exception as te:
                        logger.warning(f"[SWING-FLASH] Erro ao atualizar {trade.id}: {te}")

            except Exception as e:
                logger.error(f"[SWING-FLASH] Erro geral no loop: {e}")

            await asyncio.sleep(1.0)

    async def _update_swing_trade(self, trade, db, ws):
        """Atualiza ROI, stop e status de um trade Blitz ativo no Swing Lab."""
        symbol    = trade.symbol
        direction = trade.direction
        entry     = float(trade.entry_price)
        side_norm = "buy" if direction == "LONG" else "sell"

        # Preco atual
        current = float(ws.get_current_price(symbol) or trade.current_price)
        if current <= 0:
            return

        # ROI calculado com alavancagem 50x
        if side_norm == "buy":
            roi = ((current - entry) / entry) * 100.0 * SWING_LEVERAGE
        else:
            roi = ((entry - current) / entry) * 100.0 * SWING_LEVERAGE

        # Peak ROI
        peak = max(self._peak_roi_cache.get(trade.id, 0.0), roi)
        self._peak_roi_cache[trade.id] = peak

        # Stop Loss (em ROI %)
        flash_state  = dict(trade.flash_state or {})
        stop_roi     = float(flash_state.get("stop_roi", -50.0))
        current_unit = int(flash_state.get("blitz_unit", 0))
        active_level = flash_state.get("active_level", "INICIAL")
        new_unit     = current_unit
        new_stop_roi = stop_roi
        new_level    = active_level

        # Doutrina das 10 Extracoes — Step-Lock
        if roi >= 300.0 and current_unit < 3:
            new_stop_roi = 270.0
            new_unit = 3
            new_level = "UNIT3_GARANTIDO"
            logger.info(f"[SWING-UNIT3] {symbol} ROI={roi:.0f}% -> SL +270% (UNIDADE 3 GARANTIDA)")

        elif roi >= 200.0 and current_unit < 2:
            new_stop_roi = 180.0
            new_unit = 2
            new_level = "UNIT2_GARANTIDO"
            logger.info(f"[SWING-UNIT2] {symbol} ROI={roi:.0f}% -> SL +180% (UNIDADE 2 GARANTIDA)")

        elif roi >= 150.0 and current_unit < 2:
            new_stop_roi = 110.0
            new_unit = max(1, current_unit)
            new_level = "EMANCIPADO"
            logger.info(f"[SWING-EMANCIPADO] {symbol} ROI={roi:.0f}% -> SL +110%")

        elif roi >= 100.0 and current_unit < 1:
            new_stop_roi = 95.0
            new_unit = 1
            new_level = "UNIT1_GARANTIDO"
            logger.info(f"[SWING-UNIT1] {symbol} ROI={roi:.0f}% -> SL +95% (UNIDADE 1 GARANTIDA)")

        elif roi >= 70.0 and current_unit == 0:
            new_stop_roi = max(new_stop_roi, 50.0)
            new_level = "PRE_UNIT1"

        elif roi >= 30.0 and current_unit == 0:
            # Break-even padrao
            new_stop_roi = max(new_stop_roi, 0.0)
            new_level = "BREAKEVEN"

        # Recalcula preco de stop a partir do stop_roi
        stop_roi_used = new_stop_roi if new_stop_roi > stop_roi else stop_roi
        price_offset = stop_roi_used / (SWING_LEVERAGE * 100.0)
        if side_norm == "buy":
            stop_price = entry * (1 + price_offset)
        else:
            stop_price = entry * (1 - price_offset)

        # Verifica se o stop foi atingido
        stop_hit = (side_norm == "buy" and current <= stop_price) or \
                   (side_norm == "sell" and current >= stop_price)

        pnl_usd = (roi / 100.0) * SWING_MARGIN_PER_TRADE

        if stop_hit:
            # Fechar o trade
            close_level = new_level if new_level != "INICIAL" else "CLOSED_SL"
            status = "CLOSED_TRAILING" if new_stop_roi > 0 else "CLOSED_SL"
            flash_state["history"] = flash_state.get("history", []) + [{
                "ts": time.time(), "event": status, "roi": round(roi, 2),
                "level": close_level, "price": current
            }]
            await db.update_swing_trade(trade.id, {
                "status":        status,
                "current_price": current,
                "current_roi":   round(roi, 2),
                "pnl_pct":       round(roi, 2),
                "max_roi":       round(peak, 2),
                "closed_at":     time.time(),
                "flash_state": {**flash_state, "active_level": close_level, "stop_roi": stop_roi_used, "blitz_unit": new_unit},
            })
            self._peak_roi_cache.pop(trade.id, None)
            pnl_str = f"+{pnl_usd:.2f}" if pnl_usd >= 0 else f"{pnl_usd:.2f}"
            logger.info(f"[SWING-CLOSE] {symbol} {direction} {status} | ROI={roi:.1f}% | PnL=${pnl_str}")
        else:
            # Atualizar estado
            flash_state["stop_roi"]     = stop_roi_used
            flash_state["blitz_unit"]   = new_unit
            flash_state["active_level"] = new_level
            await db.update_swing_trade(trade.id, {
                "current_price": current,
                "current_roi":   round(roi, 2),
                "max_roi":       round(peak, 2),
                "stop_loss":     stop_price,
                "blitz_unit":    new_unit,
                "flash_state":   flash_state,
            })


# Instancia global
sandbox_swing_service = SandboxSwingService()
