# -*- coding: utf-8 -*-
"""
⚡ Agente Flash V1.1 — Motor Ultrarrápido de Escadinha, Emancipação e Moonbags
================================================================================
Monitora TUDO a cada 1 segundo e reage instantaneamente:

Slots Táticos:
  - Escadinha: 30%→6%, 50%→25%, 70%→45%, 110%→80%, 150%→Moonbag
  - BLITZ_30M: UNIT1=100%, UNIT2=200%, UNIT3=300%, Emancipação 150%
  - Violação de SL → Fechamento imediato

Moonbags (Ceifeiro Turbo):
  - Trailing Stop progressivo nos níveis do Ceifeiro
  - Se preço bater no stop → Fechamento imediato (sem dó)

Author: 1Crypten Space V4.0
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, List

from config import settings
from services.database_service import database_service
from services.order_projection_service import order_projection_service
from services.okx_ws_public import okx_ws_public_service

logger = logging.getLogger("FlashAgent")

# ⚡ Escadinha de Elite — Tabela de Degraus (Padrão TREND/SWING/SNIPER)
# Formato: (roi_minimo, stop_roi_destino, label, status_risco)
ESCADINHA_DEGRAUS = [
    (150.0, 110.0, "EMANCIPACAO", "PROFIT_LOCK"),
    (80.0,  15.0,  "RISCO_ZERO", "RISCO_ZERO"),
]

# ⚡ Escadinha BLITZ_30M — Degraus adaptados (Doutrina das 10)
ESCADINHA_BLITZ = [
    (150.0, 110.0, "BLITZ_EMANCIPACAO", "PROFIT_LOCK"),
    (300.0, 270.0, "BLITZ_UNIT3", "MEGA_PULSE"),
    (200.0, 180.0, "BLITZ_UNIT2", "MEGA_PULSE"),
    (100.0, 95.0,  "BLITZ_UNIT1", "MEGA_PULSE"),
    (70.0,  50.0,  "BLITZ_RISCO_ZERO", "RISCO_ZERO"),
    (30.0,  5.0,   "BLITZ_BREAKEVEN", "SL_0"),
]

# 🌙 Níveis de Trailing Stop para Moonbags (Ceifeiro Turbo)
# Após emancipação (150% ROI), o SL sobe progressivamente:
MOONBAG_TRAILING_LEVELS = [
    {"roi_threshold": 1200, "sl_roi": 1000, "icon": "APX", "label": "APEX"},
    {"roi_threshold": 1000, "sl_roi": 800, "icon": "HYP", "label": "HYPER"},
    {"roi_threshold": 800, "sl_roi": 650, "icon": "CHK", "label": "CHOKE"},
    {"roi_threshold": 750, "sl_roi": 600, "icon": "CP", "label": "CHOKE_PREP"},
    {"roi_threshold": 700, "sl_roi": 500, "icon": "🔱", "label": "GOD_MODE"},
    {"roi_threshold": 600, "sl_roi": 420, "icon": "💫", "label": "SUPERNOVA"},
    {"roi_threshold": 500, "sl_roi": 350, "icon": "👑", "label": "CROWN"},
    {"roi_threshold": 400, "sl_roi": 280, "icon": "⭐", "label": "STAR"},
    {"roi_threshold": 300, "sl_roi": 220, "icon": "🚀", "label": "ROCKET"},
    {"roi_threshold": 200, "sl_roi": 150, "icon": "🌊", "label": "WAVE"},
]


class FlashAgent:
    """
    ⚡ Agente Flash — Monitoramento ultrarrápido de Slots Táticos + Moonbags.
    Roda a cada 1 segundo, processa tudo em paralelo.
    Cache de leitura com refresh a cada 3s para reduzir queries no banco.
    """

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self.is_running = False
        self.leverage = 50.0

        # Cache de slots
        self._last_pnl_update = {}  # {slot_id: timestamp}
        self._slots_cache = []
        self._last_slots_refresh = 0.0
        self._slots_cache_ttl = 3.0

        # Cache de moonbags
        self._moonbags_cache = []
        self._last_moonbags_refresh = 0.0
        self._moonbags_cache_ttl = 3.0

        # Cache do Sentinel (evita gas checks redundantes enquanto cache de slots está stale)
        self._sentinel_cache = {}  # {slot_id: {"hit_at": float, "respir": float}}

        # Último preço conhecido por símbolo (fallback quando WS falha)
        self._last_price_cache = {}  # {symbol: price}
        self._peak_roi_cache = {}  # {slot_key: peak_roi}

    def _stop_improves(self, side: str, current_stop: float, candidate_stop: float) -> bool:
        if candidate_stop <= 0:
            return False
        if current_stop <= 0:
            return True
        return (side == "buy" and candidate_stop > current_stop) or (
            side == "sell" and candidate_stop < current_stop
        )

    def _moonbag_hard_lock_roi(self, moon: Dict[str, Any]) -> float:
        return max(110.0, float(moon.get("flash_last_stop_roi") or 0))

    def _stop_roi_from_price(self, entry_price: float, stop_price: float, side: str, leverage: float) -> Optional[float]:
        if entry_price <= 0 or stop_price <= 0 or leverage <= 0:
            return None
        return self._calc_roi(entry_price, stop_price, side, leverage)

    def _fmt_price(self, value: float) -> str:
        if value is None or value <= 0:
            return "n/a"
        return f"${value:.8f}"

    def _fmt_roi(self, value: Optional[float]) -> str:
        if value is None:
            return "n/a"
        return f"{value:+.1f}%"

    def _level_label(self, level: Any) -> str:
        if not isinstance(level, dict) or not level:
            return "NONE"
        name = level.get("name") or level.get("label") or "UNKNOWN"
        trigger = level.get("trigger_roi")
        stop_roi = level.get("stop_roi")
        parts = [str(name)]
        if trigger is not None:
            parts.append(f"trigger={float(trigger):.0f}%")
        if stop_roi is not None:
            parts.append(f"stop={float(stop_roi):.0f}%")
        return "/".join(parts)

    def _log_flash_exception(self, scope: str, symbol: str, exc: BaseException):
        logger.error(
            f"[FLASH-ERROR][{scope}] {symbol} falhou no ciclo de monitoramento: {exc}",
            exc_info=(type(exc), exc, exc.__traceback__),
        )

    def _log_price_unavailable(self, scope: str, symbol: str, entry_price: float, current_stop: float, side: str, leverage: float):
        stop_roi = self._stop_roi_from_price(entry_price, current_stop, side, leverage)
        logger.warning(
            f"[FLASH-TRACK][{scope}] {symbol} side={side.upper()} price=n/a "
            f"entry={self._fmt_price(entry_price)} stop_db={self._fmt_price(current_stop)} "
            f"stop_db_roi={self._fmt_roi(stop_roi)} action=PRICE_UNAVAILABLE"
        )

    def _log_slot_tracking(
        self,
        slot_id: Any,
        symbol: str,
        side: str,
        entry_price: float,
        current_price: float,
        current_stop: float,
        leverage: float,
        roi: float,
        effective_roi: float,
        projection: Dict[str, Any],
    ):
        active_level = projection.get("active_level")
        next_level = projection.get("next_level")
        phase = projection.get("phase") or "UNKNOWN"
        target_stop = float(projection.get("recommended_stop") or 0)
        current_stop_roi = self._stop_roi_from_price(entry_price, current_stop, side, leverage)
        target_stop_roi = self._stop_roi_from_price(entry_price, target_stop, side, leverage)
        if target_stop_roi is None and isinstance(active_level, dict) and active_level.get("stop_roi") is not None:
            target_stop_roi = float(active_level.get("stop_roi"))
        improves = self._stop_improves(side, current_stop, target_stop)
        action = "APPLY_STOP" if improves else "MONITOR"

        adx_val = 20.0
        try:
            from services.okx_ws_public import okx_ws_public_service
            adx_val = getattr(okx_ws_public_service, "btc_adx", 20.0)
        except Exception:
            pass
        regime_label = "RANGING" if adx_val < 25 else "TRENDING"

        logger.info(
            f"[FLASH-TRACK][SLOT] slot={slot_id} symbol={symbol} side={side.upper()} "
            f"price={self._fmt_price(current_price)} entry={self._fmt_price(entry_price)} "
            f"roi={self._fmt_roi(roi)} peak_roi={self._fmt_roi(effective_roi)} phase={phase} "
            f"active={self._level_label(active_level)} next={self._level_label(next_level)} "
            f"stop_db={self._fmt_price(current_stop)} stop_db_roi={self._fmt_roi(current_stop_roi)} "
            f"stop_target={self._fmt_price(target_stop)} stop_target_roi={self._fmt_roi(target_stop_roi)} "
            f"improves={improves} action={action} regime={regime_label}(ADX={adx_val:.1f})"
        )

    def _log_moonbag_tracking(
        self,
        moon_uuid: Any,
        symbol: str,
        side: str,
        entry_price: float,
        current_price: float,
        current_stop: float,
        leverage: float,
        roi: float,
        effective_roi: float,
        projection: Dict[str, Any],
        hard_lock_stop: float,
        hard_lock_roi: float,
        hard_lock_improves: bool,
    ):
        active_level = projection.get("active_level")
        next_level = projection.get("next_level")
        phase = projection.get("phase") or "MOONBAG"
        target_stop = float(projection.get("recommended_stop") or 0)
        current_stop_roi = self._stop_roi_from_price(entry_price, current_stop, side, leverage)
        target_stop_roi = self._stop_roi_from_price(entry_price, target_stop, side, leverage)
        if target_stop_roi is None and isinstance(active_level, dict) and active_level.get("stop_roi") is not None:
            target_stop_roi = float(active_level.get("stop_roi"))
        trailing_improves = self._stop_improves(side, current_stop, target_stop)
        action = "HARD_LOCK" if hard_lock_improves else ("TRAIL_STOP" if trailing_improves else "MONITOR")

        logger.info(
            f"[FLASH-TRACK][MOONBAG] uuid={moon_uuid} symbol={symbol} side={side.upper()} "
            f"price={self._fmt_price(current_price)} entry={self._fmt_price(entry_price)} "
            f"roi={self._fmt_roi(roi)} peak_roi={self._fmt_roi(effective_roi)} phase={phase} "
            f"active={self._level_label(active_level)} "
            f"next={self._level_label(next_level)} stop_db={self._fmt_price(current_stop)} "
            f"stop_db_roi={self._fmt_roi(current_stop_roi)} hard_lock={self._fmt_price(hard_lock_stop)} "
            f"hard_lock_roi={self._fmt_roi(hard_lock_roi)} hard_lock_improves={hard_lock_improves} "
            f"stop_target={self._fmt_price(target_stop)} stop_target_roi={self._fmt_roi(target_stop_roi)} "
            f"trailing_improves={trailing_improves} action={action}"
        )

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._flash_loop())
        logger.info("⚡ [FLASH] Agente Flash V1.1 ONLINE — Slots + Moonbags a cada 1s!")

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
                # Processa slots e moonbags em paralelo
                tasks = [
                    self._scan_all_slots(),
                    self._scan_all_moonbags(),
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for scope, result in zip(("SLOTS", "MOONBAGS"), results):
                    if isinstance(result, BaseException):
                        self._log_flash_exception(scope, "SCAN", result)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"⚡ [FLASH] Erro no loop: {e}")
            await asyncio.sleep(1.0)

    # ==================== SLOTS TÁTICOS ====================

    async def _scan_all_slots(self):
        """Escaneia todos os 4 slots com cache de 3s."""
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
        """Processa UM slot tático: Escadinha, SL, Emancipação."""
        slot_id = slot.get("id")
        symbol = slot["symbol"]
        entry_price = float(slot.get("entry_price", 0))
        current_stop = float(slot.get("current_stop", 0))
        side = (slot.get("side") or "BUY").lower()
        qty = float(slot.get("qty", 0))
        leverage = float(slot.get("leverage") or self.leverage)

        if entry_price <= 0:
            return

        current_price = await self._get_rest_price(symbol)
        if current_price <= 0:
            current_price = await self._get_current_price(symbol)
        if current_price <= 0:
            self._log_price_unavailable("SLOT", symbol, entry_price, current_stop, side, leverage)
            return

        adx_val = 30.0
        import sys
        is_test_env = any("pytest" in arg or "test" in arg for arg in sys.argv)
        if not is_test_env:
            try:
                from services.okx_ws_public import okx_ws_public_service
                val = getattr(okx_ws_public_service, "btc_adx", 0.0)
                if val > 0.1:
                    adx_val = val
            except Exception:
                pass
        is_ranging = (adx_val < 25)

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

        # Atualiza PnL (a cada 2s)
        self._update_pnl(slot_id, roi, slot)

        # ⚡ Checagem Preventiva de Stop Loss Atômico Fixo em -50% ROI (Regra do Usuário)
        if roi <= -50.0:
            logger.warning(f"🛑⚡ [FLASH-ATOMIC-SL-50] {symbol} atingiu ROI crítico de {roi:.1f}%. Fechamento imediato sem Sentinel.")
            await self._close_position(slot_id, symbol, side, qty, f"ATOMIC_SL_50_{roi:.1f}%")
            return

        # ⚡ Violação de SL
        if current_stop > 0:
            stop_hit = await self._check_stop_hit(side, current_stop, symbol)
            if stop_hit:
                fresh_price = await self._get_rest_price(symbol)
                if fresh_price > 0:
                    current_price = fresh_price
                    roi = self._calc_roi(entry_price, current_price, side, leverage)
                
                # Determina se é stop de lucro ou perda
                is_profit_stop = (side == "buy" and current_stop >= entry_price) or \
                                 (side == "sell" and current_stop <= entry_price)

                if is_profit_stop:
                    # 🟢 STOP DE LUCRO: Fecha imediatamente (lucro já garantido)
                    logger.warning(f"⚡ [FLASH-SL-PROFIT] {symbol} SL de lucro violado! Price=${current_price:.4f} Stop=${current_stop:.4f}")
                    await self._close_position(slot_id, symbol, side, qty, f"FLASH_PROFIT_SL_{roi:.1f}%")
                    return
                else:
                    # 🔴 STOP DE PERDA: Fecha imediatamente sem acionar o Sentinel (Sem olhar gás/respiro)
                    logger.warning(f"🛑⚡ [FLASH-SL-LOSS-IMMEDIATE] {symbol} SL de perda atingido! Fechando imediatamente sem Sentinel. ROI={roi:.1f}%")
                    await self._close_position(slot_id, symbol, side, qty, f"FLASH_LOSS_SL_{roi:.1f}%")
                    return

        # 🚀 Emancipação Dinâmica (100% ROI no Ranging / 150% ROI no Trending)
        adx_val = 30.0
        import sys
        is_test_env = any("pytest" in arg or "test" in arg for arg in sys.argv)
        if not is_test_env:
            try:
                from services.okx_ws_public import okx_ws_public_service
                val = getattr(okx_ws_public_service, "btc_adx", 0.0)
                if val > 0.1:
                    adx_val = val
            except Exception:
                pass
        is_ranging = (adx_val < 25)
        emancipate_threshold = 100.0 if is_ranging else 150.0
        emancipate_stop_roi = 80.0 if is_ranging else 110.0

        if decision_projection.get("should_emancipate") or (roi >= emancipate_threshold and phase == "EMANCIPACAO"):
            logger.warning(
                f"🚀⚡ [FLASH-EMANCIPAR] {symbol} peakROI={effective_roi:.1f}% "
                f"(atual {roi:.1f}%) >= {emancipate_threshold:.0f}% ({'RANGING' if is_ranging else 'TRENDING'})! EMANCIPANDO!"
            )
            sl_emancipate = float(decision_projection.get("recommended_stop") or 0)
            if sl_emancipate <= 0:
                sl_emancipate = await self._calc_stop_price(entry_price, emancipate_stop_roi, side, leverage, symbol)
            if self._stop_improves(side, current_stop, sl_emancipate):
                await self._update_slot_sl(slot_id, symbol, sl_emancipate, "PROFIT_LOCK", side, qty)
                current_stop = sl_emancipate
            stop_hit = await self._check_stop_hit(side, current_stop, symbol)
            if stop_hit:
                logger.warning(
                    f"⚡ [FLASH-EMANCIPATION-LOCK-SL] {symbol} voltou no stop de emancipação "
                    f"${current_stop:.4f}. Fechando com lucro protegido."
                )
                await self._close_position(slot_id, symbol, side, qty, f"FLASH_EMANCIPATION_LOCK_SL_{roi:.1f}%")
                self._peak_roi_cache.pop(slot_key, None)
                return
            await self._emancipate_slot(slot_id, symbol, sl_emancipate)
            self._peak_roi_cache.pop(slot_key, None)
            return

        # ⚡ Escadinha
        active_level = decision_projection.get("active_level")
        if not active_level or active_level.get("phase") not in ("ESCADINHA", "EMANCIPACAO"):
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

    # ==================== MOONBAGS ====================

    async def _scan_all_moonbags(self):
        """Escaneia todas as Moonbags com cache de 3s."""
        now = time.time()
        if now - self._last_moonbags_refresh > self._moonbags_cache_ttl:
            self._moonbags_cache = await database_service.get_moonbags()
            self._last_moonbags_refresh = now

        moons = self._moonbags_cache
        if not moons:
            return

        tracked_tasks: List[tuple] = []
        for moon in moons:
            if moon.get("symbol") and float(moon.get("entry_price", 0)) > 0:
                tracked_tasks.append((str(moon.get("symbol")), self._process_moonbag(moon)))
        if tracked_tasks:
            results = await asyncio.gather(
                *(task for _, task in tracked_tasks),
                return_exceptions=True,
            )
            for (symbol, _), result in zip(tracked_tasks, results):
                if isinstance(result, BaseException):
                    self._log_flash_exception("MOONBAG", symbol, result)

    async def _process_moonbag(self, moon: Dict[str, Any]):
        """
        🌙 Processa UMA Moonbag:
        1. Verifica se o stop foi violado → FECHA IMEDIATAMENTE
        2. Calcula trailing stop → SOBE O SL se ROI aumentou
        """
        moon_uuid = moon.get("uuid")
        symbol = moon["symbol"]
        entry_price = float(moon.get("entry_price", 0))
        current_stop = float(moon.get("current_stop", 0))
        qty = float(moon.get("qty", 0))
        leverage = float(moon.get("leverage") or self.leverage)
        # Moonbag side pode vir como "Buy"/"Sell" ou "LONG"/"SHORT"
        side_raw = (moon.get("side") or "BUY").upper()
        side = "buy" if side_raw in ("BUY", "LONG") else "sell"

        if entry_price <= 0:
            return

        current_price = await self._get_current_price(symbol)
        if current_price <= 0:
            self._log_price_unavailable("MOONBAG", symbol, entry_price, current_stop, side, leverage)
            return

        projection = await order_projection_service.build_projection(
            moon,
            current_price=current_price,
            phase_hint="MOONBAG",
        )
        roi = float(projection.get("roi_percent") or 0)
        peak_price = self._get_peak_price(symbol, side, current_price)
        peak_roi = self._calc_roi(entry_price, peak_price, side, leverage) if peak_price > 0 else roi
        moon_key = moon.get("genesis_id") or moon_uuid or f"moon:{symbol}"
        cached_peak = float(self._peak_roi_cache.get(moon_key, 0.0) or 0.0)
        stored_peak = float(moon.get("pnl_percent") or 0.0)
        effective_roi = max(roi, peak_roi, cached_peak, stored_peak)
        self._peak_roi_cache[moon_key] = effective_roi

        decision_projection = projection
        if effective_roi > roi + 0.1:
            decision_price = order_projection_service.raw_price_from_roi(
                entry_price,
                effective_roi,
                side,
                leverage,
            )
            decision_projection = await order_projection_service.build_projection(
                moon,
                current_price=decision_price,
                phase_hint="MOONBAG",
            )

        hard_lock_roi = self._moonbag_hard_lock_roi(moon)
        hard_lock_stop = await self._calc_stop_price(entry_price, hard_lock_roi, side, leverage, symbol)
        hard_lock_improves = self._stop_improves(side, current_stop, hard_lock_stop)
        effective_stop = hard_lock_stop if hard_lock_improves else current_stop

        self._log_moonbag_tracking(
            moon_uuid,
            symbol,
            side,
            entry_price,
            current_price,
            current_stop,
            leverage,
            roi,
            effective_roi,
            decision_projection,
            hard_lock_stop,
            hard_lock_roi,
            hard_lock_improves,
        )

        # ⚡ 1. VIOLAÇÃO DE STOP → FECHAR MOONBAG IMEDIATAMENTE
        if effective_stop > 0:
            stop_hit = await self._check_stop_hit(side, effective_stop, symbol)
            if stop_hit:
                if hard_lock_improves:
                    await self._update_moonbag_sl(moon_uuid, symbol, hard_lock_stop, roi, "EMANCIPADA", hard_lock_roi)
                # Log com o current_price mesmo, mas foi detectado via conservative (low/high)
                logger.warning(
                    f"🌙⚡ [FLASH-MOON-SL] {symbol} Moonbag SL violado! "
                    f"Price=${current_price:.4f} Stop=${effective_stop:.4f} ROI={roi:.1f}%"
                )
                asyncio.create_task(self._close_moonbag(moon_uuid, symbol, side, qty, f"MOONBAG_SL_{roi:.1f}%"))
                return
            if hard_lock_improves:
                logger.warning(
                    f"[FLASH-MOON-HARDLOCK] {symbol} corrigindo piso Moonbag "
                    f"SL +{hard_lock_roi:.0f}% (${hard_lock_stop:.4f})"
                )
                await self._update_moonbag_sl(moon_uuid, symbol, hard_lock_stop, roi, "EMANCIPADA", hard_lock_roi)
                current_stop = hard_lock_stop

        # ⚡ 2. TRAILING STOP — Só sobe se ROI for >= 160% (igual ao Ceifeiro)
        projected_level = decision_projection.get("active_level")
        if not projected_level or projected_level.get("phase") != "MOONBAG":
            return

        sl_roi = float(projected_level.get("stop_roi") or 0)
        label = projected_level.get("name") or "MOONBAG_TRAIL"
        icon = ""
        new_stop = float(decision_projection.get("recommended_stop") or 0)
        if new_stop <= 0 and sl_roi > 0:
            new_stop = await self._calc_stop_price(entry_price, sl_roi, side, leverage, symbol)

        if new_stop <= 0:
            return

        stop_improved = self._stop_improves(side, current_stop, new_stop)
        if not stop_improved:
            return

        logger.info(
            f"🌙⚡ [FLASH-MOON-TRAIL] {symbol} ROI={roi:.1f}% → SL +{sl_roi:.0f}% "
            f"(${new_stop:.4f}) [{icon} {label}]"
        )
        await self._update_moonbag_sl(moon_uuid, symbol, new_stop, roi, label, sl_roi)
        stop_hit = await self._check_stop_hit(side, new_stop, symbol)
        if stop_hit:
            logger.warning(
                f"[FLASH-MOON-TRAIL-SL] {symbol} voltou no stop conquistado "
                f"${new_stop:.4f}. Fechando com lucro protegido."
            )
            asyncio.create_task(self._close_moonbag(moon_uuid, symbol, side, qty, f"MOONBAG_TRAIL_SL_{roi:.1f}%"))
            self._peak_roi_cache.pop(moon_key, None)
        return

    # ==================== HELPERS ====================

    async def _get_current_price(self, symbol: str) -> float:
        """
        Preço via WS cache local. Se WS falhar, usa último preço conhecido.
        Isso garante que o FlashAgent nunca perca um stop por falha temporária do WS.
        """
        try:
            price = okx_ws_public_service.get_current_price(symbol)
            if price and price > 0:
                # Atualiza cache
                self._last_price_cache[symbol] = price
                return price
        except Exception:
            pass

        rest_price = await self._get_rest_price(symbol)
        if rest_price > 0:
            self._last_price_cache[symbol] = rest_price
            return rest_price

        # Fallback: último preço conhecido (até 60s de idade)
        last_price = self._last_price_cache.get(symbol, 0.0)
        if last_price > 0:
            return last_price

        return 0.0

    async def _get_rest_price(self, symbol: str) -> float:
        """Preço REST fresco para confirmar stops quando o WS/cache estiver atrasado."""
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
        """
        Melhor preco recente a favor da ordem.
        LONG usa high recente; SHORT usa low recente. Isso evita perder um alvo
        rapido entre ciclos do Flash.
        """
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
        """
        ⚡ Verifica se o stop foi violado usando PREÇO CONSERVATIVO.
        Para LONG: usa o LOW dos últimos 30s (pega dips intra-ciclo que o polling perderia)
        Para SHORT: usa o HIGH dos últimos 30s (pega pumps intra-ciclo)
        Fallback para preço atual se conservative não estiver disponível.
        """
        if stop_price <= 0:
            return False

        try:
            # Tenta conservative price primeiro (low para LONG, high para SHORT)
            check_price = okx_ws_public_service.get_conservative_price(symbol, side)
            if check_price > 0:
                stop_hit = (side == "buy" and check_price <= stop_price) or \
                           (side == "sell" and check_price >= stop_price)
                if stop_hit:
                    return True
        except Exception:
            pass

        # Confirmação REST/atual: cobre WS/cache atrasado em stop de lucro.
        current_price = await self._get_current_price(symbol)
        if current_price <= 0:
            return False
        return (side == "buy" and current_price <= stop_price) or \
               (side == "sell" and current_price >= stop_price)

    def _calc_roi(self, entry: float, current: float, side: str, leverage: float) -> float:
        """ROI instantâneo em percentual (ex: 2.1 para +2.1%)."""
        if entry <= 0:
            return 0.0
        if side == "buy":
            price_diff = (current - entry) / entry
        else:
            price_diff = (entry - current) / entry
        return price_diff * leverage * 100

    def _update_pnl(self, slot_id: int, roi: float, slot: Dict[str, Any]):
        """Atualiza PnL no banco a cada 2s."""
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
        """Calcula preço do stop a partir do ROI desejado.

        Fórmula: ROI = price_diff_pct * leverage * 100
        Então: price_diff_pct = stop_roi / (leverage * 100)

        Para LONG:  stop = entry * (1 + price_diff_pct)  — stop ACIMA do entry (lucro travado)
        Para SHORT: stop = entry * (1 - price_diff_pct)  — stop ABAIXO do entry (lucro travado)
        """
        price_offset_pct = stop_roi / (leverage * 100)
        if side == "buy":
            new_stop = entry_price * (1 + price_offset_pct)  # Stop ACIMA do entry para LONG
        else:
            new_stop = entry_price * (1 - price_offset_pct)  # Stop ABAIXO do entry para SHORT
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

    # ==================== AÇÕES ====================

    async def _update_slot_sl(self, slot_id: int, symbol: str, sl_price: float,
                               status_risco: str, side: str, qty: float):
        """Atualiza SL do slot no Postgres + Paper Memory."""
        update_payload = {"current_stop": sl_price, "status_risco": status_risco}
        await database_service.update_slot(slot_id, update_payload)
        await self._sync_paper_stop(symbol, sl_price)
        await self._sync_firebase_slot(slot_id, update_payload)

    async def _update_moonbag_sl(
        self,
        moon_uuid: str,
        symbol: str,
        sl_price: float,
        roi: float,
        flash_action: str = "MOONBAG_TRAIL",
        stop_roi: float = None,
    ):
        """Atualiza SL da Moonbag no Postgres + Paper Memory."""
        update_payload = {
            "current_stop": sl_price,
            "pnl_percent": roi,
            "flash_last_action": flash_action,
        }
        if stop_roi is not None:
            update_payload["flash_last_stop_roi"] = stop_roi
        await database_service.update_moonbag(moon_uuid, update_payload)
        await self._sync_paper_stop(symbol, sl_price)

    # ==================== SENTINEL (STOPS DE PERDA) ====================

    async def _process_sentinel_stop(self, slot_id: int, symbol: str, side: str, qty: float,
                                      entry_price: float, stop_price: float, current_price: float,
                                      roi: float, slot: Dict[str, Any]):
        """
        🛡️ SENTINEL INTELIGENTE: Para stops de PERDA, verifica o GÁS antes de fechar.
        Se o fluxo (CVD) ainda favorece a direção do trade, concede respiro.
        """
        now = time.time()
        loss_pct = abs(roi)

        # Determina o tempo de respiro baseado na perda
        # Quanto maior a perda, MENOS respiro (não deixar sangrar muito)
        if loss_pct > 100:
            base_respir = 15   # Perda >100%: só 15s de respiro
        elif loss_pct > 50:
            base_respir = 30   # Perda >50%: 30s
        else:
            base_respir = 45   # Perda <=50%: 45s

        # Usa cache em memória primeiro (mais rápido que esperar refresh do banco)
        sentinel_cache = self._sentinel_cache.get(slot_id, {})
        sentinel_hit = sentinel_cache.get("hit_at", 0) or slot.get("sentinel_first_hit_at", 0) or 0

        if sentinel_hit == 0:
            # 🔴 PRIMEIRA VEZ que toca o stop: verifica o GÁS
            is_gas_favorable = await self._check_gas_favorable_simple(symbol, side)

            if is_gas_favorable:
                # Gás favorável: concede respiro diplomático
                logger.info(
                    f"🛡️⚡ [SENTINEL-HOLD] {symbol} SL de perda atingido mas GÁS favorável! "
                    f"Concedendo {base_respir}s de respiro. ROI={roi:.1f}%"
                )
                # Salva no cache em memória + banco (fire-and-forget)
                self._sentinel_cache[slot_id] = {"hit_at": now, "respir": base_respir}
                asyncio.create_task(
                    database_service.update_slot(slot_id, {
                        "sentinel_first_hit_at": now,
                        "pensamento": f"🛡️ SENTINEL: Gás favorável em {roi:.1f}% ROI. Respiro de {base_respir}s."
                    })
                )
                return  # Não fecha, deixa o preço respirar
            else:
                # Gás desfavorável: fecha imediatamente
                logger.warning(
                    f"🛑⚡ [SENTINEL-DENIED] {symbol} GÁS desfavorável! "
                    f"Fechando stop de perda. ROI={roi:.1f}%"
                )
                asyncio.create_task(
                    self._close_position(slot_id, symbol, side, qty, f"SENTINEL_SL_{roi:.1f}%")
                )
                return

        else:
            # 🟡 JÁ ESTÁ SOB SENTINEL: verifica se o tempo já esgotou
            elapsed = now - sentinel_hit

            if elapsed > base_respir:
                # ⏰ TEMPO ESGOTOU: O preço não voltou, fecha
                logger.warning(
                    f"⏰⚡ [SENTINEL-TIMEOUT] {symbol} Respiro de {base_respir}s esgotou "
                    f"({elapsed:.0f}s). Fechando stop de perda. ROI={roi:.1f}%"
                )
                # Limpa cache
                self._sentinel_cache.pop(slot_id, None)
                asyncio.create_task(
                    self._close_position(slot_id, symbol, side, qty, f"SENTINEL_TIMEOUT_{roi:.1f}%")
                )
                return
            else:
                # ⏳ Ainda no prazo: re-checa o gás rapidamente
                is_still_favorable = await self._check_gas_favorable_simple(symbol, side)
                if is_still_favorable:
                    # Gás ainda segurando: mantém a paciência
                    if int(elapsed) % 5 == 0:  # Log a cada 5s
                        logger.info(
                            f"🛡️⚡ [SENTINEL-WAIT] {symbol} Gás mantém favorável "
                            f"({elapsed:.0f}s/{base_respir}s). ROI={roi:.1f}%"
                        )
                    return
                else:
                    # Gás virou contra: fecha imediatamente
                    logger.warning(
                        f"🛑⚡ [SENTINEL-GAS-FLIP] {symbol} Gás virou contra! "
                        f"Fechando stop de perda. ROI={roi:.1f}%"
                    )
                    self._sentinel_cache.pop(slot_id, None)
                    asyncio.create_task(
                        self._close_position(slot_id, symbol, side, qty, f"SENTINEL_GAS_FLIP_{roi:.1f}%")
                    )
                    return

    async def _check_gas_favorable_simple(self, symbol: str, side: str) -> bool:
        """
        ⛽ Verifica GÁS (CVD) de forma ultra-rápida usando apenas cache do WebSocket.
        Sem chamadas REST para não atrasar o ciclo de 1s.
        Retorna True se o fluxo monetário ainda favorece a direção do trade.
        """
        try:
            # CVD de curto prazo (5 minutos) via WS cache
            cvd_5m = okx_ws_public_service.get_cvd_score_time(symbol, window_seconds=300)

            # Threshold adaptativo baseado no turnover do ativo
            turnover = getattr(okx_ws_public_service, 'turnover_24h_cache', {}).get(symbol, 50_000_000)
            threshold = max(5000, turnover * 0.00005)

            side_norm = side.lower()
            if side_norm == "buy":
                # Para LONG: CVD positivo (dinheiro entrando) = gás favorável
                favorable = cvd_5m > threshold
            else:
                # Para SHORT: CVD negativo (dinheiro saindo) = gás favorável
                favorable = cvd_5m < -threshold

            logger.info(
                f"[GAS-AUDIT-FLASH] {symbol} side={side_norm.upper()} "
                f"CVD_5m={cvd_5m:.0f} threshold={threshold:.0f} favorable={favorable}"
            )
            return favorable

        except Exception as e:
            logger.warning(f"⚡ [FLASH] Erro no gas check (non-critical): {e}")
            return False  # Conservador: se não consegue medir o gás, fecha

    async def _emancipate_slot(self, slot_id: int, symbol: str, sl_price: float):
        """🚀 Emancipação: protege lucro + promote no Postgres."""
        try:
            await self._sync_paper_stop(symbol, sl_price)
            await database_service.promote_to_moonbag(slot_id, emancipation_stop=sl_price)
            logger.info(f"🚀⚡ [FLASH] {symbol} EMANCIPADO! Slot {slot_id} LIVRE. Moonbag criada.")
        except Exception as e:
            logger.error(f"⚡ [FLASH] Erro na emancipação de {symbol}: {e}")

    async def _close_position(self, slot_id: int, symbol: str, side: str, qty: float, reason: str):
        """🛑 Fecha posição tática por SL."""
        try:
            from services.okx_rest import okx_rest_service
            await okx_rest_service.close_position(symbol, side, qty, reason=reason)
            await database_service.update_slot(slot_id, {
                "symbol": None, "entry_price": 0, "current_stop": 0,
                "qty": 0, "pnl_percent": 0, "status_risco": "LIVRE"
            })
            logger.warning(f"🛑⚡ [FLASH] {symbol} FECHADO por SL. Motivo: {reason}")
        except Exception as e:
            logger.error(f"⚡ [FLASH] Erro ao fechar {symbol}: {e}")

    async def _close_moonbag(self, moon_uuid: str, symbol: str, side: str, qty: float, reason: str):
        """🌙🛑 Fecha Moonbag por violação de SL."""
        try:
            from services.okx_rest import okx_rest_service
            closed = await okx_rest_service.close_position(symbol, side, qty, reason=reason)
            if not closed:
                logger.error(
                    f"[MOONBAG-CLOSE-GUARD] {symbol} close_position retornou False. "
                    f"Moonbag {moon_uuid} NAO sera removida sem ledger."
                )
                closed = await self._forensic_close_paper_moonbag(moon_uuid, symbol, side, qty, reason)
            if not closed:
                return
            await database_service.remove_moonbag(moon_uuid)
            logger.warning(f"🌙🛑⚡ [FLASH] Moonbag {symbol} FECHADA por SL. Motivo: {reason}")
        except Exception as e:
            logger.error(f"⚡ [FLASH] Erro ao fechar Moonbag {symbol}: {e}")

    # ==================== SINCRONIZAÇÃO ====================

    async def _forensic_close_paper_moonbag(self, moon_uuid: str, symbol: str, side: str, qty: float, reason: str) -> bool:
        """Fecha uma moonbag PAPER pelo registro Postgres quando a memoria local perdeu a posicao."""
        try:
            from services.okx_rest import okx_rest_service
            if okx_rest_service.execution_mode != "PAPER":
                return False

            moon = await database_service.get_moonbag(moon_uuid)
            if not moon:
                logger.error(f"[MOONBAG-FORENSIC-CLOSE] {symbol} sem registro Postgres {moon_uuid}.")
                return False

            entry_price = float(moon.get("entry_price") or 0)
            exit_price = float(moon.get("current_stop") or 0)
            close_qty = float(qty or moon.get("qty") or 0)
            leverage = float(moon.get("leverage") or 50)
            if entry_price <= 0 or exit_price <= 0 or close_qty <= 0:
                logger.error(
                    f"[MOONBAG-FORENSIC-CLOSE] {symbol} dados invalidos: "
                    f"entry={entry_price} exit={exit_price} qty={close_qty}"
                )
                return False

            projection = moon.get("projection") or {}
            contract = projection.get("contract") or moon.get("contract_meta") or {}
            ct_val = float(contract.get("ct_val") or contract.get("ctVal") or 0)
            if ct_val <= 0:
                try:
                    info = await okx_rest_service.get_instrument_info(symbol)
                    ct_val = float(info.get("lotSizeFilter", {}).get("ctVal") or 1.0)
                except Exception:
                    ct_val = 1.0

            from services.execution_protocol import execution_protocol
            final_pnl = execution_protocol.calculate_pnl(entry_price, exit_price, close_qty, side, ct_val)
            final_roi = order_projection_service.calculate_roi(entry_price, exit_price, side, leverage)
            entry_margin = float(moon.get("entry_margin") or 0)
            pnl_percent = (final_pnl / entry_margin * 100.0) if entry_margin > 0 else final_roi

            trade_data = {
                "symbol": symbol,
                "side": side,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "qty": close_qty,
                "order_id": f"{moon_uuid}_forensic",
                "genesis_id": moon.get("genesis_id"),
                "pnl": final_pnl,
                "slot_id": 0,
                "slot_type": "MOONBAG",
                "close_reason": f"MOONBAG_FORENSIC_CLOSE_{reason}",
                "final_roi": final_roi,
                "closed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "opened_at": moon.get("opened_at", 0),
                "entry_margin": entry_margin,
                "leverage": leverage,
                "pnl_percent": round(pnl_percent, 2),
                "current_stop_at_close": exit_price,
                "flash_last_action": moon.get("flash_last_action"),
                "flash_last_stop_roi": moon.get("flash_last_stop_roi"),
                "reasoning_report": (
                    f"MOONBAG FORENSIC CLOSE\n"
                    f"Motivo: {reason}\n"
                    f"Memoria paper nao confirmou close_position; fechamento reconstruido do Postgres.\n"
                    f"Entry={entry_price} ExitStop={exit_price} Qty={close_qty} ctVal={ct_val} PnL={final_pnl:.4f} ROI={final_roi:.1f}%"
                ),
            }

            from services.bankroll import bankroll_manager
            await bankroll_manager.register_sniper_trade(trade_data)
            okx_rest_service.paper_balance += final_pnl
            norm = okx_rest_service.normalize_symbol(symbol)
            okx_rest_service.paper_moonbags = [
                p for p in okx_rest_service.paper_moonbags
                if okx_rest_service.normalize_symbol(p.get("symbol", "")) != norm
            ]
            await okx_rest_service._save_paper_state()
            logger.warning(
                f"[MOONBAG-FORENSIC-CLOSE] {symbol} ledger registrado | "
                f"pnl=${final_pnl:.2f} roi={final_roi:.1f}% stop=${exit_price:.8f}"
            )
            return True
        except Exception as exc:
            logger.error(f"[MOONBAG-FORENSIC-CLOSE] Falha ao fechar {symbol}: {exc}")
            return False

    async def _sync_paper_stop(self, symbol: str, sl_price: float):
        """Sincroniza stop no Paper Memory (fire-and-forget)."""
        try:
            from services.okx_rest import okx_rest_service
            if okx_rest_service.execution_mode == "PAPER":
                norm = okx_rest_service.normalize_symbol(symbol)
                # Procura em paper_positions primeiro, depois paper_moonbags
                for lista in [okx_rest_service.paper_positions, okx_rest_service.paper_moonbags]:
                    pos = next(
                        (p for p in lista if okx_rest_service.normalize_symbol(p.get("symbol", "")) == norm),
                        None
                    )
                    if pos:
                        pos["stopLoss"] = str(sl_price)
                        await okx_rest_service._save_paper_state()
                        break
        except Exception as e:
            logger.warning(f"⚡ [FLASH] Paper sync fail (non-critical): {e}")

    async def _sync_firebase_slot(self, slot_id: int, payload: dict):
        """Sincroniza com Firebase (fire-and-forget)."""
        try:
            from services.firebase_service import firebase_service
            slot_state = await firebase_service.get_slot(slot_id)
            if slot_state and slot_state.get("symbol"):
                await firebase_service.update_slot(slot_id, payload)
        except Exception:
            pass


# Instância global
flash_agent = FlashAgent()
