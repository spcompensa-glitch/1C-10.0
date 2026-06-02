import logging
import time
from typing import Dict, Any, List
from services.agents.aios_adapter import AIOSAgent
from services.okx_ws_public import okx_ws_public_service

logger = logging.getLogger("MacroAnalyst")

class MacroAnalyst(AIOSAgent):
    """
    [V35.0] Python-Logic Specialist: Macro Trend & BTC Guard.
    Analyzes global market bias without using LLMs.
    """
    def __init__(self):
        super().__init__(
            agent_id="agent-macro-logic",
            role="macro_analyst",
            capabilities=["trend_analysis", "btc_dominance", "market_bias"]
        )

    async def on_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        
        if msg_type == "GET_MACRO_BIAS":
            return await self._get_macro_bias()
            
        if msg_type == "GET_BTC_DOMINANCE":
            return await self._get_btc_dominance()
            
        return {"status": "ERROR", "message": f"Unknown message type: {msg_type}"}

    async def _get_btc_dominance(self) -> float:
        """[V55.0] Fetches global BTC Dominance from a public API (CoinGecko fallback). Cached for 10 min."""
        now = time.time()
        if hasattr(self, "_dom_cache") and (now - self._dom_cache_time < 600):
            return self._dom_cache

        try:
            import httpx
            # Use CoinGecko Global API (Public, no key required for basic usage)
            url = "https://api.coingecko.com/api/v3/global"
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    dominance = data.get("data", {}).get("market_cap_percentage", {}).get("btc", 0)
                    self._dom_cache = float(dominance)
                    self._dom_cache_time = now
                    return self._dom_cache
            return getattr(self, "_dom_cache", 0.0)
        except Exception:
            return getattr(self, "_dom_cache", 0.0)

    async def _get_macro_bias(self) -> Dict[str, Any]:
        """Calculates macro risk based on BTC variation and Dominance."""
        try:
            btc_var = okx_ws_public_service.btc_variation_1h
            btc_dom = await self._get_btc_dominance()
            
            # Risk Score Logic (0-10)
            risk_score = 5 # Neutral default
            
            # 1. Price Volatility
            if abs(btc_var) > 2.0: risk_score += 4
            elif abs(btc_var) > 1.0: risk_score += 2
            
            # 2. [V55.0] Dominance Logic
            # High Dominance (> 50%) = BTC sucking liquidity (Risk-Off for Alts)
            # Falling Dominance = Alt-Season potential (Risk-On)
            if btc_dom > 55: risk_score += 2
            elif btc_dom < 48: risk_score -= 2
            
            # Clamp result
            risk_score = max(0, min(10, risk_score))
                
            return {
                "status": "SUCCESS",
                "data": {
                    "risk_score": risk_score,
                    "btc_variation": btc_var,
                    "btc_dominance": btc_dom,
                    "bias": "BULLISH" if btc_var > 0 else "BEARISH" if btc_var < 0 else "NEUTRAL"
                }
            }
        except Exception as e:
            logger.error(f"Macro Logic Error: {e}")
            return {"status": "SUCCESS", "data": {"risk_score": 5, "bias": "NEUTRAL"}}

# Instance
macro_analyst = MacroAnalyst()
