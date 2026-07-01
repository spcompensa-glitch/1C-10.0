"""
[V120] Phase Detector — Detecção de Fase 1 (Acumulação) e Fase 2 (Compressão)

Detecta os estágios ANTES de uma explosão de preço (4-10%).
Combina OI, CVD, Volume, BB Width e Range num "Explosion Score".

Fase 1: Acumulação (2-6 horas)
  - OI crescendo enquanto preço fica lateral
  - CVD divergindo do preço (smart money)
  - Volume subindo gradualmente

Fase 2: Compressão (30min-2h)
  - BB Width no percentil mais baixo
  - Range diminuindo progressivamente
  - Volume secando (dry-up)

Fase 3: Detonação (5-30min)
  - Volume explode (confirmado pelo Explosion Score)

[V120.1] Persistência: dados são salvos no PostgreSQL e carregados no startup.
"""

import time
import logging
import asyncio
from collections import deque
from typing import Dict, Any, Optional, List

logger = logging.getLogger("PhaseDetector")


class PhaseDetector:
    """
    Detector de fases pré-explosão.
    Combina múltiplos indicadores num score composto (0-100).
    """

    def __init__(self):
        # OI History: {symbol: deque([{oi, ts}, ...], maxlen=48)}
        # 48 snapshots x 15min = 12 horas de histórico
        self._oi_history: Dict[str, deque] = {}

        # CVD History: {symbol: deque([{cvd, price, ts}, ...], maxlen=60)}
        # 60 snapshots x 1min = 1 hora de CVD para divergência
        self._cvd_price_history: Dict[str, deque] = {}

        # BB Width History: {symbol: deque([bb_width, ...], maxlen=100)}
        # 100 períodos para calcular percentil
        self._bb_width_history: Dict[str, deque] = {}

        # Volume History: {symbol: deque([volume, ...], maxlen=100)}
        self._volume_history: Dict[str, deque] = {}

        # Range History: {symbol: deque([{high, low, range_pct}, ...], maxlen=20)}
        self._range_history: Dict[str, deque] = {}

        # Cache de último snapshot por símbolo
        self._last_oi_snapshot: Dict[str, float] = {}
        self._last_oi_ts: Dict[str, float] = {}

        # [V120.1] Controle de persistência
        self._db_buffer: List[Dict[str, Any]] = []
        self._last_db_flush: float = 0.0
        self._flush_interval: float = 300.0  # Salvar a cada 5 minutos
        self._loaded_from_db: bool = False

    # ==================== DATABASE PERSISTENCE (V120.1) ====================

    async def load_history_from_db(self):
        """
        Carrega histórico do banco de dados na inicialização.
        Chamar uma vez no startup do sistema.
        """
        if self._loaded_from_db:
            return

        try:
            from services.database_service import database_service

            # Todos os pares monitorados (RADAR + DECOR + MASTER)
            from config import settings
            active_symbols = list(set(
                getattr(settings, 'RADAR_WATCHLIST', []) +
                getattr(settings, 'DECOR_WATCHLIST', []) +
                getattr(settings, 'MASTER_CONTEXT_ASSETS', [])
            ))

            loaded_count = 0
            for symbol in active_symbols:
                # Carregar OI history (últimas 12h)
                oi_data = await database_service.load_phase_detector_history(symbol, "OI", lookback_hours=12.0)
                if oi_data:
                    self._oi_history[symbol] = deque(maxlen=48)
                    for item in oi_data:
                        self._oi_history[symbol].append({"oi": item["value"], "ts": item["timestamp"]})
                    if self._oi_history[symbol]:
                        last = self._oi_history[symbol][-1]
                        self._last_oi_snapshot[symbol] = last["oi"]
                        self._last_oi_ts[symbol] = last["ts"]
                    loaded_count += len(oi_data)

                # Carregar CVD history (última 1h)
                cvd_data = await database_service.load_phase_detector_history(symbol, "CVD", lookback_hours=1.0)
                if cvd_data:
                    self._cvd_price_history[symbol] = deque(maxlen=60)
                    for item in cvd_data:
                        self._cvd_price_history[symbol].append(item["value"])
                    loaded_count += len(cvd_data)

                # Carregar BB Width history (últimas 12h)
                bb_data = await database_service.load_phase_detector_history(symbol, "BB_WIDTH", lookback_hours=12.0)
                if bb_data:
                    self._bb_width_history[symbol] = deque(maxlen=100)
                    for item in bb_data:
                        self._bb_width_history[symbol].append(item["value"])
                    loaded_count += len(bb_data)

                # Carregar Volume history (últimas 12h)
                vol_data = await database_service.load_phase_detector_history(symbol, "VOLUME", lookback_hours=12.0)
                if vol_data:
                    self._volume_history[symbol] = deque(maxlen=100)
                    for item in vol_data:
                        self._volume_history[symbol].append(item["value"])
                    loaded_count += len(vol_data)

                # Carregar Range history (últimas 6h)
                range_data = await database_service.load_phase_detector_history(symbol, "RANGE", lookback_hours=6.0)
                if range_data:
                    self._range_history[symbol] = deque(maxlen=20)
                    for item in range_data:
                        self._range_history[symbol].append(item["value"])
                    loaded_count += len(range_data)

            self._loaded_from_db = True
            logger.info(
                f"💾 [PHASE-DETECTOR] Histórico carregado do banco: {loaded_count} snapshots "
                f"para {len(active_symbols)} símbolos"
            )

            # Limpar dados antigos (>24h)
            await database_service.cleanup_old_phase_detector_data(max_age_hours=24.0)

        except Exception as e:
            logger.warning(f"[PHASE-DETECTOR] Erro ao carregar histórico do banco: {e}")
            self._loaded_from_db = True  # Marcar como carregado mesmo com erro para não tentar de novo

    def _queue_db_save(self, symbol: str, data_type: str, value: Any):
        """
        Adiciona snapshot ao buffer para salvar em batch.
        Não bloqueia o loop principal.
        """
        self._db_buffer.append({
            "symbol": symbol,
            "data_type": data_type,
            "value": value,
            "timestamp": time.time()
        })

    async def flush_db_buffer(self):
        """
        Salva o buffer acumulado no banco de dados.
        Chamar periodicamente (a cada 5 min).
        """
        if not self._db_buffer:
            return

        now = time.time()
        if now - self._last_db_flush < self._flush_interval:
            return

        try:
            from services.database_service import database_service
            batch = self._db_buffer.copy()
            self._db_buffer.clear()
            self._last_db_flush = now
            await database_service.save_phase_detector_batch(batch)
        except Exception as e:
            logger.debug(f"[PHASE-DETECTOR] Erro ao flush buffer: {e}")

    async def collect_periodic_data(self):
        """
        [V120.1] Coleta periódica de dados para todos os pares monitorados.
        Executa a cada 15 minutos para manter o histórico atualizado.
        Coleta: OI, CVD, BB Width, Volume, Range para cada par.
        """
        try:
            from config import settings
            from services.okx_rest import okx_rest_service
            from services.okx_ws_public import okx_ws_public_service

            # Todos os pares monitorados (RADAR + DECOR + MASTER)
            all_symbols = list(set(
                getattr(settings, 'RADAR_WATCHLIST', []) +
                getattr(settings, 'DECOR_WATCHLIST', []) +
                getattr(settings, 'MASTER_CONTEXT_ASSETS', [])
            ))

            collected = 0
            for symbol in all_symbols:
                try:
                    # 1. OI (Open Interest)
                    oi = okx_ws_public_service.oi_cache.get(symbol, 0)
                    if oi and oi > 0:
                        self.update_oi(symbol, oi)
                        collected += 1

                    # 2. CVD e Price
                    cvd = okx_ws_public_service.get_cvd_score_time(symbol, 300) or 0
                    price = okx_ws_public_service.get_current_price(symbol) or 0
                    if price > 0:
                        self.update_cvd_price(symbol, cvd, price)
                        collected += 1

                    # 3. BB Width (precisa de klines)
                    candles = await okx_rest_service.get_klines(symbol, interval="30", limit=20)
                    if candles and len(candles) >= 20:
                        closes = [float(c.get("close") or c[4]) for c in reversed(candles)]
                        # BB simples: média ± 2*std
                        if len(closes) >= 20:
                            sma = sum(closes[-20:]) / 20
                            std = (sum((c - sma) ** 2 for c in closes[-20:]) / 20) ** 0.5
                            bb_width = (4 * std / sma) * 100 if sma > 0 else 5.0
                            self.update_bb_width(symbol, bb_width)
                            collected += 1

                            # 4. Volume
                            volumes = [float(c.get("volCcy24h") or c.get("vol") or c[5]) for c in reversed(candles)]
                            if volumes:
                                self.update_volume(symbol, volumes[-1])
                                collected += 1

                            # 5. Range
                            highs = [float(c.get("high") or c[2]) for c in reversed(candles)]
                            lows = [float(c.get("low") or c[3]) for c in reversed(candles)]
                            if highs and lows:
                                self.update_range(symbol, highs[-1], lows[-1])
                                collected += 1

                except Exception as sym_err:
                    logger.debug(f"[PHASE-DETECTOR] Erro ao coletar dados para {symbol}: {sym_err}")
                    continue

            logger.info(
                f"📡 [PHASE-DETECTOR] Coleta periódica concluída: {collected} snapshots "
                f"para {len(all_symbols)} símbolos"
            )

        except Exception as e:
            logger.warning(f"[PHASE-DETECTOR] Erro na coleta periódica: {e}")

    async def fetch_okx_historical_data(self, symbols: List[str] = None):
        """
        [V120.1] Busca dados históricos da OKX e popula o banco de dados.
        Executar UMA VEZ no startup para ter histórico imediato.

        Coleta:
        - Klines 30M (20 candles = 10 horas) → BB Width, Volume, Range
        - Funding Rate History (100 snapshots) → Funding Bonus
        - OI atual → Open Interest
        """
        try:
            from config import settings
            from services.okx_rest import okx_rest_service

            if not symbols:
                symbols = list(set(
                    getattr(settings, 'RADAR_WATCHLIST', []) +
                    getattr(settings, 'DECOR_WATCHLIST', []) +
                    getattr(settings, 'MASTER_CONTEXT_ASSETS', [])
                ))

            logger.info(f"📡 [PHASE-DETECTOR] Buscando dados históricos da OKX para {len(symbols)} pares...")

            snapshots = []
            for symbol in symbols:
                try:
                    # 1. Klines 30M (últimos 20 candles = 10 horas)
                    candles = await okx_rest_service.get_klines(symbol, interval="30", limit=20)
                    if candles and len(candles) >= 10:
                        # OKX retorna mais novos primeiro, inverter
                        chronological = list(reversed(candles))

                        closes = [float(c.get("close") or c[4]) for c in chronological]
                        highs = [float(c.get("high") or c[2]) for c in chronological]
                        lows = [float(c.get("low") or c[3]) for c in chronological]
                        volumes = [float(c.get("volCcy24h") or c.get("vol") or c[5]) for c in chronological]
                        timestamps = [float(c.get("ts") or c[0]) / 1000.0 for c in chronological]

                        # BB Width para cada candle
                        for i in range(19, len(closes)):
                            window = closes[i-19:i+1]
                            sma = sum(window) / 20
                            std = (sum((c - sma) ** 2 for c in window) / 20) ** 0.5
                            bb_width = (4 * std / sma) * 100 if sma > 0 else 5.0
                            snapshots.append({
                                "symbol": symbol,
                                "data_type": "BB_WIDTH",
                                "value": bb_width,
                                "timestamp": timestamps[i]
                            })

                        # Volume para cada candle
                        for i, vol in enumerate(volumes):
                            snapshots.append({
                                "symbol": symbol,
                                "data_type": "VOLUME",
                                "value": vol,
                                "timestamp": timestamps[i]
                            })

                        # Range para cada candle
                        for i in range(len(highs)):
                            range_pct = ((highs[i] - lows[i]) / lows[i]) * 100.0 if lows[i] > 0 else 0
                            snapshots.append({
                                "symbol": symbol,
                                "data_type": "RANGE",
                                "value": {"high": highs[i], "low": lows[i], "range_pct": range_pct},
                                "timestamp": timestamps[i]
                            })

                    # 2. Funding Rate History (últimos 100 = ~33 horas se 20min interval)
                    funding_data = await okx_rest_service.get_funding_rate_history(symbol, limit=100)
                    if funding_data:
                        for item in funding_data:
                            rate = float(item.get("fundingRate", 0))
                            ts = int(item.get("fundingTime", 0)) / 1000.0
                            if ts > 0:
                                snapshots.append({
                                    "symbol": symbol,
                                    "data_type": "FUNDING",
                                    "value": rate,
                                    "timestamp": ts
                                })

                    # 3. OI atual (já temos no cache)
                    from services.okx_ws_public import okx_ws_public_service
                    oi = okx_ws_public_service.oi_cache.get(symbol, 0)
                    if oi and oi > 0:
                        snapshots.append({
                            "symbol": symbol,
                            "data_type": "OI",
                            "value": oi,
                            "timestamp": time.time()
                        })

                except Exception as sym_err:
                    logger.debug(f"[PHASE-DETECTOR] Erro ao buscar dados para {symbol}: {sym_err}")
                    continue

            # Salvar tudo no banco em batch
            if snapshots:
                from services.database_service import database_service
                await database_service.save_phase_detector_batch(snapshots)
                logger.info(
                    f"✅ [PHASE-DETECTOR] {len(snapshots)} snapshots históricos salvos no banco "
                    f"para {len(symbols)} pares"
                )

            # Recarregar em memória
            self._loaded_from_db = False
            await self.load_history_from_db()

        except Exception as e:
            logger.warning(f"[PHASE-DETECTOR] Erro ao buscar dados históricos: {e}")

    # ==================== OI TRACKING ====================

    def update_oi(self, symbol: str, oi_value: float):
        """
        Registra snapshot de OI. Chamar a cada 15min ou quando disponível.
        """
        if symbol not in self._oi_history:
            self._oi_history[symbol] = deque(maxlen=48)

        now = time.time()
        self._oi_history[symbol].append({
            "oi": oi_value,
            "ts": now
        })
        self._last_oi_snapshot[symbol] = oi_value
        self._last_oi_ts[symbol] = now

        # [V120.1] Queue para persistência no banco
        self._queue_db_save(symbol, "OI", oi_value)

    def get_oi_change_pct(self, symbol: str, lookback_hours: float = 4.0) -> Optional[float]:
        """
        Calcula variação percentual do OI nas últimas X horas.
        Retorna None se não há dados suficientes.
        """
        history = self._oi_history.get(symbol)
        if not history or len(history) < 2:
            return None

        now = time.time()
        cutoff = now - (lookback_hours * 3600)

        # Encontra o OI mais próximo do cutoff
        oldest_oi = None
        for snapshot in history:
            if snapshot["ts"] >= cutoff:
                oldest_oi = snapshot["oi"]
                break

        if oldest_oi is None or oldest_oi <= 0:
            return None

        current_oi = self._last_oi_snapshot.get(symbol, 0)
        if current_oi <= 0:
            return None

        return ((current_oi - oldest_oi) / oldest_oi) * 100.0

    # ==================== CVD DIVERGENCE ====================

    def update_cvd_price(self, symbol: str, cvd: float, price: float):
        """
        Registra snapshot de CVD + Preço para detectar divergência.
        Chamar a cada 1 minuto.
        """
        if symbol not in self._cvd_price_history:
            self._cvd_price_history[symbol] = deque(maxlen=60)

        snapshot = {
            "cvd": cvd,
            "price": price,
            "ts": time.time()
        }
        self._cvd_price_history[symbol].append(snapshot)

        # [V120.1] Queue para persistência no banco
        self._queue_db_save(symbol, "CVD", snapshot)

    def detect_cvd_divergence(self, symbol: str, lookback_minutes: int = 30) -> Dict[str, Any]:
        """
        Detecta divergência entre CVD e preço.

        Bullish Divergence: Preço faz lower low mas CVD faz higher low
          → Smart money comprando enquanto preço cai

        Bearish Divergence: Preço faz higher high mas CVD faz lower high
          → Smart money vendendo enquanto preço sobe

        Retorna: {"detected": bool, "type": "BULLISH"|"BEARISH"|"NONE", "strength": 0-100}
        """
        history = self._cvd_price_history.get(symbol)
        if not history or len(history) < 10:
            return {"detected": False, "type": "NONE", "strength": 0}

        # Pega os últimos N snapshots
        now = time.time()
        cutoff = now - (lookback_minutes * 60)
        recent = [h for h in history if h["ts"] >= cutoff]

        if len(recent) < 10:
            return {"detected": False, "type": "NONE", "strength": 0}

        # Divide em duas metades
        mid = len(recent) // 2
        first_half = recent[:mid]
        second_half = recent[mid:]

        # Calcula preço e CVD de cada metade
        price_first = sum(h["price"] for h in first_half) / len(first_half)
        price_second = sum(h["price"] for h in second_half) / len(second_half)
        cvd_first = sum(h["cvd"] for h in first_half) / len(first_half)
        cvd_second = sum(h["cvd"] for h in second_half) / len(second_half)

        price_change_pct = ((price_second - price_first) / price_first) * 100.0 if price_first > 0 else 0
        cvd_change = cvd_second - cvd_first

        # Bullish Divergence: preço cai mas CVD sobe
        if price_change_pct < -0.3 and cvd_change > 0:
            strength = min(100, int(abs(cvd_change) / 1000 + abs(price_change_pct) * 10))
            return {"detected": True, "type": "BULLISH", "strength": strength}

        # Bearish Divergence: preço sobe mas CVD cai
        if price_change_pct > 0.3 and cvd_change < 0:
            strength = min(100, int(abs(cvd_change) / 1000 + abs(price_change_pct) * 10))
            return {"detected": True, "type": "BEARISH", "strength": strength}

        return {"detected": False, "type": "NONE", "strength": 0}

    # ==================== VOLUME TREND ====================

    def update_volume(self, symbol: str, volume: float):
        """
        Registra volume de cada candle para análise de tendência.
        """
        if symbol not in self._volume_history:
            self._volume_history[symbol] = deque(maxlen=100)

        self._volume_history[symbol].append(volume)

        # [V120.1] Queue para persistência no banco
        self._queue_db_save(symbol, "VOLUME", volume)

    def get_volume_trend(self, symbol: str, short_periods: int = 5, long_periods: int = 20) -> Dict[str, Any]:
        """
        Analisa tendência do volume.

        volume_ratio = média curta / média longa
        - > 1.2 = volume crescendo (pressão se formando)
        - < 0.8 = volume secando (compressão)
        - 0.8-1.2 = neutro

        Retorna: {"ratio": float, "trend": "RISING"|"FALLING"|"FLAT", "score": 0-100}
        """
        history = self._volume_history.get(symbol)
        if not history or len(history) < long_periods:
            return {"ratio": 1.0, "trend": "FLAT", "score": 0}

        volumes = list(history)

        # Média curta (últimos N candles)
        short_avg = sum(volumes[-short_periods:]) / short_periods

        # Média longa (últimos M candles)
        long_avg = sum(volumes[-long_periods:]) / long_periods

        if long_avg <= 0:
            return {"ratio": 1.0, "trend": "FLAT", "score": 0}

        ratio = short_avg / long_avg

        if ratio > 1.2:
            trend = "RISING"
            score = min(100, int((ratio - 1.0) * 100))
        elif ratio < 0.8:
            trend = "FALLING"
            score = min(100, int((1.0 - ratio) * 100))
        else:
            trend = "FLAT"
            score = 0

        return {"ratio": ratio, "trend": trend, "score": score}

    # ==================== BB WIDTH PERCENTILE ====================

    def update_bb_width(self, symbol: str, bb_width: float):
        """
        Registra BB Width para cálculo de percentil histórico.
        """
        if symbol not in self._bb_width_history:
            self._bb_width_history[symbol] = deque(maxlen=100)

        self._bb_width_history[symbol].append(bb_width)

        # [V120.1] Queue para persistência no banco
        self._queue_db_save(symbol, "BB_WIDTH", bb_width)

    def get_bb_width_percentile(self, symbol: str) -> Dict[str, Any]:
        """
        Calcula em que percentil o BB Width atual está vs histórico.

        percentile < 10 = muito comprimido (Fase 2)
        percentile 10-30 = comprimido
        percentile 30-70 = normal
        percentile > 70 = expandido

        Retorna: {"percentile": float, "is_compressed": bool, "score": 0-100}
        """
        history = self._bb_width_history.get(symbol)
        if not history or len(history) < 20:
            return {"percentile": 50.0, "is_compressed": False, "score": 0}

        current = list(history)[-1]
        past = list(history)[:-1]

        # Conta quantos valores históricos são maiores que o atual
        higher_count = sum(1 for v in past if v > current)
        percentile = (higher_count / len(past)) * 100.0

        # Score: quanto menor o percentil, maior o score de compressão
        is_compressed = percentile < 20
        score = max(0, int((20 - percentile) * 5)) if percentile < 20 else 0

        return {
            "percentile": round(percentile, 1),
            "is_compressed": is_compressed,
            "score": min(100, score)
        }

    # ==================== RANGE COMPRESSION ====================

    def update_range(self, symbol: str, high: float, low: float):
        """
        Registra range de cada candle para detectar compressão progressiva.
        """
        if symbol not in self._range_history:
            self._range_history[symbol] = deque(maxlen=20)

        range_pct = ((high - low) / low) * 100.0 if low > 0 else 0
        snapshot = {
            "high": high,
            "low": low,
            "range_pct": range_pct,
            "ts": time.time()
        }
        self._range_history[symbol].append(snapshot)

        # [V120.1] Queue para persistência no banco
        self._queue_db_save(symbol, "RANGE", snapshot)

    def get_range_compression(self, symbol: str) -> Dict[str, Any]:
        """
        Detecta se o range está diminuindo progressivamente.

        Compara range médio dos últimos 5 candles vs 10 candles anteriores.
        Se diminuiu > 30% = compressão significativa.

        Retorna: {"compression_pct": float, "is_compressed": bool, "score": 0-100}
        """
        history = self._range_history.get(symbol)
        if not history or len(history) < 10:
            return {"compression_pct": 0, "is_compressed": False, "score": 0}

        ranges = [h["range_pct"] for h in history]

        # Range médio dos últimos 5
        recent_avg = sum(ranges[-5:]) / 5

        # Range médio dos 10 anteriores
        older_avg = sum(ranges[-15:-5]) / 10 if len(ranges) >= 15 else sum(ranges[:-5]) / max(1, len(ranges) - 5)

        if older_avg <= 0:
            return {"compression_pct": 0, "is_compressed": False, "score": 0}

        compression_pct = ((older_avg - recent_avg) / older_avg) * 100.0

        is_compressed = compression_pct > 30
        score = min(100, int(compression_pct * 2)) if compression_pct > 0 else 0

        return {
            "compression_pct": round(compression_pct, 1),
            "is_compressed": is_compressed,
            "score": min(100, score)
        }

    # ==================== PHASE 1: ACUMULAÇÃO ====================

    def detect_phase1(self, symbol: str, cvd: float, price: float, volume: float, oi_value: float = 0) -> Dict[str, Any]:
        """
        [V120] Detecta Fase 1: Acumulação.

        Combina:
        - OI crescendo (gente posicionando)
        - CVD divergindo do preço (smart money)
        - Volume crescendo gradualmente

        Retorna: {"score": 0-100, "signals": [...], "detected": bool}
        """
        signals = []
        total_score = 0

        # 1. OI Divergence (peso: 25)
        if oi_value > 0:
            self.update_oi(symbol, oi_value)
            oi_change = self.get_oi_change_pct(symbol, lookback_hours=4.0)
            if oi_change is not None and oi_change > 5:
                # OI crescendo > 5% em 4h = posicionamento
                oi_score = min(25, int(oi_change * 2.5))
                total_score += oi_score
                signals.append(f"OI+{oi_change:.1f}% (score={oi_score})")

        # 2. CVD Divergence (peso: 30)
        self.update_cvd_price(symbol, cvd, price)
        cvd_div = self.detect_cvd_divergence(symbol, lookback_minutes=30)
        if cvd_div["detected"]:
            cvd_score = min(30, int(cvd_div["strength"] * 0.3))
            total_score += cvd_score
            signals.append(f"CVD_{cvd_div['type']} (score={cvd_score})")

        # 3. Volume Trend (peso: 20)
        self.update_volume(symbol, volume)
        vol_trend = self.get_volume_trend(symbol)
        if vol_trend["trend"] == "RISING":
            vol_score = min(20, int(vol_trend["score"] * 0.2))
            total_score += vol_score
            signals.append(f"VOL_RISING ratio={vol_trend['ratio']:.2f} (score={vol_score})")

        detected = total_score >= 40

        return {
            "score": min(100, total_score),
            "signals": signals,
            "detected": detected
        }

    # ==================== PHASE 2: COMPRESSÃO ====================

    def detect_phase2(self, symbol: str, bb_width: float, high: float, low: float, volume: float) -> Dict[str, Any]:
        """
        [V120] Detecta Fase 2: Compressão.

        Combina:
        - BB Width no percentil mais baixo (comprimido)
        - Range diminuindo progressivamente
        - Volume secando (dry-up)

        Retorna: {"score": 0-100, "signals": [...], "detected": bool}
        """
        signals = []
        total_score = 0

        # 1. BB Width Percentile (peso: 30)
        self.update_bb_width(symbol, bb_width)
        bb_info = self.get_bb_width_percentile(symbol)
        if bb_info["is_compressed"]:
            bb_score = min(30, bb_info["score"])
            total_score += bb_score
            signals.append(f"BB_P{bb_info['percentile']:.0f} (score={bb_score})")

        # 2. Range Compression (peso: 35)
        self.update_range(symbol, high, low)
        range_info = self.get_range_compression(symbol)
        if range_info["is_compressed"]:
            range_score = min(35, range_info["score"])
            total_score += range_score
            signals.append(f"RANGE_{range_info['compression_pct']:.0f}% (score={range_score})")

        # 3. Volume Dry-up (peso: 25)
        vol_trend = self.get_volume_trend(symbol)
        if vol_trend["trend"] == "FALLING":
            vol_score = min(25, int(vol_trend["score"] * 0.25))
            total_score += vol_score
            signals.append(f"VOL_DRY ratio={vol_trend['ratio']:.2f} (score={vol_score})")

        detected = total_score >= 50

        return {
            "score": min(100, total_score),
            "signals": signals,
            "detected": detected
        }

    # ==================== EXPLOSION SCORE ====================

    def calculate_explosion_score(
        self,
        symbol: str,
        cvd: float,
        price: float,
        volume: float,
        bb_width: float,
        high: float,
        low: float,
        oi_value: float = 0,
        funding_rate: float = 0.0
    ) -> Dict[str, Any]:
        """
        [V120] Calcula o Explosion Score composto (0-100).

        Combina Fase 1 + Fase 2 + indicadores extras.

        Score >= 60 = sinal de entrada (confiança moderada)
        Score >= 75 = sinal forte (confiança alta)
        Score >= 90 = sinal premium (confiança máxima)

        Retorna: {
            "score": int (0-100),
            "phase1": {...},
            "phase2": {...},
            "funding_bonus": int,
            "total_signals": [...],
            "recommendation": "ENTER"|"WAIT"|"NO_SIGNAL"
        }
        """
        total_signals = []

        # Fase 1
        phase1 = self.detect_phase1(symbol, cvd, price, volume, oi_value)
        total_signals.extend([f"P1:{s}" for s in phase1["signals"]])

        # Fase 2
        phase2 = self.detect_phase2(symbol, bb_width, high, low, volume)
        total_signals.extend([f"P2:{s}" for s in phase2["signals"]])

        # Base score = Fase 1 + Fase 2
        base_score = phase1["score"] + phase2["score"]

        # Funding bonus (peso: 15)
        funding_bonus = 0
        if abs(funding_rate) > 0.001:
            funding_bonus = min(15, int(abs(funding_rate) * 5000))
            total_signals.append(f"FUNDING={funding_rate:.4f} (bonus={funding_bonus})")

        total_score = min(100, base_score + funding_bonus)

        # Recomendação
        if total_score >= 90:
            recommendation = "ENTER"
        elif total_score >= 75:
            recommendation = "ENTER"
        elif total_score >= 60:
            recommendation = "ENTER"
        else:
            recommendation = "WAIT"

        return {
            "score": total_score,
            "phase1": phase1,
            "phase2": phase2,
            "funding_bonus": funding_bonus,
            "total_signals": total_signals,
            "recommendation": recommendation
        }


# Instância global
phase_detector = PhaseDetector()
