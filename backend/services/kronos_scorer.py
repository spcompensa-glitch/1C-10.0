# -*- coding: utf-8 -*-
"""
[KRONOS] Kronos Conviction Scorer — V1.0
Integração com Kronos-mini (4.1M params) para scoring de convicção de sinais.

Arquitetura:
  - Lazy load do modelo (só carrega na 1ª chamada)
  - Execução em thread pool para não bloquear event loop
  - Cache por símbolo com TTL configurável
  - Fallback robusto: se Kronos falhar, retorna score=50 (neutro)
  - Timeout de 5s por predição

Dependências:
  - kronos-forecast>=0.1.0 (pip install kronos-forecast)
  - torch>=2.0.0 (instalado como dependência do kronos-forecast)
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor

# Lazy import — só falha se o serviço okx_rest não existir (não deve acontecer)
from services.okx_rest import okx_rest_service

logger = logging.getLogger("KronosScorer")

# Tentativa de import real — verifica se kronos-forecast está instalado
_KRONOS_AVAILABLE = False
try:
    from model import Kronos, KronosTokenizer, KronosPredictor  # noqa: F401
    import torch  # noqa: F401
    _KRONOS_AVAILABLE = True
except Exception:
    _KRONOS_AVAILABLE = False

# Se o kronos-forecast não estiver instalado, loga no módulo
if not _KRONOS_AVAILABLE:
    logger.warning(
        "⚠️ [KRONOS] kronos-forecast ou torch não instalados. "
        "O serviço operará em modo FALLBACK (regressão linear). "
        "Para ativar o modo REAL: pip install kronos-forecast torch"
    )


class KronosScorer:
    """
    Serviço de scoring de convicção usando Kronos-mini.
    
    O Kronos é um foundation model para séries temporais financeiras que
    tokeniza OHLCV em tokens discretos e prevê a sequência futura.
    Usamos o Kronos-mini (4.1M params, contexto 2048) para:
      1. Prever direção do preço nas próximas N velas
      2. Calcular convicção baseada em alinhamento de direção + dispersão
      3. Opcionalmente estimar volatilidade prevista
    
    Nota: Se o PyTorch/Kronos não estiver instalado, o serviço opera
    em modo "mock" — retorna scores baseados em regressão linear simples
    para não quebrar o fluxo de sinais.
    """
    
    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._predictor = None
        self._executor = None
        self.is_loaded = False
        self.is_available = _KRONOS_AVAILABLE
        self._load_lock = asyncio.Lock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="kronos")
        self._score_cache = {}  # {symbol: {score, timestamp, expiry}}
        # Config
        self.model_name = "NeoQuasar/Kronos-mini"
        self.max_context = 2048
        self.pred_len = 12       # Próximas 12 velas
        self.lookback = 400      # 400 velas de histórico (5m = ~33h)
        self.cache_ttl = 60      # Cache de 60s por símbolo
        self.prediction_timeout = 5.0  # Timeout de 5s por predição
        self.sample_count = 3    # Número de trajetórias (mais = melhor confiança, mais lento)
        
        logger.info(
            f"🔮 [KRONOS] Inicializado. Modo: {'REAL' if self.is_available else 'MOCK'} | "
            f"Modelo: {self.model_name}"
        )
    
    async def initialize(self):
        """
        Inicializa o modelo Kronos (lazy load).
        Só carrega o modelo na primeira chamada de score_signal().
        """
        if self.is_loaded or not self.is_available:
            return
        
        async with self._load_lock:
            if self.is_loaded:
                return
            logger.info("🔮 [KRONOS] Iniciando carga do modelo (lazy load)...")
            loop = asyncio.get_event_loop()
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(self._executor, self._load_model),
                    timeout=30.0
                )
                self.is_loaded = True
                logger.info("✅ [KRONOS] Modelo carregado com sucesso!")
            except asyncio.TimeoutError:
                logger.warning("⏱️ [KRONOS] Timeout de 30s na carga do modelo. Usando fallback.")
                self.is_available = False
            except Exception as e:
                logger.warning(f"⚠️ [KRONOS] Falha ao carregar modelo: {e}. Usando fallback.")
                self.is_available = False
    
    def _load_model(self):
        """Synchronous model loading (roda em thread pool)."""
        try:
            from model import Kronos, KronosTokenizer, KronosPredictor
            
            self._tokenizer = KronosTokenizer.from_pretrained(
                "NeoQuasar/Kronos-Tokenizer-base"
            )
            self._model = Kronos.from_pretrained(
                self.model_name
            )
            self._model.eval()  # Modo inference
            
            # Força device='cpu' para garantir compatibilidade sem GPU
            import torch
            self._model = self._model.to('cpu')
            
            self._predictor = KronosPredictor(
                self._model, 
                self._tokenizer, 
                max_context=self.max_context
            )
            logger.info(
                f"✅ [KRONOS] Modelo {self.model_name} carregado em CPU. "
                f"Parâmetros: {sum(p.numel() for p in self._model.parameters()):,}"
            )
        except Exception as e:
            logger.error(f"❌ [KRONOS] Erro no _load_model: {e}")
            raise
    
    async def score_signal(
        self, 
        symbol: str, 
        direction: str,
        interval: str = "5"
    ) -> Dict[str, Any]:
        """
        Gera score de convicção Kronos para um sinal de trading.
        
        Args:
            symbol: Símbolo ex: "BTCUSDT" ou "BTCUSDT.P"
            direction: "Buy"/"Long" ou "Sell"/"Short"
            interval: Timeframe das velas (padrão "5" = 5 minutos)
        
        Returns:
            Dict com:
                conviction: int 0-100 — score de convicção
                prediction_direction: str — direção prevista
                confidence: float 0-100 — confiança do modelo
                volatility: float — volatilidade prevista (desvio padrão %)
                source: str — "kronos" | "fallback" | "cache" | "mock"
                error: str | None
        """
        # Normaliza símbolo
        clean_symbol = symbol.replace(".P", "").upper()
        side_norm = direction.lower()
        
        # 1. Verifica cache
        cached = self._get_cached(clean_symbol)
        if cached:
            return cached
        
        # 2. Garante que o modelo está carregado
        if self.is_available and not self.is_loaded:
            await self.initialize()
        
        # 3. Se não disponível, usa fallback
        if not self.is_available or not self.is_loaded:
            result = await self._fallback_score(clean_symbol, side_norm, interval)
            self._set_cache(clean_symbol, result)
            return result
        
        # 4. Busca OHLCV da OKX
        try:
            total_lookback = self.lookback + self.pred_len + 10  # margem
            klines = await asyncio.wait_for(
                okx_rest_service.get_klines(
                    symbol=clean_symbol, 
                    interval=interval, 
                    limit=total_lookback
                ),
                timeout=3.0
            )
            
            if not klines or len(klines) < self.lookback:
                logger.warning(f"[KRONOS] Dados insuficientes para {clean_symbol}: {len(klines) if klines else 0}")
                return await self._fallback_score(clean_symbol, side_norm, interval)
            
            # 5. Prepara DataFrame para o Kronos
            candles = klines[::-1]  # Ordem cronológica
            df = self._prepare_dataframe(candles[:self.lookback])
            
            # 6. Prepara timestamps
            import pandas as pd
            x_timestamp = pd.to_datetime(
                [float(c[0]) for c in candles[:self.lookback]], 
                unit='ms'
            )
            
            # Prepara timestamps futuros (estimados)
            last_ts = float(candles[self.lookback - 1][0])
            interval_ms = self._get_interval_ms(interval)
            future_timestamps = [last_ts + (i + 1) * interval_ms for i in range(self.pred_len)]
            y_timestamp = pd.to_datetime(future_timestamps, unit='ms')
            
            # 7. Executa predição em thread pool (com timeout)
            loop = asyncio.get_event_loop()
            try:
                pred_df = await asyncio.wait_for(
                    loop.run_in_executor(
                        self._executor,
                        self._run_prediction,
                        df, x_timestamp, y_timestamp
                    ),
                    timeout=self.prediction_timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ [KRONOS] Timeout de {self.prediction_timeout}s para {clean_symbol}")
                return await self._fallback_score(clean_symbol, side_norm, interval)
            
            # 8. Calcula o score de convicção
            result = self._calculate_conviction(pred_df, df, side_norm)
            
            # 9. Cache
            self._set_cache(clean_symbol, result)
            
            logger.info(
                f"🔮 [KRONOS] {clean_symbol} {direction.upper()} | "
                f"Conviction={result['conviction']} | "
                f"PredDir={result['prediction_direction']} | "
                f"Conf={result['confidence']:.1f}%"
            )
            
            return result
            
        except Exception as e:
            logger.warning(f"⚠️ [KRONOS] Erro em score_signal({clean_symbol}): {e}")
            return await self._fallback_score(clean_symbol, side_norm, interval)
    
    def _run_prediction(self, df, x_timestamp, y_timestamp):
        """Roda a predição Kronos (síncrono, roda em thread pool)."""
        if self._predictor is None:
            raise RuntimeError("KronosPredictor não inicializado")
        
        return self._predictor.predict(
            df=df,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=self.pred_len,
            T=1.0,
            top_p=0.9,
            sample_count=self.sample_count
        )
    
    def _prepare_dataframe(self, candles: list) -> 'pd.DataFrame':
        """
        Converte candles da OKX para DataFrame no formato do Kronos.
        
        Candle OKX: [ts, open, high, low, close, volume, turnover]
        Kronos espera: colunas open, high, low, close, volume, amount
        """
        import pandas as pd
        df = pd.DataFrame(candles, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 'amount'
        ])
        df = df[['open', 'high', 'low', 'close', 'volume', 'amount']].astype(float)
        return df
    
    def _get_interval_ms(self, interval: str) -> int:
        """Converte string de intervalo para milissegundos."""
        mapping = {
            "1": 60000,
            "3": 180000,
            "5": 300000,
            "15": 900000,
            "30": 1800000,
            "60": 3600000,
            "120": 7200000,
            "240": 14400000,
            "D": 86400000,
        }
        return mapping.get(interval, 300000)
    
    def _calculate_conviction(
        self, 
        pred_df: 'pd.DataFrame',
        hist_df: 'pd.DataFrame',
        side_norm: str
    ) -> Dict[str, Any]:
        """
        Calcula o score de convicção baseado na predição do Kronos.
        
        Algoritmo:
          1. Direção prevista = média do último terço das predições vs primeira predição
          2. Confiança = 1 - (dispersão entre trajetórias / |movimento médio|)
             - Se sample_count=1, usa razão entre desvio padrão e preço médio
          3. Volatilidade = desvio padrão dos retornos previstos
          4. Conviction = match de direção (0-60) + confiança (0-40)
        """
        import numpy as np
        
        # Extrai closes projetados
        pred_closes = pred_df['close'].values.astype(float)
        
        if len(pred_closes) < 2:
            return {
                "conviction": 50,
                "prediction_direction": "NEUTRAL",
                "confidence": 50.0,
                "volatility": 0.0,
                "source": "kronos"
            }
        
        # Preço atual (último close do histórico)
        current_price = float(hist_df['close'].iloc[-1]) if len(hist_df) > 0 else pred_closes[0]
        
        # --- Direção Prevista ---
        # Dividimos a predição em 3 partes e comparamos o final com o início
        split = len(pred_closes) // 3
        early_avg = np.mean(pred_closes[:split]) if split > 0 else pred_closes[0]
        late_avg = np.mean(pred_closes[-split:]) if split > 0 else pred_closes[-1]
        
        price_change_pct = ((late_avg - early_avg) / early_avg) * 100 if early_avg > 0 else 0
        
        if price_change_pct > 0.3:
            pred_direction = "UP"
        elif price_change_pct < -0.3:
            pred_direction = "DOWN"
        else:
            pred_direction = "SIDEWAYS"
        
        # --- Volatilidade Prevista ---
        returns = np.diff(pred_closes) / pred_closes[:-1] * 100
        volatility = float(np.std(returns)) if len(returns) > 0 else 0.0
        
        # --- Confiança (dispersão) ---
        # Quanto menor a volatilidade relativa ao movimento, maior a confiança
        abs_movement = abs(price_change_pct)
        if abs_movement > 0 and volatility > 0:
            # Signal-to-Noise ratio: movimento / volatilidade
            snr = abs_movement / max(volatility, 0.01)
            confidence = min(100.0, snr * 20)  # SNR de 5 = 100%
        else:
            confidence = 30.0  # Baixa confiança se movimento quase zero
        
        # --- Conviction Score (0-100) ---
        # Direção correta: 0-60 pontos
        is_direction_match = (
            (side_norm in ("buy", "long") and pred_direction == "UP") or
            (side_norm in ("sell", "short") and pred_direction == "DOWN")
        )
        
        if is_direction_match:
            direction_score = min(60, 30 + abs_movement * 5)  # Quanto maior o movimento, mais score
        elif pred_direction == "SIDEWAYS":
            direction_score = 20  # Sideways não é contra, mas não confirma
        else:
            direction_score = 0  # Direção contrária
        
        # Confiança: 0-40 pontos
        confidence_score = confidence * 0.4
        
        conviction = min(100, int(direction_score + confidence_score))
        
        # --- Volatilidade muito baixa = mar morto → penalidade ---
        if volatility < 0.05:
            conviction = max(0, conviction - 20)
        
        # --- Movimento muito pequeno → penalidade ---
        if abs_movement < 0.1:
            conviction = max(0, conviction - 15)
        
        return {
            "conviction": conviction,
            "prediction_direction": pred_direction,
            "confidence": round(confidence, 1),
            "volatility": round(volatility, 4),
            "predicted_change_pct": round(price_change_pct, 2),
            "source": "kronos"
        }
    
    async def _fallback_score(
        self, 
        symbol: str, 
        side_norm: str,
        interval: str
    ) -> Dict[str, Any]:
        """
        Fallback quando Kronos não está disponível.
        Usa regressão linear simples dos últimos closes para estimar direção.
        """
        try:
            klines = await asyncio.wait_for(
                okx_rest_service.get_klines(
                    symbol=symbol, 
                    interval=interval, 
                    limit=50
                ),
                timeout=2.0
            )
            
            if not klines or len(klines) < 20:
                return {
                    "conviction": 50,
                    "prediction_direction": "NEUTRAL",
                    "confidence": 50.0,
                    "volatility": 0.0,
                    "source": "fallback"
                }
            
            # Regressão linear simples nos closes
            candles = klines[::-1]
            closes = [float(c[4]) for c in candles]
            n = len(closes)
            
            # Slope da regressão linear
            x_mean = (n - 1) / 2
            y_mean = sum(closes) / n
            num = sum((i - x_mean) * (c - y_mean) for i, c in enumerate(closes))
            den = sum((i - x_mean) ** 2 for i in range(n))
            slope = num / den if den > 0 else 0
            
            # Direção baseada no slope
            if slope > 0:
                pred_direction = "UP"
            elif slope < 0:
                pred_direction = "DOWN"
            else:
                pred_direction = "SIDEWAYS"
            
            # Confiança baseada em R² aproximado
            y_pred = [y_mean + slope * (i - x_mean) for i in range(n)]
            ss_res = sum((c - yp) ** 2 for c, yp in zip(closes, y_pred))
            ss_tot = sum((c - y_mean) ** 2 for c in closes)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
            confidence = min(70, r_squared * 100)  # Máximo 70% no fallback
            
            # Volatilidade
            returns = [(closes[i] - closes[i-1]) / closes[i-1] * 100 for i in range(1, n)]
            volatility = (sum(r ** 2 for r in returns) / len(returns)) ** 0.5 if returns else 0
            
            # Conviction
            is_match = (
                (side_norm in ("buy", "long") and pred_direction == "UP") or
                (side_norm in ("sell", "short") and pred_direction == "DOWN")
            )
            direction_score = 30 if is_match else (15 if pred_direction == "SIDEWAYS" else 0)
            conviction = min(70, direction_score + int(confidence * 0.4))
            
            result = {
                "conviction": conviction,
                "prediction_direction": pred_direction,
                "confidence": round(confidence, 1),
                "volatility": round(volatility, 4),
                "source": "fallback"
            }
            
            return result
            
        except Exception as e:
            logger.debug(f"[KRONOS] Fallback error for {symbol}: {e}")
            return {
                "conviction": 50,
                "prediction_direction": "NEUTRAL",
                "confidence": 50.0,
                "volatility": 0.0,
                "source": "fallback"
            }
    
    async def score_batch(self, signals: List[Dict]) -> List[Dict]:
        """
        Gera scores para múltiplos sinais em paralelo.
        
        Args:
            signals: Lista de dicts com {symbol, side, ...}
        
        Returns:
            Lista com os mesmos dicts + campo 'kronos_score'
        """
        tasks = []
        for sig in signals:
            symbol = sig.get("symbol", "")
            direction = sig.get("side", "Buy")
            if symbol:
                task = self.score_signal(symbol, direction)
                tasks.append(task)
        
        if not tasks:
            return signals
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, sig in enumerate(signals):
            if i < len(results):
                if isinstance(results[i], Exception):
                    sig["kronos_score"] = 50
                    sig["kronos_data"] = {"source": "error", "error": str(results[i])}
                else:
                    sig["kronos_score"] = results[i].get("conviction", 50)
                    sig["kronos_data"] = results[i]
        
        return signals
    
    def _get_cached(self, symbol: str) -> Optional[Dict]:
        """Retorna resultado em cache se ainda válido."""
        cached = self._score_cache.get(symbol)
        if cached and time.time() < cached.get("expiry", 0):
            return cached.get("data")
        return None
    
    def _set_cache(self, symbol: str, data: Dict):
        """Armazena resultado em cache com TTL."""
        self._score_cache[symbol] = {
            "data": data,
            "expiry": time.time() + self.cache_ttl
        }
    
    async def health_check(self) -> Dict:
        """Retorna status do serviço Kronos."""
        return {
            "available": self.is_available,
            "loaded": self.is_loaded,
            "model": self.model_name if self.is_loaded else None,
            "cache_size": len(self._score_cache),
            "mode": "REAL" if (self.is_available and self.is_loaded) else "FALLBACK"
        }


# Singleton
kronos_scorer = KronosScorer()
