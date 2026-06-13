# -*- coding: utf-8 -*-
"""
⚡ BLITZ SNIPER AGENT — V110.137
Dual Elite Extraction Agent (Slots 1 e 2)

Doutrina: Doutrina das 10 Extracoes — Step-Lock a cada 100% ROI.
Alvo: 10 unidades/dia x 100% ROI. Score minimo: 80.
Moonbag condicional via Ceifeiro apos 300% ROI.

Indicadores Utilizados:
  1. Fibonacci (Golden Zone M30)
  2. SMA Crossover (SMA9 x SMA21 no M30 — Confirmacao de Momentum)
  3. CVD (Cumulative Volume Delta — Pressao Institucional)
  4. Price Action M30 (Wick Reclaim, Sweep & Reclaim, Engulf)
  5. Volume Relativo (Confirmacao de forca do movimento)
  6. Librarian DNA (Wick-Adaptive Breakeven — RETEST_HEAVY/EXTREME)
"""

import logging
import asyncio
import time
from typing import Dict, Any, List, Optional, Tuple
from services.agents.aios_adapter import AIOSAgent

logger = logging.getLogger("BlitzSniperAgent")


class BlitzSniperAgent(AIOSAgent):
    """
    [V110.136] Agente especializado em captura de reversões e expansões no M30.
    Alimenta exclusivamente o Slot 1 (BLITZ_30M) com sinais de alta precisão.
    """

    def __init__(self):
        super().__init__(
            agent_id="agent-blitz-sniper",
            role="blitz_sniper",
            capabilities=["blitz_scanning", "m30_analysis", "momentum_extraction"]
        )
        self.last_scan_time = {}         # { symbol: timestamp }
        self.scan_cooldown = 300         # 5 minutos entre scans do mesmo ativo
        self.signal_cache = {}           # { symbol: { 'signal': dict, 'at': timestamp } }
        self.signal_cache_ttl = 120      # 2 minutos

    async def on_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Implementação obrigatória do protocolo AIOSAgent."""
        return {"status": "ok"}

    # =========================================================================
    # ████  SCAN PRINCIPAL — M30 BLITZ  ████
    # =========================================================================

    async def scan_for_blitz_signal(
        self,
        symbol: str,
        btc_direction: str = "LATERAL",
        btc_adx: float = 0.0
    ) -> Optional[Dict[str, Any]]:
        """
        Analisa o ativo no TF 30M e retorna um sinal de entrada BLITZ se todos
        os critérios forem satisfeitos.

        Returns:
            Um dicionário de sinal ou None se nenhum setup de qualidade for encontrado.
        """
        try:
            from services.okx_rest import okx_rest_service
            from services.okx_ws_public import okx_ws_public_service

            # Throttle: Evita scans repetidos para o mesmo ativo
            now = time.time()
            last = self.last_scan_time.get(symbol, 0)
            if now - last < self.scan_cooldown:
                return None
            self.last_scan_time[symbol] = now

            # ── 1. Busca candles M30 (últimos 60 = 30 horas de dados)
            klines = await okx_rest_service.get_klines(symbol=symbol, interval="30", limit=60)
            if not klines or len(klines) < 30:
                return None

            # Bybit retorna os mais recentes primeiro — inverter para ordem cronológica
            candles = list(reversed(klines))
            closes  = [float(c[4]) for c in candles]
            highs   = [float(c[2]) for c in candles]
            lows    = [float(c[3]) for c in candles]
            volumes = []
            for c in candles:
                try:
                    volumes.append(float(c[5]))
                except (IndexError, ValueError):
                    volumes.append(0.0)

            # ── 2. Calcula indicadores
            sma9  = self._sma(closes, 9)
            sma21 = self._sma(closes, 21)
            fib   = self._fibonacci_levels(highs, lows, lookback=30)
            vol_avg_10 = sum(volumes[-11:-1]) / 10.0 if len(volumes) >= 11 else 1.0
            last_vol   = volumes[-1]
            cvd        = okx_ws_public_service.get_cvd_score(symbol)

            current_close = closes[-1]
            current_high  = highs[-1]
            current_low   = lows[-1]

            # ── 3. Validação de Momentum: Crossover ou Alinhamento Estabelecido
            # [V110.136-SENSITIVITY] Expandimos para detectar cruzamentos até 10 candles atrás
            # ou validar se as médias já estão alinhadas (Trend Following Blitz).
            cross_result = self._detect_sma_crossover(sma9, sma21)
            
            side = "NONE"
            entry_type = "CROSSOVER"

            if cross_result["direction"] != "NONE":
                side = "Buy" if cross_result["direction"] == "UP" else "Sell"
                entry_type = f"CROSSOVER ({cross_result['candles_ago']} bars ago)"
            else:
                # Se não houve cruzamento recente, verificamos o alinhamento atual (Trend Following)
                if len(sma9) >= 2 and len(sma21) >= 2:
                    s9_now, s21_now = sma9[-1], sma21[-1]
                    s9_prev, s21_prev = sma9[-2], sma21[-2]
                    
                    if s9_now > s21_now and s9_prev > s21_prev:
                        side = "Buy"
                        entry_type = "TREND_ALIGNMENT"
                    elif s9_now < s21_now and s9_prev < s21_prev:
                        side = "Sell"
                        entry_type = "TREND_ALIGNMENT"

            if side == "NONE":
                return None  # Médias emboladas ou sem tendência clara

            # ── 4. Filtro de BTC Direction (não opera contra tendência violenta)
            if btc_direction == "UP" and side == "Sell" and btc_adx >= 30:
                logger.debug(f"⚡ [BLITZ-FILTER] {symbol} SELL negado — BTC em alta forte (ADX={btc_adx:.1f})")
                return None
            if btc_direction == "DOWN" and side == "Buy" and btc_adx >= 30:
                logger.debug(f"⚡ [BLITZ-FILTER] {symbol} BUY negado — BTC em queda forte (ADX={btc_adx:.1f})")
                return None

            # ── 5. Score composto (100 pontos possíveis)
            score = 0
            reasons = []

            # Critério A: Fibonacci Golden Zone (0.618 - 0.786) — até 30 pts
            fib_score, fib_reason = self._score_fibonacci(
                current_close, current_low, current_high, fib, side
            )
            score += fib_score
            if fib_reason:
                reasons.append(fib_reason)

            # Critério B: Volume Relativo (≥ 1.5x médio) — até 20 pts
            if last_vol >= vol_avg_10 * 2.0:
                score += 20
                reasons.append(f"Volume 2x+ (Vol={last_vol:.0f} | Avg={vol_avg_10:.0f})")
            elif last_vol >= vol_avg_10 * 1.5:
                score += 15
                reasons.append(f"Volume 1.5x (Vol={last_vol:.0f} | Avg={vol_avg_10:.0f})")
            elif last_vol >= vol_avg_10 * 1.2:
                score += 8
                reasons.append(f"Volume acima da média ({last_vol:.0f})")

            # Critério C: CVD Institucional — até 25 pts
            cvd_score, cvd_reason = self._score_cvd(cvd, side)
            score += cvd_score
            if cvd_reason:
                reasons.append(cvd_reason)

            # Critério D: Price Action Pattern (Wick Reclaim / Sweep & Reclaim / Engulf) — até 25 pts
            pa_score, pa_reason = self._detect_price_action(candles, closes, highs, lows, side)
            score += pa_score
            if pa_reason:
                reasons.append(pa_reason)

            # ── 6. Threshold mínimo de entrada BLITZ (Score ≥ 75) [V110.137]
            if score < 75:
                logger.debug(
                    f"⚡ [BLITZ-SKIP] {symbol} {side} ({entry_type}) — Score {score}/100 insuficiente (<80). "
                    f"Razões: {', '.join(reasons) or 'Nenhuma condição forte'}"
                )
                return None

            # ── 7. Signal de alta qualidade encontrado
            reason_str = f"[{entry_type}] " + (" | ".join(reasons) if reasons else "SMA M30")
            logger.info(
                f"⚡ [BLITZ-SIGNAL] 🎯 {symbol} {side} | Score: {score}/100 | "
                f"CVD: {cvd:.0f} | Razão: {reason_str}"
            )

            signal = {
                "id":              f"blitz_{symbol.replace('.P','')}_{int(time.time())}",
                "symbol":          symbol,
                "side":            side,
                "score":           score,
                "layer":           "BLITZ",
                "is_blitz":        True,                # [V110.136] Flag para prioridade no Capitão
                "slot_type":       "BLITZ_30M",
                "target_slot":     None,                # [V110.137] Bankroll decide slot 1 ou 2
                "timeframe":       "30",
                "strategy":        "BLITZ_SNIPER",
                "indicators": {
                    "sma_cross":    cross_result["direction"],
                    "fib_zone":     fib.get("golden_zone"),
                    "cvd":          cvd,
                    "volume_ratio": round(last_vol / vol_avg_10, 2) if vol_avg_10 > 0 else 0,
                    "pa_pattern":   pa_reason,
                    "score":        score,
                },
                "reasons":         reasons,
                "leverage":        50,                  # [V110.136] Forçado 50x conforme pedido do usuário
                "timestamp":       time.time(),
            }

            # Cache
            self.signal_cache[symbol] = {"signal": signal, "at": time.time()}
            return signal

        except Exception as e:
            logger.error(f"❌ [BLITZ-ERROR] {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return None

    # =========================================================================
    # ████  INDICADORES  ████
    # =========================================================================

    def _sma(self, data: List[float], period: int) -> List[Optional[float]]:
        """Calcula Simple Moving Average."""
        result: List[Optional[float]] = []
        for i in range(len(data)):
            if i < period - 1:
                result.append(None)
            else:
                window = data[i - period + 1: i + 1]
                result.append(sum(window) / period)
        return result

    def _detect_sma_crossover(
        self, sma9: List[Optional[float]], sma21: List[Optional[float]]
    ) -> Dict[str, Any]:
        """
        Detecta cruzamento de SMA9 com SMA21 nos últimos 3 candles M30.
        Retorna: { 'direction': 'UP' | 'DOWN' | 'NONE', 'candles_ago': int }
        """
        # Precisa de ao menos 3 valores válidos
        if len(sma9) < 3 or len(sma21) < 3:
            return {"direction": "NONE", "candles_ago": 0}

        for i in range(-1, -11, -1):  # Últimos 10 candles (5 horas no M30)
            try:
                s9_now  = sma9[i]
                s21_now = sma21[i]
                s9_prev  = sma9[i - 1]
                s21_prev = sma21[i - 1]

                if None in (s9_now, s21_now, s9_prev, s21_prev):
                    continue

                # Cruzamento Altista: SMA9 cruzou acima da SMA21
                if s9_prev <= s21_prev and s9_now > s21_now:
                    return {"direction": "UP", "candles_ago": abs(i + 1)}

                # Cruzamento Baixista: SMA9 cruzou abaixo da SMA21
                if s9_prev >= s21_prev and s9_now < s21_now:
                    return {"direction": "DOWN", "candles_ago": abs(i + 1)}

            except IndexError:
                continue

        return {"direction": "NONE", "candles_ago": 0}

    def _fibonacci_levels(
        self, highs: List[float], lows: List[float], lookback: int = 30
    ) -> Dict[str, Any]:
        """
        Calcula níveis de Fibonacci do swing mais recente nos últimos N candles.
        """
        if len(highs) < lookback or len(lows) < lookback:
            return {}

        window_h = highs[-lookback:]
        window_l = lows[-lookback:]
        swing_high = max(window_h)
        swing_low  = min(window_l)
        diff = swing_high - swing_low

        if diff <= 0:
            return {}

        return {
            "swing_high": swing_high,
            "swing_low":  swing_low,
            "fib_0":      swing_high,
            "fib_236":    swing_high - 0.236 * diff,
            "fib_382":    swing_high - 0.382 * diff,
            "fib_500":    swing_high - 0.500 * diff,
            "fib_618":    swing_high - 0.618 * diff,
            "fib_786":    swing_high - 0.786 * diff,
            "fib_1":      swing_low,
            "golden_zone": (swing_high - 0.786 * diff, swing_high - 0.618 * diff),
        }

    def _score_fibonacci(
        self,
        current_close: float,
        current_low: float,
        current_high: float,
        fib: Dict[str, Any],
        side: str,
    ) -> Tuple[int, str]:
        """
        Pontua a qualidade da entrada em relação aos níveis de Fibonacci.
        Máximo: 30 pontos.
        """
        if not fib:
            return 0, ""

        gz_low, gz_high = fib.get("golden_zone", (0, 0))
        fib_382 = fib.get("fib_382", 0)
        fib_500 = fib.get("fib_500", 0)

        if side == "Buy":
            # Preço tocou o Golden Zone (retração para suporte Fibonacci)
            if gz_low <= current_low <= gz_high:
                return 30, f"Fibonacci Golden Zone (0.618-0.786) @ {current_low:.4f}"
            elif fib_500 and abs(current_close - fib_500) / fib_500 < 0.005:
                return 20, f"Fibonacci 0.5 @ {fib_500:.4f}"
            elif fib_382 and abs(current_close - fib_382) / fib_382 < 0.005:
                return 15, f"Fibonacci 0.382 @ {fib_382:.4f}"
        else:  # Sell
            # Para SHORT: preço rallied até zona de resistência Fibonacci
            if gz_low <= current_high <= gz_high:
                return 30, f"Fibonacci Resistência Golden Zone @ {current_high:.4f}"
            elif fib_382 and abs(current_close - fib_382) / fib_382 < 0.005:
                return 20, f"Fibonacci Resistência 0.382 @ {fib_382:.4f}"

        return 5, "Fibonacci próximo (sem zona exata)"

    def _score_cvd(self, cvd: float, side: str) -> Tuple[int, str]:
        """
        Pontua o CVD (Cumulative Volume Delta) com base no alinhamento com a entrada.
        Máximo: 25 pontos.
        """
        if side == "Buy":
            if cvd > 100_000:
                return 25, f"CVD Institucional FORTE LONG ({cvd:.0f})"
            elif cvd > 50_000:
                return 18, f"CVD Positivo LONG ({cvd:.0f})"
            elif cvd > 15_000:
                return 12, f"CVD Levemente Positivo ({cvd:.0f})"
            elif cvd < -50_000:
                return 0, ""  # CVD contra a posição — sinal fraco
            else:
                return 5, f"CVD Neutro ({cvd:.0f})"
        else:  # Sell
            if cvd < -100_000:
                return 25, f"CVD Institucional FORTE SHORT ({cvd:.0f})"
            elif cvd < -50_000:
                return 18, f"CVD Negativo SHORT ({cvd:.0f})"
            elif cvd < -15_000:
                return 12, f"CVD Levemente Negativo ({cvd:.0f})"
            elif cvd > 50_000:
                return 0, ""  # Contra a posição
            else:
                return 5, f"CVD Neutro ({cvd:.0f})"

    def _detect_price_action(
        self,
        candles: List,
        closes: List[float],
        highs: List[float],
        lows: List[float],
        side: str,
    ) -> Tuple[int, str]:
        """
        Detecta padrões de Price Action no M30 para confirmar a entrada:
          - Wick Reclaim: Candle anterior varreu liquidez, candle atual reclamou o nível
          - Engulf: Candle atual engole completamente o anterior (reversão)
          - Sweep & Reclaim: Spike abaixo/acima de suporte/resistência seguido de reclaim

        Máximo: 25 pontos.
        """
        if len(closes) < 3 or len(highs) < 3 or len(lows) < 3:
            return 0, ""

        cur_close  = closes[-1]
        cur_open   = float(candles[-1][1]) if candles else closes[-2]
        cur_high   = highs[-1]
        cur_low    = lows[-1]

        prev_close = closes[-2]
        prev_open  = float(candles[-2][1]) if len(candles) >= 2 else closes[-3]
        prev_high  = highs[-2]
        prev_low   = lows[-2]

        prev2_close = closes[-3]
        prev2_high  = highs[-3]
        prev2_low   = lows[-3]

        # ── Padrão 1: Engulfing Bullish/Bearish
        if side == "Buy":
            # Bullish Engulf: Candle atual fecha acima da abertura anterior
            if cur_close > prev_open and cur_open < prev_close and prev_close < prev_open:
                return 25, "Bullish Engulfing M30"
        else:
            # Bearish Engulf: Candle atual fecha abaixo da abertura anterior
            if cur_close < prev_open and cur_open > prev_close and prev_close > prev_open:
                return 25, "Bearish Engulfing M30"

        # ── Padrão 2: Wick Reclaim (Pavio extremo + reclaim no candle seguinte)
        if side == "Buy":
            prev_wick_pct = (prev_low - min(lows[-4:-2])) if len(lows) >= 4 else 0
            body_size = abs(prev_close - prev_open)
            wick_low_size = abs(prev_open - prev_low) if prev_open > prev_low else abs(prev_close - prev_low)

            if wick_low_size > body_size * 1.5 and cur_close > prev_close:
                return 22, "Wick Reclaim Bullish M30 (Pavio extremo + reclaim)"
        else:
            body_size = abs(prev_close - prev_open)
            wick_high_size = abs(prev_high - prev_open) if prev_open < prev_high else abs(prev_high - prev_close)

            if wick_high_size > body_size * 1.5 and cur_close < prev_close:
                return 22, "Wick Reclaim Bearish M30 (Pavio de alta + reclaim de baixa)"

        # ── Padrão 3: Sweep & Reclaim (Liquidity Grab)
        if side == "Buy":
            # Sweep: Prev varreu abaixo do mínimo anterior
            if prev_low < prev2_low and cur_close > prev2_low:
                return 20, f"Sweep & Reclaim Bullish M30 (Liquidity @ {prev_low:.4f})"
        else:
            # Sweep: Prev varreu acima do máximo anterior
            if prev_high > prev2_high and cur_close < prev2_high:
                return 20, f"Sweep & Reclaim Bearish M30 (Liquidity @ {prev_high:.4f})"

        # ── Padrão 4: Doji / Pin Bar / Hammer de reversão (padrão simples)
        body = abs(cur_close - cur_open)
        total_range = cur_high - cur_low
        if total_range > 0 and body / total_range < 0.3:
            # Pequeno corpo com pavio longo = Pin Bar
            if side == "Buy" and cur_low < lows[-3]:
                return 15, "Pin Bar Bullish M30 (reversão de suporte)"
            elif side == "Sell" and cur_high > highs[-3]:
                return 15, "Pin Bar Bearish M30 (rejeição de resistência)"

        return 0, ""

    # =========================================================================
    # ████  SCANNING LOOP  ████
    # =========================================================================

    async def scan_watchlist(
        self,
        symbols: List[str],
        btc_direction: str = "LATERAL",
        btc_adx: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Varre a lista de ativos em busca de setups BLITZ no M30.
        Retorna uma lista de sinais ordenados por score (maior primeiro).
        """
        found_signals = []

        tasks = [
            self.scan_for_blitz_signal(sym, btc_direction, btc_adx)
            for sym in symbols
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for sym, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.error(f"❌ [BLITZ-SCAN] Erro em {sym}: {result}")
                continue
            if result:
                found_signals.append(result)

        found_signals.sort(key=lambda s: s.get("score", 0), reverse=True)

        if found_signals:
            logger.info(
                f"⚡ [BLITZ-SCAN] {len(found_signals)} setup(s) M30 encontrado(s): "
                + ", ".join(f"{s['symbol']} {s['side']} ({s['score']})" for s in found_signals[:3])
            )
        else:
            logger.debug("⚡ [BLITZ-SCAN] Nenhum setup M30 qualificado encontrado.")

        return found_signals

    async def scan_and_inject(self, signal_queue: asyncio.PriorityQueue):
        """
        [V110.136 BLITZ] Varre ativos de elite e injeta sinais qualificados na queue continuamente.
        """
        logger.info("⚡ [BLITZ-SCAN] Injetor Blitz M30 iniciado.")
        while True:
            try:
                from services.okx_rest import okx_rest_service
                from services.agents.oracle_agent import oracle_agent

                # 1. Obtém lista de ativos oficial da watchlist de 20 pares
                from config import settings
                symbols = getattr(settings, "RADAR_WATCHLIST", [])
                if not symbols:
                    logger.warning("⚡ [BLITZ-SCAN] RADAR_WATCHLIST nao encontrada no config. settings.")
                    await asyncio.sleep(60)
                    continue
                
                # 2. Obtém contexto do BTC para filtragem
                ctx = oracle_agent.get_validated_context()
                btc_dir = ctx.get("btc_direction", "LATERAL")
                btc_adx = ctx.get("btc_adx", 0.0)

                # 3. Varre a watchlist
                signals = await self.scan_watchlist(symbols, btc_dir, btc_adx)

                # 4. Injeta na Queue com prioridade máxima
                for sig in signals:
                    # Score de 100 vira -100 (mais prioritário)
                    priority = -sig.get("score", 70)
                    await signal_queue.put((priority, time.time(), sig))
                    logger.info(f"⚡ [BLITZ-INJECT] {sig['symbol']} {sig['side']} injetado na queue (Score: {sig['score']})")
                
                # Aguarda 60 segundos antes da próxima varredura global
                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"❌ [BLITZ-INJECT-ERROR] Falha na injeção de sinais: {e}")
                await asyncio.sleep(30)


# Instância global do agente
blitz_sniper_agent = BlitzSniperAgent()
