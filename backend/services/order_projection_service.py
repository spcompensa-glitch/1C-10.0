# 1CRYPTEN - Order Projection Service
"""
Single source of truth for order ROI, stop levels, and chart lines.

The same order moves through one continuous lifecycle:
ORDER -> ESCADINHA -> TRAILING. There is no promotion to a separate Moonbag
container; every broken target only promotes the stop on the same order.
Frontend surfaces should render this projection instead of recalculating stops.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class StopLevel:
    phase: str
    name: str
    trigger_roi: float
    stop_roi: float
    status_risco: str


ORDER_STOP_LADDER_RANGING: List[StopLevel] = [
    # [V119] Escadinha RANGING Progressiva e Acelerada (Calibrada)
    # Folga maior para evitar violinada precoce no lucro pequeno (+6% trigger, stop +1.5% break-even)
    StopLevel("ESCADINHA", "GARANTIA_TAXAS", 8.0, 2.0, "RISCO_ZERO"),
    StopLevel("ESCADINHA", "GARANTIA_LUCRO_CURTO", 12.0, 5.0, "RISCO_ZERO"),
    StopLevel("ESCADINHA", "GARANTIA_LUCRO_MEDIO", 20.0, 10.0, "RISCO_ZERO"),
    StopLevel("ESCADINHA", "GARANTIA_LUCRO_ALTO", 32.0, 18.0, "RISCO_ZERO"),
    # Trailing muito apertado em +48% assim que bate +50% ROI para travar lucro máximo
    StopLevel("TRAILING", "ALVO_MAXIMO_LATERAL", 50.0, 48.0, "PROFIT_LOCK"),
]

ORDER_STOP_LADDER_TRENDING: List[StopLevel] = [
    # [V119] Escadinha TRENDING Progressiva e Calibrada
    # O trade corre livre até +12% ROI antes de mover para break-even, evitando violinadas curtas
    StopLevel("ESCADINHA", "GARANTIA_TAXAS", 14.0, 2.0, "RISCO_ZERO"),
    StopLevel("ESCADINHA", "GARANTIA_20", 25.0, 10.0, "RISCO_BAIXO"),
    StopLevel("ESCADINHA", "LUCRO_INICIAL", 40.0, 20.0, "RISCO_ZERO"),
    StopLevel("ESCADINHA", "LUCRO_MEDIO", 60.0, 40.0, "RISCO_ZERO"),
    StopLevel("ESCADINHA", "LUCRO_ALTO", 80.0, 60.0, "RISCO_ZERO"),
    StopLevel("ESCADINHA", "LUCRO_GARANTIDO_100", 100.0, 80.0, "RISCO_ZERO"),
    StopLevel("ESCADINHA", "SUCESSO_TOTAL", 130.0, 110.0, "PROFIT_LOCK"),
    StopLevel("TRAILING", "ALVO_150", 150.0, 110.0, "PROFIT_LOCK"),
    StopLevel("TRAILING", "WAVE", 200.0, 150.0, "TRAIL_LOCK"),
    StopLevel("TRAILING", "ROCKET", 300.0, 220.0, "TRAIL_LOCK"),
    StopLevel("TRAILING", "STAR", 400.0, 280.0, "TRAIL_LOCK"),
    StopLevel("TRAILING", "CROWN", 500.0, 350.0, "TRAIL_LOCK"),
    StopLevel("TRAILING", "SUPERNOVA", 600.0, 420.0, "TRAIL_LOCK"),
    StopLevel("TRAILING", "GOD_MODE", 700.0, 500.0, "TRAIL_LOCK"),
    StopLevel("TRAILING", "CHOKE_PREP", 750.0, 600.0, "TRAIL_LOCK"),
    StopLevel("TRAILING", "CHOKE", 800.0, 650.0, "TRAIL_LOCK"),
    StopLevel("TRAILING", "HYPER", 1000.0, 800.0, "TRAIL_LOCK"),
    StopLevel("TRAILING", "APEX", 1200.0, 1000.0, "TRAIL_LOCK"),
]

ORDER_STOP_LADDER: List[StopLevel] = ORDER_STOP_LADDER_TRENDING # Alias para compatibilidade com o compliance do hermes-agent

POST_APEX_STEP_ROI = 200.0
POST_APEX_STOP_OFFSET_ROI = 200.0


class OrderProjectionService:
    def normalize_side(self, side: Any) -> str:
        raw = str(side or "BUY").upper()
        return "buy" if raw in ("BUY", "LONG", "B") else "sell"

    def calculate_roi(self, entry_price: float, current_price: float, side: Any, leverage: float) -> float:
        if entry_price <= 0 or current_price <= 0 or leverage <= 0:
            return 0.0

        normalized_side = self.normalize_side(side)
        if normalized_side == "buy":
            price_diff_pct = (current_price - entry_price) / entry_price
        else:
            price_diff_pct = (entry_price - current_price) / entry_price
        return price_diff_pct * leverage * 100

    def raw_price_from_roi(self, entry_price: float, roi_percent: float, side: Any, leverage: float) -> float:
        if entry_price <= 0 or leverage <= 0:
            return 0.0

        price_offset_pct = roi_percent / (leverage * 100)
        normalized_side = self.normalize_side(side)
        if normalized_side == "buy":
            return entry_price * (1 + price_offset_pct)
        return entry_price * (1 - price_offset_pct)

    def round_to_tick(self, price: float, tick_size: float) -> float:
        if price <= 0 or tick_size <= 0:
            return price
        tick = Decimal(str(tick_size))
        rounded = (Decimal(str(price)) / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick
        return float(rounded.normalize())

    def round_stop_to_tick(self, price: float, tick_size: float, side: Any, stop_roi: float) -> float:
        if price <= 0 or tick_size <= 0:
            return price
        from decimal import ROUND_CEILING, ROUND_FLOOR

        tick = Decimal(str(tick_size))
        normalized_side = self.normalize_side(side)
        if stop_roi >= 0 and normalized_side == "buy":
            rounding = ROUND_CEILING
        elif stop_roi >= 0 and normalized_side == "sell":
            rounding = ROUND_FLOOR
        else:
            rounding = ROUND_HALF_UP
        rounded = (Decimal(str(price)) / tick).quantize(Decimal("1"), rounding=rounding) * tick
        return float(rounded.normalize())

    async def price_from_roi(self, symbol: str, entry_price: float, roi_percent: float, side: Any, leverage: float) -> float:
        raw_price = self.raw_price_from_roi(entry_price, roi_percent, side, leverage)
        if raw_price <= 0:
            return 0.0

        try:
            from services.okx_rest import okx_rest_service

            return await asyncio.wait_for(okx_rest_service.round_price(symbol, raw_price), timeout=1.5)
        except Exception:
            return raw_price

    def get_stop_ladder(self, roi_percent: float = 0.0, is_ranging: bool = False) -> List[StopLevel]:
        ladder = list(ORDER_STOP_LADDER_RANGING if is_ranging else ORDER_STOP_LADDER_TRENDING)
        highest_trigger = max(level.trigger_roi for level in ladder)
        target_ceiling = max(highest_trigger, roi_percent + 400.0)
        
        if is_ranging:
            # Em Ranging, acima de 20% ROI, a escada sobe dinamicamente de 1 em 1%
            trigger_roi = highest_trigger + 1.0
            while trigger_roi <= target_ceiling + 1e-9:
                ladder.append(
                    StopLevel(
                        "TRAILING",
                        f"TRAIL_{int(trigger_roi)}",
                        trigger_roi,
                        trigger_roi - 5.0,
                        "TRAIL_LOCK",
                    )
                )
                trigger_roi += 1.0
        else:
            trigger_roi = highest_trigger + POST_APEX_STEP_ROI
            while trigger_roi <= target_ceiling + 1e-9:
                ladder.append(
                    StopLevel(
                        "TRAILING",
                        f"ULTRA_{int(trigger_roi)}",
                        trigger_roi,
                        max(trigger_roi - POST_APEX_STOP_OFFSET_ROI, 0.0),
                        "TRAIL_LOCK",
                    )
                )
                trigger_roi += POST_APEX_STEP_ROI

        return ladder

    def get_active_level(self, roi_percent: float, ladder: Optional[List[StopLevel]] = None, is_ranging: bool = False) -> Optional[StopLevel]:
        active = None
        epsilon = 1e-9
        for level in ladder or self.get_stop_ladder(roi_percent, is_ranging):
            if roi_percent + epsilon >= level.trigger_roi:
                active = level
            else:
                break
        
        # Se estiver em Ranging e em trailing stop ativo (ROI >= 50%)
        if is_ranging and active and active.phase == "TRAILING" and roi_percent >= 50.0:
            active = StopLevel(
                phase=active.phase,
                name=active.name,
                trigger_roi=active.trigger_roi,
                stop_roi=round(roi_percent - 2.0, 2), # Trailing stop apertado de 2% para fechar no pico
                status_risco=active.status_risco
            )
        return active

    def get_next_level(self, roi_percent: float, ladder: Optional[List[StopLevel]] = None, is_ranging: bool = False) -> Optional[StopLevel]:
        epsilon = 1e-9
        for level in ladder or self.get_stop_ladder(roi_percent, is_ranging):
            if roi_percent + epsilon < level.trigger_roi:
                return level
        return None

    def get_phase(self, roi_percent: float, phase_hint: Optional[str] = None, is_ranging: bool = False) -> str:
        if is_ranging:
            if roi_percent >= 50.0:
                return "TRAILING"
            if roi_percent >= 5.0:
                return "ESCADINHA"
            return "ORDER"
        else:
            if roi_percent >= 150.0:
                return "TRAILING"
            if roi_percent >= 10.0:
                return "ESCADINHA"
            return "ORDER"

    async def get_contract_meta(self, symbol: str) -> Dict[str, float]:
        try:
            from services.okx_rest import okx_rest_service

            info = await asyncio.wait_for(okx_rest_service.get_instrument_info(symbol), timeout=1.5)
            return {
                "tick_size": float(info.get("priceFilter", {}).get("tickSize") or 0.01),
                "qty_step": float(info.get("lotSizeFilter", {}).get("qtyStep") or 1.0),
                "min_qty": float(info.get("lotSizeFilter", {}).get("minOrderQty") or 1.0),
                "ct_val": float(info.get("lotSizeFilter", {}).get("ctVal") or 1.0),
            }
        except Exception:
            return {"tick_size": 0.01, "qty_step": 1.0, "min_qty": 1.0, "ct_val": 1.0}

    def notional_usd(self, qty: float, price: float, ct_val: float) -> float:
        return max(qty, 0.0) * max(price, 0.0) * max(ct_val, 0.0)

    def margin_usd(self, qty: float, price: float, leverage: float, ct_val: float) -> float:
        if leverage <= 0:
            return 0.0
        return self.notional_usd(qty, price, ct_val) / leverage

    async def build_projection(
        self,
        order: Dict[str, Any],
        current_price: Optional[float] = None,
        phase_hint: Optional[str] = None,
        fetch_contract: bool = True,
        is_ranging: Optional[bool] = None,
    ) -> Dict[str, Any]:
        symbol = order.get("symbol") or ""
        side = self.normalize_side(order.get("side"))
        entry_price = float(order.get("entry_price") or 0)
        current_price = float(current_price if current_price is not None else order.get("current_price") or 0)
        leverage = float(order.get("leverage") or 50.0)
        qty = float(order.get("qty") or order.get("size") or 0)
        current_stop = float(order.get("current_stop") or 0)

        # Obtem is_ranging dinamicamente do btc_adx do WS cache se não for fornecido e se okx_ws_public_service estiver instanciado
        if is_ranging is None:
            is_ranging = False
            import sys
            is_test_env = any("pytest" in arg or "test" in arg for arg in sys.argv)
            if not is_test_env:
                try:
                    from services.okx_ws_public import okx_ws_public_service
                    adx = getattr(okx_ws_public_service, "btc_adx", 0.0)
                    if adx > 0.1:
                        is_ranging = (adx < 25)
                except Exception:
                    pass

        roi = self.calculate_roi(entry_price, current_price, side, leverage)
        phase = self.get_phase(roi, phase_hint, is_ranging)
        stop_ladder = self.get_stop_ladder(roi, is_ranging)
        active_level = self.get_active_level(roi, stop_ladder, is_ranging)
        next_level = self.get_next_level(roi, stop_ladder, is_ranging)
        existing_contract = order.get("contract") or order.get("contract_meta") or {}
        if existing_contract:
            contract = {
                "tick_size": float(existing_contract.get("tick_size") or existing_contract.get("tickSize") or 0.01),
                "qty_step": float(existing_contract.get("qty_step") or existing_contract.get("qtyStep") or 1.0),
                "min_qty": float(existing_contract.get("min_qty") or existing_contract.get("minQty") or 1.0),
                "ct_val": float(existing_contract.get("ct_val") or existing_contract.get("ctVal") or 1.0),
            }
        elif symbol and fetch_contract:
            contract = await self.get_contract_meta(symbol)
        else:
            contract = {
            "tick_size": 0.01,
            "qty_step": 1.0,
            "min_qty": 1.0,
            "ct_val": 1.0,
            }

        levels = []
        for level in stop_ladder:
            raw_price = self.raw_price_from_roi(entry_price, level.stop_roi, side, leverage)
            price = self.round_stop_to_tick(raw_price, contract["tick_size"], side, level.stop_roi)
            raw_target_price = self.raw_price_from_roi(entry_price, level.trigger_roi, side, leverage)
            target_price = self.round_to_tick(raw_target_price, contract["tick_size"])
            levels.append({
                "phase": level.phase,
                "name": level.name,
                "trigger_roi": level.trigger_roi,
                "stop_roi": level.stop_roi,
                "price": price,
                "target_price": target_price,
                "active": roi >= level.trigger_roi,
                "status_risco": level.status_risco,
            })

        recommended_stop = 0.0
        if active_level:
            raw_stop = self.raw_price_from_roi(entry_price, active_level.stop_roi, side, leverage)
            recommended_stop = self.round_stop_to_tick(raw_stop, contract["tick_size"], side, active_level.stop_roi)

        # Calcular Preço de Liquidação teórico (100% da margem perdida)
        # Em 50x, isso ocorre com variação de 2% (1 / 50 = 0.02)
        liq_price = 0.0
        if entry_price > 0 and leverage > 0:
            margin_loss_ratio = 1.0 / leverage
            if side == "buy":
                raw_liq = entry_price * (1.0 - margin_loss_ratio)
                liq_price = self.round_stop_to_tick(raw_liq, contract["tick_size"], side, -100.0)
            else:
                raw_liq = entry_price * (1.0 + margin_loss_ratio)
                liq_price = self.round_stop_to_tick(raw_liq, contract["tick_size"], side, -100.0)

        pnl_usd = 0.0
        if entry_price > 0 and current_price > 0 and qty > 0:
            price_delta = current_price - entry_price if side == "buy" else entry_price - current_price
            pnl_usd = qty * contract["ct_val"] * price_delta

        margin = self.margin_usd(qty, entry_price, leverage, contract["ct_val"])

        return {
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "current_price": current_price,
            "qty": qty,
            "leverage": leverage,
            "roi_percent": roi,
            "phase": phase,
            "current_stop": current_stop,
            "recommended_stop": recommended_stop,
            "liq_price": liq_price,
            "active_level": {
                "phase": active_level.phase,
                "name": active_level.name,
                "trigger_roi": active_level.trigger_roi,
                "stop_roi": active_level.stop_roi,
                "status_risco": active_level.status_risco,
            } if active_level else None,
            "next_level": {
                "phase": next_level.phase,
                "name": next_level.name,
                "trigger_roi": next_level.trigger_roi,
                "stop_roi": next_level.stop_roi,
                "price": self.round_to_tick(
                    self.raw_price_from_roi(entry_price, next_level.stop_roi, side, leverage),
                    contract["tick_size"],
                ),
                "target_price": self.round_to_tick(
                    self.raw_price_from_roi(entry_price, next_level.trigger_roi, side, leverage),
                    contract["tick_size"],
                ),
                "status_risco": next_level.status_risco,
            } if next_level else None,
            "should_emancipate": False,
            "levels": levels,
            "contract": contract,
            "notional_usd": self.notional_usd(qty, current_price or entry_price, contract["ct_val"]),
            "entry_margin": margin,
            "pnl_usd": pnl_usd,
            "flash": {
                "agent": "FLASH",
                "last_action": active_level.name if active_level else "MONITORANDO",
                "stop_roi": active_level.stop_roi if active_level else None,
            },
        }


order_projection_service = OrderProjectionService()
