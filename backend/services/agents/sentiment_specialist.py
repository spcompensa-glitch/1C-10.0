import logging
import time
from typing import Dict, Any, List
from services.agents.aios_adapter import AIOSAgent
from services.okx_rest import okx_rest_service

logger = logging.getLogger("SentimentSpecialist")

class SentimentSpecialist(AIOSAgent):
    """
    [V35.0] Python-Logic Specialist: Retail Sentiment & LS-Ratio.
    Analyzes Long/Short ratio and Funding Rates without using LLMs.
    """
    def __init__(self):
        super().__init__(
            agent_id="agent-sentiment-logic",
            role="sentiment_specialist",
            capabilities=["ls_ratio_analysis", "funding_rate_tracking", "retail_bias"]
        )

    async def on_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        try:
            msg_type = message.get("type")
            # Ensure data is always a dict to avoid NameError/AttributeError downstream
            data_raw = message.get("data", {})
            data = data_raw if isinstance(data_raw, dict) else {}
            
            symbol = data.get("symbol")
            
            if msg_type == "GET_SENTIMENT" and symbol:
                return await self._get_sentiment(symbol, is_ranging=data.get("is_ranging", False))
                
            return {"status": "ERROR", "message": f"Unknown message type: {msg_type}"}
        except Exception as e:
            logger.error(f"Sentiment Specialist Critical on_message Error: {e}")
            return {"status": "SUCCESS", "data": {"score": 50, "ls_ratio": 1.0}}

    async def _get_sentiment(self, symbol: str, is_ranging: bool = False) -> Dict[str, Any]:
        """Calculates sentiment score based on LS-Ratio and Funding Rate."""
        try:
            # 1. Get Long/Short Ratio (Retail Positioning)
            ls_ratio = await okx_rest_service.get_account_ratio(symbol)
            
            # 2. Get Funding Rate (Pressure)
            funding = await okx_rest_service.get_funding_rate(symbol)
            
            # Sentiment Score (0-100)
            # 50: Neutral
            score = 50
            # > 70: Extreme Bullish (Retail trapped Long?)
            # < 30: Extreme Bearish (Retail trapped Short?)
            
            # [V43.0] Rigorous Bias Logic: High LS-Ratio = Retail are Long = Institutional Trap
            # Limits reduced from 2.0 to 1.7
            if ls_ratio > 1.7:
                score = 15 # Extreme Retail Long (High dump risk)
            elif ls_ratio > 1.4:
                score = 30 # Retail Long bias
            elif ls_ratio < 0.8:
                score = 85 # Retail too Short (High squeeze potential)
            elif ls_ratio < 0.9:
                score = 70 # Retail Short bias
            
            # [V43.0] Ranging Rigor: In slow markets, retail leverage is even more dangerous
            if is_ranging and ls_ratio > 1.3:
                score -= 15
                logger.info(f"🛡️ [V43.0 RIGOR] Ranging market detected. Punishing LS-Ratio {ls_ratio:.2f}")

            # [V55.0] Microstructure OBI Injection
            from services.okx_ws_public import okx_ws_public_service
            obi = okx_ws_public_service.obi_cache.get(symbol, 0)
            if (obi > 0.5): # Strong Buy pressure
                score += 10
            elif (obi < -0.5): # Strong Sell pressure
                score -= 10
            
            # [V56.0] On-Chain Whale Alert Injection
            from services.agents.onchain_whale_watcher import on_chain_whale_watcher
            whale_alerts = on_chain_whale_watcher.whale_alerts
            onchain_score = 50 # Neutral base for on-chain
            onchain_summary = "Scan Global: Sem anomalias"
            
            for alert in whale_alerts:
                # If alert is recent (< 1 hour) and relevant to our symbol or global (BTC/ETH/USDT)
                if (time.time() - alert['timestamp']) < 3600:
                    is_global = alert['symbol'] in ["USDT", "ETH", "BTC"]
                    if alert['symbol'] == symbol or is_global:
                        val_str = alert.get('value', 'N/A')
                        if "INFLOW" in alert['type']:
                            score -= 20 # Whale moving to exchange = DUMP RISK
                            onchain_score -= 30
                            onchain_summary = f"⚠️ ALERTA: Baleia enviou {val_str} {alert['symbol']} p/ Exchange"
                            logger.info(f"🚨 [V56.0] ON-CHAIN WHALE INFLOW DETECTED: {alert['symbol']} {val_str} -> score -20")
                        elif "OUTFLOW" in alert['type']:
                            score += 15 # Whale moving to wallet = HODL/PUMP
                            onchain_score += 25
                            onchain_summary = f"🐋 ALERTA: Baleia retirou {val_str} {alert['symbol']} da Bybit"
                            logger.info(f"🐋 [V56.0] ON-CHAIN WHALE OUTFLOW DETECTED: {alert['symbol']} {val_str} -> score +15")
            
            # Weighting Funding Rate (Funding positive = Longs pay Shorts)
            if funding > 0.0003: # High 0.03%+
                score -= 15
            elif funding < -0.0003:
                score += 15
                
            return {
                "status": "SUCCESS",
                "data": {
                    "score": max(0, min(100, score)),
                    "onchain_score": max(0, min(100, onchain_score)),
                    "onchain_summary": onchain_summary,
                    "ls_ratio": ls_ratio,
                    "funding_rate": funding,
                    "bias": "OVERBOUGHT" if ls_ratio > 1.4 else "OVERSOLD" if ls_ratio < 0.85 else "NEUTRAL",
                    "pain_points": self._get_pain_points(symbol, ls_ratio) 
                }
            }
        except Exception as e:
            logger.error(f"Sentiment Logic Error for {symbol}: {e}")
            return {"status": "SUCCESS", "data": {"score": 50, "ls_ratio": 1.0}}

    def _get_pain_points(self, symbol: str, ls_ratio: float) -> Dict[str, Any]:
        """
        [V46.0] Pain Point Mapper: Estimates liquidation clusters.
        If LS Ratio is high (Retail Long), pain points are below (liquidation prices).
        If LS Ratio is low (Retail Short), pain points are above.
        """
        from services.okx_ws_public import okx_ws_public_service
        current_price = okx_ws_public_service.get_current_price(symbol)
        if current_price <= 0: return {}

        # Estimativa simplificada baseada em alavancagem comum (10x, 25x, 50x)
        # 100 / lev = dist_pct
        levs = [10, 25, 50]
        clusters = []

        if ls_ratio > 1.2:
            # Varejo LONG -> Liquidações abaixo
            side = "LONG_LIQ"
            for lev in levs:
                dist = (100 / lev) * 0.8  # 80% do caminho para segurança
                liq_price = current_price * (1 - (dist / 100))
                clusters.append({"lev": lev, "price": liq_price, "dist_pct": dist})
        elif ls_ratio < 0.85:
            # Varejo SHORT -> Liquidações acima
            side = "SHORT_LIQ"
            for lev in levs:
                dist = (100 / lev) * 0.8
                liq_price = current_price * (1 + (dist / 100))
                clusters.append({"lev": lev, "price": liq_price, "dist_pct": dist})
        else:
            return {"bias": "NEUTRAL", "clusters": []}

        return {
            "bias": side,
            "clusters": clusters,
            "primary_target": clusters[1]["price"] if len(clusters) > 1 else 0 # 25x is often the big prize
        }

# Instance
sentiment_specialist = SentimentSpecialist()
