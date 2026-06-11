import logging
import time
import asyncio
import math
from typing import Dict, Any, List
from services.agents.aios_adapter import AIOSAgent
from services.okx_ws_public import okx_ws_public_service

logger = logging.getLogger("MacroAnalyst")

class MacroAnalyst(AIOSAgent):
    """
    [V35.0] Python-Logic Specialist: Macro Trend & BTC Guard.
    Analyzes global market bias without using LLMs.
    [ECC ito-market-intelligence] Correlação de Pearson BTC-Altcoin para Filtro de Pânico.
    """
    def __init__(self):
        super().__init__(
            agent_id="agent-macro-logic",
            role="macro_analyst",
            capabilities=["trend_analysis", "btc_dominance", "market_bias", "panic_filter"]
        )
        # Cache para correlação de Pearson (evita chamadas excessivas à API)
        self._corr_cache: Dict[str, Any] = {}
        self._corr_cache_time: float = 0.0

    async def on_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")

        if msg_type == "GET_MACRO_BIAS":
            return await self._get_macro_bias()

        if msg_type == "GET_BTC_DOMINANCE":
            return await self._get_btc_dominance()

        if msg_type == "GET_PANIC_FILTER":
            symbol = message.get("data", {}).get("symbol", "ETHUSDT")
            return await self.get_btc_altcoin_correlation(symbol)

        return {"status": "ERROR", "message": f"Unknown message type: {msg_type}"}

    async def _get_btc_dominance(self) -> float:
        """[V55.0] Fetches global BTC Dominance from a public API (CoinGecko fallback). Cached for 10 min."""
        now = time.time()
        if hasattr(self, "_dom_cache") and (now - self._dom_cache_time < 600):
            return self._dom_cache

        try:
            import httpx
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

    # -------------------------------------------------------------------------
    # [ECC ito-market-intelligence] PANIC FILTER: Pearson Correlation
    # -------------------------------------------------------------------------

    def _pearson_correlation(self, x: List[float], y: List[float]) -> float:
        """
        Calcula o coeficiente de correlação de Pearson entre duas séries de preços.
        Retorna valor entre -1 (inversamente correlacionados) e 1 (perfeitamente correlacionados).
        """
        n = min(len(x), len(y))
        if n < 3:
            return 0.0
        x = x[-n:]
        y = y[-n:]

        mean_x = sum(x) / n
        mean_y = sum(y) / n

        cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        std_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
        std_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))

        if std_x == 0 or std_y == 0:
            return 0.0
        return cov / (std_x * std_y)

    async def _fetch_recent_closes(self, symbol: str, limit: int = 20) -> List[float]:
        """
        Busca os últimos 'limit' fechamentos de 1h para o símbolo via OKX REST.
        Usa cache interno de até 5 minutos.
        """
        now = time.time()
        cache_key = f"closes_{symbol}"
        if cache_key in self._corr_cache:
            cached_time = self._corr_cache.get(f"{cache_key}_time", 0)
            if now - cached_time < 300:  # 5 min cache
                return self._corr_cache[cache_key]

        try:
            from services.okx_rest import okx_rest_service
            # get_klines retorna lista de [ts, open, high, low, close, vol, ...]
            candles = await asyncio.wait_for(
                okx_rest_service.get_klines(symbol, interval="60", limit=limit),
                timeout=3.0
            )
            closes = []
            if isinstance(candles, list):
                for c in candles:
                    try:
                        # Índice 4 = close price na estrutura OKX kline
                        closes.append(float(c[4]))
                    except (IndexError, TypeError, ValueError):
                        pass

            if closes:
                self._corr_cache[cache_key] = closes
                self._corr_cache[f"{cache_key}_time"] = now
            return closes
        except Exception as e:
            logger.warning(f"⚠️ [MACRO-CORR] Falha ao buscar klines de {symbol}: {e}")
            return []


    async def get_btc_altcoin_correlation(
        self,
        symbol: str,
        correlation_threshold: float = 0.8,
        btc_drop_threshold_pct: float = -2.0,  # em % (ex: -2.0 = -2%)
    ) -> Dict[str, Any]:
        """
        [ECC ito-market-intelligence] FILTRO DE PÂNICO:
        Calcula a correlação de Pearson entre BTC e a Altcoin nos últimos 20 fechamentos de 1H.

        Se BTC cai > 2% em 1H E correlação BTC/Altcoin >= 0.8:
          → Modo PÁNICO: bloqueia novas entradas LONG para proteger a banca.
        """
        result = {
            "status": "SUCCESS",
            "data": {
                "panic_mode": False,
                "correlation": 0.0,
                "btc_variation_1h": 0.0,
                "btc_drop": False,
                "reason": "CORRELATION_OK",
                "recommendation": "ALLOW_LONG",
            }
        }

        try:
            btc_var = float(getattr(okx_ws_public_service, "btc_variation_1h", 0.0) or 0.0)
            result["data"]["btc_variation_1h"] = round(btc_var, 4)

            btc_drop = btc_var < btc_drop_threshold_pct
            result["data"]["btc_drop"] = btc_drop

            if not btc_drop:
                result["data"]["reason"] = (
                    f"BTC_STABLE: var1h={btc_var:.2f}% acima do limiar {btc_drop_threshold_pct:.1f}%"
                )
                return result

            # BTC está caindo — calculamos a correlação Pearson
            btc_closes = await self._fetch_recent_closes("BTCUSDT", limit=20)
            alt_closes = await self._fetch_recent_closes(symbol, limit=20)

            if len(btc_closes) < 5 or len(alt_closes) < 5:
                result["data"]["reason"] = "DADOS_INSUFICIENTES_PARA_CORRELACAO"
                return result

            correlation = self._pearson_correlation(btc_closes, alt_closes)
            result["data"]["correlation"] = round(correlation, 4)

            if correlation >= correlation_threshold:
                result["data"]["panic_mode"] = True
                result["data"]["recommendation"] = "BLOCK_LONG"
                result["data"]["reason"] = (
                    f"PÁNICO DETECTADO: BTC var1h={btc_var:.2f}% | "
                    f"Correlação {symbol}/BTC={correlation:.2f} >= {correlation_threshold} | "
                    f"BLOQUEANDO novas entradas LONG"
                )
                logger.warning(
                    f"🚨 [PANIC-FILTER] {symbol} correlação={correlation:.2f} >= {correlation_threshold} "
                    f"com BTC caindo {btc_var:.2f}%. MODO PÁNICO ATIVADO!"
                )
            else:
                result["data"]["reason"] = (
                    f"DESCORRELACIONADO: BTC cai {btc_var:.2f}% mas correlação={correlation:.2f} < {correlation_threshold} | "
                    f"Oportunidade de descorrelação detectada para {symbol}"
                )
                logger.info(
                    f"✅ [PANIC-FILTER] {symbol} DESCORRELACIONADO (corr={correlation:.2f}). "
                    f"Entrada LONG permitida mesmo com BTC em queda."
                )

        except Exception as e:
            logger.error(f"❌ [PANIC-FILTER] Erro ao calcular correlação para {symbol}: {e}")
            result["data"]["reason"] = f"ERRO: {str(e)}"

        return result

    # -------------------------------------------------------------------------

    async def _get_macro_bias(self) -> Dict[str, Any]:
        """Calculates macro risk based on BTC variation and Dominance."""
        try:
            btc_var = okx_ws_public_service.btc_variation_1h
            btc_dom = await self._get_btc_dominance()

            # Risk Score Logic (0-10)
            risk_score = 5  # Neutral default

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
