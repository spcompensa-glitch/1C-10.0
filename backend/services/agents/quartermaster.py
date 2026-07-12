# -*- coding: utf-8 -*-
import logging
import time
from typing import Dict, Any, List, Optional
from services.agents.aios_adapter import AIOSAgent
from services.firebase_service import firebase_service
from config import settings

logger = logging.getLogger("QuartermasterAgent")

class QuartermasterAgent(AIOSAgent):
    """
    [V110.135] QUARTERMASTER AGENT (The Intendente)
    Responsibility: Risk Equalization, Dynamic Leverage Scaling, and Armory Control.
    Ensures that the fleet uses the correct tools for the asset DNA.
    """

    def __init__(self):
        super().__init__(
            agent_id="agent-quartermaster-elite",
            role="quartermaster",
            capabilities=["risk_management", "leverage_scaling", "armory_audit"]
        )
        # User defined thresholds for V110.135
        self.wick_smooth_threshold = 0.45
        self.wick_jumpy_threshold = 0.70
        
        # Standard leverages
        self.lev_smooth = 50
        self.lev_jumpy = 20
        self.lev_extreme = 10

    async def on_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """AIOS Message Handler for Quartermaster."""
        msg_type = message.get("type")
        data = message.get("data", {})
        
        if msg_type == "CHECK_ARMORY":
            return await self.check_armory(
                symbol=data.get("symbol"),
                lib_dna=data.get("lib_dna", {}),
                market_data=data.get("market_data", {})
            )
            
        return {"status": "error", "message": f"Unknown command: {msg_type}"}

    async def check_armory(self, symbol: str, lib_dna: Dict[str, Any], market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates the asset DNA and market environment to assign leverage and verify entry safety.
        Returns: { 'leverage': int, 'margin_multiplier': float, 'block_reason': str | None }
        """
        wick_intensity = lib_dna.get("wick_intensity", 0.0)
        btc_adx = market_data.get("btc_adx", 0.0)
        
        # 1. Classification & Leverage Scaling
        if wick_intensity < self.wick_smooth_threshold:
            classification = "SMOOTH"
            leverage = self.lev_smooth
        elif wick_intensity < self.wick_jumpy_threshold:
            classification = "JUMPY"
            leverage = self.lev_jumpy
        else:
            classification = "EXTREME"
            leverage = self.lev_extreme

        # [V126] Filtro Hermes: Volatilidade M30
        if classification == "SMOOTH":
            try:
                from services.okx_rest import okx_rest_service
                # Pega as últimas 12 velas M30 para média de volatilidade
                candles = await okx_rest_service.get_klines(symbol, interval='30', limit=12)
                if candles and len(candles) >= 5:
                    vols = []
                    for c in candles:
                        h = float(c[2] if isinstance(c, list) else c.get('high', 0))
                        l = float(c[3] if isinstance(c, list) else c.get('low', 0))
                        cp = float(c[4] if isinstance(c, list) else c.get('close', 1))
                        vols.append((h - l) / cp if cp > 0 else 0)
                    
                    if vols:
                        avg_vol = sum(vols) / len(vols)
                        curr_vol = vols[-1]
                        if avg_vol > 0 and curr_vol > (avg_vol * 1.2):
                            logger.info(f"⚓ [QUARTERMASTER] {symbol} Volatilidade M30 explodindo ({curr_vol:.4f} > avg {avg_vol:.4f}). Rebaixado SMOOTH -> JUMPY.")
                            classification = "JUMPY"
                            leverage = self.lev_jumpy
            except Exception:
                pass

        # 2. Risk Equalization Multiplier
        # Based on 50x as base, margin must move inversely to leverage.
        # multiplier = base_leverage / target_leverage
        margin_multiplier = 50.0 / leverage
        
        # 3. Security Check (The Guillotine)
        block_reason = None
        if classification == "EXTREME" and btc_adx < 25:
            if settings.OKX_EXECUTION_MODE == "PAPER":
                logger.warning(f"🛡️ [PAPER] [QUARTERMASTER] BYPASS LOW_ADX_EXTREME_WICK para permitir teste de ordens do Capitão no simulador.")
            else:
                block_reason = f"LOW_ADX_EXTREME_WICK: Asset is too wicky ({wick_intensity:.2f}) for low trend environment (ADX={btc_adx:.1f})"
                logger.warning(f"🛡️ [QUARTERMASTER] {symbol} BLOCKED: {block_reason}")
            
        logger.info(
            f"⚓ [QUARTERMASTER] {symbol} | Class: {classification} | "
            f"Wick: {wick_intensity:.2f} | Leverage: {leverage}x | "
            f"Margin Multiplier: {margin_multiplier:.1f}x | Block: {block_reason}"
        )
        
        return {
            "status": "success",
            "symbol": symbol,
            "classification": classification,
            "leverage": leverage,
            "margin_multiplier": margin_multiplier,
            "block_reason": block_reason,
            "wick_intensity": wick_intensity,
            "btc_adx": btc_adx
        }

    @staticmethod
    def calculate_wick_intensity(high: float, low: float, open_p: float, close_p: float) -> float:
        """
        Normalized Wick Intensity Formula: (Range - Body) / Body
        Body = abs(Close - Open)
        Range = High - Low
        """
        body = abs(close_p - open_p)
        range_val = high - low
        
        if body <= 0:
            # Doji bar where range > 0
            if range_val > 0:
                return 5.0 # Max penalty for pure doji wicks
            return 0.0
            
        return (range_val - body) / body

quartermaster_agent = QuartermasterAgent()
