# -*- coding: utf-8 -*-
"""
⚡ Agente Flash V1.0 — Motor Ultrarrápido de Escadinha e Emancipação
====================================================================
Monitora TODOS os slots a cada 1 segundo e reage instantaneamente
aos gatilhos da Escadinha (30% → 50% → 70% → 110% → 150%).

- SEM throttles, SEM gas checks, SEM sentinelas
- Apenas Escadinha pura + Emancipação imediata
- SL atualizado no Postgres + Firebase (fire-and-forget)
- Emancipação para Moonbag no exato momento que bate 150%

Author: 1Crypten Space V4.0
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any

from config import settings
from services.database_service import database_service
from services.okx_ws_public import okx_ws_public_service

logger = logging.getLogger("FlashAgent")

# ⚡ Escadinha de Elite — Tabela de Degraus (Padrão TREND/SWING/SNIPER)
# Formato: (roi_minimo, stop_roi_destino, label, status_risco)
ESCADINHA_DEGRAUS = [
    (150.0, 110.0, "EMANCIPACAO", "PROFIT_LOCK"),  # 150%+ → Moonbag com SL +110%
    (130.0, 105.0, "PRE_EMANCIPACAO", "PROFIT_LOCK"),  # 130%+ → Pré-emancipação
    (110.0, 80.0,  "PROFIT_LOCK", "PROFIT_LOCK"),     # 110%+ → SL +80%
    (70.0,  45.0,  "RISCO_ZERO", "RISCO_ZERO"),       # 70%+  → SL +45%
    (50.0,  25.0,  "PROFIT_BRIDGE", "SL_0"),          # 50%+  → SL +25%
    (30.0,  6.0,   "BREAKEVEN", "SL_0"),              # 30%+  → SL +6% (break-even)
]

# ⚡ Escadinha BLITZ_30M — Degraus adaptados para slots 1 e 2 (Doutrina das 10)
# UNIT1=100%, UNIT2=200%, UNIT3=300%, Emancipação em 150%
ESCADINHA_BLITZ = [
    (150.0, 110.0, "BLITZ_EMANCIPACAO", "PROFIT_LOCK"),
    (300.0, 270.0, "BLITZ_UNIT3", "MEGA_PULSE"),
    (200.0, 180.0, "BLITZ_UNIT2", "MEGA_PULSE"),
    (100.0, 95.0,  "BLITZ_UNIT1", "MEGA_PULSE"),
    (70.0,  50.0,  "BLITZ_RISCO_ZERO", "RISCO_ZERO"),
    (30.0,  5.0,   "BLITZ_BREAKEVEN", "SL_0"),
]


class FlashAgent:
    """
    ⚡ Agente Flash — Monitoramento ultrarrápido de Escadinha e Emancipação.
    Roda a cada 1 segundo, processa todos os slots em paralelo.
    Cache de slots com refresh a cada 3s para reduzir queries no banco.
    """

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self.is_running = False
        self._last_pnl_update = {}  # {slot_id: timestamp}
        self._slots_cache = []  # Cache local de slots
        self._last_slots_refresh = 0.0  # Timestamp do último refresh
        self._slots_cache_ttl = 3.0  # Refresh a cada 3s
        self.leverage = 50.0  # Alavancagem padrão Sniper

    async def start(self):
        """Inicia o loop principal do FlashAgent."""
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._flash_loop())
        logger.info("⚡ [FLASH] Agente Flash ONLINE — Monitoramento a cada 1s ativo!")

    async def stop(self):
        """Para o FlashAgent."""
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
                await self._scan_all_slots()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"⚡ [FLASH] Erro no loop: {e}")
            await asyncio.sleep(1.0)  # ⚡ 1 segundo — ultra-rápido

    async def _scan_all_slots(self):
        """Escaneia todos os 4 slots em paralelo.
        Usa cache local com refresh a cada {ttl}s para reduzir queries no banco.
        """
        now = time.time()
        if now - self._last_slots_refresh > self._slots_cache_ttl:
            self._slots_cache = await database_service.get_active_slots()
            self._last_slots_refresh = now

        slots = self._slots_cache
        if not slots:
            return

        tasks = []
        for slot in slots:
            if slot.get("symbol") and float(slot.get("entry_price", 0)) > 0:
                tasks.append(self._process_slot(slot))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _get_current_price(self, symbol: str) -> float:
        """Obtém o preço atual APENAS do WebSocket (cache local, ultra-rápido).
        Sem fallback REST para não atrasar o ciclo de 1s.
        """
        try:
            price = okx_ws_public_service.get_current_price(symbol)
            if price and price > 0:
                return price
        except Exception:
            pass
        return 0.0

    async def _process_slot(self, slot: Dict[str, Any]):
        """
        ⚡ Processa UM slot: calcula ROI, verifica Escadinha, atualiza SL, emancipa.
        Tudo em menos de 100ms.
        """
        slot_id = slot.get("id")
        symbol = slot["symbol"]
        entry_price = float(slot.get("entry_price", 0))
        current_stop = float(slot.get("current_stop", 0))
        side = (slot.get("side") or "BUY").lower()
        qty = float(slot.get("qty", 0))
        leverage = float(slot.get("leverage") or self.leverage)

        if entry_price <= 0:
            return

        # 1. Preço via WS (cache local, sem latência de rede)
        current_price = await self._get_current_price(symbol)
        if current_price <= 0:
            return  # Sem preço neste ciclo, tenta no próximo

        # 2. ROI instantâneo
        if side == "buy":
            price_diff_pct = (current_price - entry_price) / entry_price
        else:
            price_diff_pct = (entry_price - current_price) / entry_price

        roi = price_diff_pct * leverage * 100

        # 3. Atualiza PnL no banco (a cada 2s para reduzir escrita)
        now = time.time()
        last_up = self._last_pnl_update.get(slot_id, 0)
        if now - last_up >= 2.0:
            self._last_pnl_update[slot_id] = now
            pnl_diff = abs(roi - float(slot.get("pnl_percent") or 0))
            if pnl_diff > 1.0:
                asyncio.create_task(
                    database_service.update_slot(slot_id, {"pnl_percent": roi})
                )

        # 4. ⚡ Violação de Stop Loss (verificar antes de qualquer ação)

        if current_stop > 0:
            stop_hit = (side == "buy" and current_price <= current_stop) or \
                       (side == "sell" and current_price >= current_stop)
            if stop_hit:
                logger.warning(f"⚡ [FLASH-SL] {symbol} SL violado! Price=${current_price:.4f} Stop=${current_stop:.4f}")
                # Dispara fechamento via BankrollManager
                asyncio.create_task(self._close_position(slot_id, symbol, side, qty, f"FLASH_SL_{roi:.1f}%", slot))
                return

        # 5. ⚡ VERIFICAR EMANCIPAÇÃO (ROI >= 150%)
        # Nota: Não verificamos slot.status porque o model Slot no DB não tem campo 'status'.
        #       Slots emancipados são limpos (symbol=None) e já seriam pulados acima.
        if roi >= 150.0:
            logger.warning(f"🚀⚡ [FLASH-EMANCIPAR] {symbol} ROI={roi:.1f}% >= 150%! EMANCIPANDO AGORA!")
            # Calcula SL de +110% para a Moonbag
            sl_110 = await self._calc_stop_price(entry_price, 110.0, side, leverage, symbol)
            asyncio.create_task(self._emancipate_slot(slot_id, symbol, slot, sl_110))
            return

        # 6. ⚡ VERIFICAR ESCADINHA — seleciona tabela conforme slot_type
        slot_type = (slot.get("slot_type") or "SNIPER").upper()
        degraus = ESCADINHA_BLITZ if slot_type == "BLITZ_30M" else ESCADINHA_DEGRAUS

        new_stop_roi = None
        label = None
        status_risco = None

        for min_roi, stop_roi, lbl, risco in degraus:
            if roi >= min_roi:
                # Para BLITZ, ignoramos degraus de emancipação (já tratado acima)
                if slot_type == "BLITZ_30M" and lbl == "BLITZ_EMANCIPACAO":
                    continue
                new_stop_roi = stop_roi
                label = lbl
                status_risco = risco
                break  # Pega o maior degrau atingido

        if new_stop_roi is None:
            return  # Nenhum degrau atingido ainda

        # 7. Calcular preço do stop
        new_stop_price = await self._calc_stop_price(entry_price, new_stop_roi, side, leverage, symbol)
        if new_stop_price <= 0:
            return

        # 8. Verificar se o stop melhorou (Paciência Absoluta)
        stop_improved = (side == "buy" and new_stop_price > current_stop) or \
                        (side == "sell" and (current_stop == 0 or new_stop_price < current_stop))

        if not stop_improved:
            return  # Stop já está melhor ou igual

        # 9. ⚡ ATUALIZAR STOP AGORA — fire-and-forget
        logger.info(
            f"⚡ [FLASH-ESCADINHA] {symbol} ROI={roi:.1f}% → SL +{new_stop_roi:.0f}% "
            f"(${new_stop_price:.4f}) | Degrau: {label}"
        )
        asyncio.create_task(self._update_slot_sl(slot_id, symbol, new_stop_price, status_risco, side, qty))

    async def _calc_stop_price(self, entry_price: float, stop_roi: float, side: str,
                                leverage: float, symbol: str) -> float:
        """Calcula o preço do stop a partir do ROI desejado."""
        price_offset_pct = stop_roi / (leverage * 100)
        if side == "buy":
            new_stop = entry_price * (1 + price_offset_pct)
        else:
            new_stop = entry_price * (1 - price_offset_pct)

        # Arredondar para o tick size correto
        try:
            from services.okx_rest import okx_rest_service
            new_stop = await okx_rest_service.round_price(symbol, new_stop)
        except Exception:
            pass
        return new_stop

    async def _update_slot_sl(self, slot_id: int, symbol: str, sl_price: float,
                               status_risco: str, side: str, qty: float):
        """
        ⚡ Atualiza o Stop Loss no Postgres e no Paper Memory.
        Fire-and-forget para não travar o ciclo de 1s.
        """
        update_payload = {
            "current_stop": sl_price,
            "status_risco": status_risco,
        }

        # 1. Postgres (SSOT)
        await database_service.update_slot(slot_id, update_payload)

        # 2. Paper Memory (se aplicável)
        try:
            from services.okx_rest import okx_rest_service
            if okx_rest_service.execution_mode == "PAPER":
                norm_symbol = okx_rest_service.normalize_symbol(symbol)
                pos = next(
                    (p for p in okx_rest_service.paper_positions
                     if okx_rest_service.normalize_symbol(p.get("symbol", "")) == norm_symbol),
                    None
                )
                if pos:
                    pos["stopLoss"] = str(sl_price)
                    await okx_rest_service._save_paper_state()
        except Exception as e:
            logger.warning(f"⚡ [FLASH] Paper state update fail (non-critical): {e}")

        # 3. Firebase (fire-and-forget)
        try:
            from services.firebase_service import firebase_service
            slot_state = await firebase_service.get_slot(slot_id)
            if slot_state and slot_state.get("symbol"):
                await firebase_service.update_slot(slot_id, update_payload)
        except Exception:
            pass  # Firebase falha não crítica

    async def _emancipate_slot(self, slot_id: int, symbol: str, slot: Dict[str, Any], sl_price: float):
        """
        🚀⚡ EMANCIPAÇÃO IMEDIATA: Move posição para Moonbag e libera o slot.
        Tudo em paralelo para ser o mais rápido possível.
        """
        try:
            # 1. Primeiro, atualiza o stop no paper memory para proteger o lucro
            try:
                from services.okx_rest import okx_rest_service
                if okx_rest_service.execution_mode == "PAPER":
                    norm_sym = okx_rest_service.normalize_symbol(symbol)
                    pos = next(
                        (p for p in okx_rest_service.paper_positions
                         if okx_rest_service.normalize_symbol(p.get("symbol", "")) == norm_sym),
                        None
                    )
                    if pos:
                        pos["stopLoss"] = str(sl_price)
            except Exception:
                pass

            # 2. Promote no Postgres (libera slot + cria Moonbag atômicamente)
            await database_service.promote_to_moonbag(slot_id)

            # 3. Log
            logger.info(f"🚀⚡ [FLASH] {symbol} EMANCIPADO! Slot {slot_id} LIVRE. Moonbag criada.")

        except Exception as e:
            logger.error(f"⚡ [FLASH] Erro na emancipação de {symbol}: {e}")

    async def _close_position(self, slot_id: int, symbol: str, side: str, qty: float,
                               reason: str, slot: Dict[str, Any]):
        """Dispara fechamento de posição por stop loss."""
        try:
            from services.okx_rest import okx_rest_service
            await okx_rest_service.close_position(symbol, side, qty, reason=reason)
            # Libera o slot
            await database_service.update_slot(slot_id, {
                "symbol": None, "entry_price": 0, "current_stop": 0,
                "qty": 0, "pnl_percent": 0, "status_risco": "LIVRE"
            })
            logger.warning(f"🛑⚡ [FLASH] {symbol} FECHADO por SL. Motivo: {reason}")
        except Exception as e:
            logger.error(f"⚡ [FLASH] Erro ao fechar {symbol}: {e}")


# Instância global
flash_agent = FlashAgent()
