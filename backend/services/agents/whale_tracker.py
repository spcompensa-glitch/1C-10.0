import logging
from typing import Dict, Any, List
from services.agents.aios_adapter import AIOSAgent
from services.okx_rest import okx_rest_service
from services.signal_generator import signal_generator

logger = logging.getLogger("WhaleTracker")

class WhaleTracker(AIOSAgent):
    """
    [V43.0] Python-Logic Specialist: Institutional Flow & Absorption Detection.
    Analyzes CVD delta and Open Interest variation to detect traps.
    """
    def __init__(self):
        super().__init__(
            agent_id="agent-whale-logic",
            role="whale_tracker",
            capabilities=["liquidity_analysis", "oi_tracking", "cvd_delta", "absorption_detection"]
        )
        # Histórico curto para detecção de divergência {symbol: [list of {'price': float, 'cvd': float, 'ts': float}]}
        self.flow_history = {}

    async def on_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        data = message.get("data", {})
        symbol = data.get("symbol")
        
        if msg_type == "CHECK_LIQUIDITY" and symbol:
            return await self._check_liquidity(symbol)
            
        return {"status": "ERROR", "message": f"Unknown message type: {msg_type}"}

    async def _check_liquidity(self, symbol: str) -> Dict[str, Any]:
        """Analyzes CVD and OI to detect institutional presence and absorption."""
        try:
            from services.okx_ws_public import okx_ws_public_service
            import time

            # 1. Get CVD (from Signal Generator helper)
            cvd = await signal_generator.calculate_rest_cvd(symbol)
            current_price = okx_ws_public_service.get_current_price(symbol)
            
            # 2. Get Open Interest
            oi_data = await okx_rest_service.get_open_interest(symbol, interval="5min")
            oi_val = 0
            if oi_data and isinstance(oi_data, list) and len(oi_data) > 0:
                oi_val = float(oi_data[0].get("openInterest", 0))
            
            # 3. Absorption Detection [V43.0]
            if symbol not in self.flow_history:
                self.flow_history[symbol] = []
            
            self.flow_history[symbol].append({
                'price': current_price,
                'cvd': cvd,
                'ts': time.time()
            })
            
            # Keep only last 5 entries (approx 5-10 mins if called by monitor)
            if len(self.flow_history[symbol]) > 5:
                self.flow_history[symbol].pop(0)
            
            trap_risk = False
            trap_reason = ""
            
            suggested_side = None
            if len(self.flow_history[symbol]) >= 3:
                first = self.flow_history[symbol][0]
                last = self.flow_history[symbol][-1]
                
                price_change_pct = (last['price'] - first['price']) / first['price'] if first['price'] > 0 else 0
                cvd_change = last['cvd'] - first['cvd']
                
                # [BULL TRAP DETECTION] CVD subindo forte mas preço parado ou caindo
                if cvd_change > 40000 and price_change_pct < 0.0003: 
                    trap_risk = True
                    trap_reason = "BULL_TRAP: Absorption detected (High CVD Buy / Late Price)"
                    suggested_side = "Sell"
                # [BEAR TRAP DETECTION] CVD caindo forte mas preço parado ou subindo
                elif cvd_change < -40000 and price_change_pct > -0.0003:
                    trap_risk = True
                    trap_reason = "BEAR_TRAP: Absorption detected (High CVD Sell / Late Price)"
                    suggested_side = "Buy"
                # [V89.0] WHALE_PULSE: Ignição Institucional (CVD Alpha Explosion)
                # Se o CVD variar mais de 150k em minutos, é ignição de baleia
                if cvd_change > 150000:
                    whale_presence = "EXTREME (Whale Pulse)"
                    suggested_side = "Buy"
                    logger.info(f"💥 [WHALE-PULSE] {symbol}: Ignição de Compra Institucional detectada! CVD Delta: {cvd_change:.0f}")
                elif cvd_change < -150000:
                    whale_presence = "EXTREME (Whale Pulse)"
                    suggested_side = "Sell"
                    logger.info(f"💥 [WHALE-PULSE] {symbol}: Ignição de Venda Institucional detectada! CVD Delta: {cvd_change:.0f}")
                else:
                    suggested_side = None

            # Simplified bias logic
            whale_presence = "Neutral"
            if abs(cvd) > 100000:
                whale_presence = "High (CVD Alpha)"
            elif abs(cvd) > 50000:
                whale_presence = "Moderate"
                
            bias = "ACCUMULATION" if cvd > 0 else "DISTRIBUTION" if cvd < 0 else "SIDEWAYS"
            if trap_risk:
                bias = f"TRAP_{bias}"

            return {
                "status": "SUCCESS",
                "data": {
                    "whale_presence": whale_presence,
                    "cvd_delta": cvd,
                    "open_interest": oi_val,
                    "bias": bias,
                    "trap_risk": trap_risk,
                    "trap_reason": trap_reason,
                    "suggested_side": suggested_side
                }
            }
        except Exception as e:
            logger.error(f"Whale Logic Error for {symbol}: {e}")
            return {"status": "SUCCESS", "data": {"whale_presence": "Neutral", "cvd_delta": 0, "trap_risk": False}}

# Instance
whale_tracker = WhaleTracker()
