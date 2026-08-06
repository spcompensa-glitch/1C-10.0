# -*- coding: utf-8 -*-
"""
[V136-SWING] Double Top/Bottom Pattern Detector
Detecta Topo Duplo e Fundo Duplo em dados OHLC.

Metodologia:
- Topo Duplo: dois máximos similares (diferença < 2%) + neckline rompido
- Fundo Duplo: dois mínimos similares (diferença < 2%) + neckline rompido
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class DoublePattern:
    """Resultado da detecção de um padrão duplo."""
    type: str           # "DOUBLE_TOP" ou "DOUBLE_BOTTOM"
    direction: str      # "BEARISH" (topo) ou "BULLISH" (fundo)
    confidence: float   # 0.0 a 1.0
    neckline: float     # Preço do neckline
    target: float       # Preço alvo projetado
    boost_score: int    # Bonus para o score do sinal (+10 a +20)


class DoublePatternDetector:
    """
    Detecta padrões de topo/fundo duplo em dados de preço.
    Usado para Swing Lab (2H).
    """

    def detect(self, highs: List[float], lows: List[float], closes: List[float],
               window: int = 30) -> List[DoublePattern]:
        """
        Detecta padrões duplos nos últimos N períodos.
        """
        if len(highs) < window or len(lows) < window:
            return []

        recent_highs = highs[-window:]
        recent_lows = lows[-window:]
        recent_closes = closes[-window:]

        patterns = []

        # Detecta Topo Duplo
        dt = self._detect_double_top(recent_highs, recent_lows, recent_closes)
        if dt:
            patterns.append(dt)

        # Detecta Fundo Duplo
        db = self._detect_double_bottom(recent_highs, recent_lows, recent_closes)
        if db:
            patterns.append(db)

        return patterns

    def _detect_double_top(self, highs: List[float], lows: List[float],
                           closes: List[float]) -> Optional[DoublePattern]:
        """
        Detecta Topo Duplo.
        Condições:
        1. Dois máximos locais com diferença < 2%
        2. Separados por pelo menos 5 períodos
        3. Neckline (mínimo entre os topos) definido
        """
        # Encontra máximas locais (pivôs)
        pivot_highs = self._find_pivot_highs(highs, window=3)
        
        if len(pivot_highs) < 2:
            return None

        # Verifica pares de pivôs
        for i in range(len(pivot_highs)):
            for j in range(i+1, len(pivot_highs)):
                idx1, val1 = pivot_highs[i]
                idx2, val2 = pivot_highs[j]
                
                # Deve haver pelo menos 5 períodos entre os topos
                if abs(idx2 - idx1) < 5:
                    continue
                
                # Verifica se os topos são similares (diferença < 2%)
                diff_pct = abs(val1 - val2) / max(val1, val2)
                if diff_pct > 0.02:
                    continue
                
                # Encontra o neckline (mínimo entre os topos)
                start = min(idx1, idx2)
                end = max(idx1, idx2)
                neckline = min(lows[start:end+1])
                
                # Calcula confiança
                confidence = min(0.9, 0.6 + (0.02 - diff_pct) * 10)
                
                # Alvo projetado: neckline - altura do padrão
                pattern_height = max(val1, val2) - neckline
                target = neckline - pattern_height
                
                return DoublePattern(
                    type="DOUBLE_TOP",
                    direction="BEARISH",
                    confidence=confidence,
                    neckline=neckline,
                    target=target,
                    boost_score=15
                )

        return None

    def _detect_double_bottom(self, highs: List[float], lows: List[float],
                               closes: List[float]) -> Optional[DoublePattern]:
        """
        Detecta Fundo Duplo.
        Condições:
        1. Dois mínimos locais com diferença < 2%
        2. Separados por pelo menos 5 períodos
        3. Neckline (máximo entre os fundos) definido
        """
        pivot_lows = self._find_pivot_lows(lows, window=3)
        
        if len(pivot_lows) < 2:
            return None

        for i in range(len(pivot_lows)):
            for j in range(i+1, len(pivot_lows)):
                idx1, val1 = pivot_lows[i]
                idx2, val2 = pivot_lows[j]
                
                if abs(idx2 - idx1) < 5:
                    continue
                
                diff_pct = abs(val1 - val2) / min(val1, val2)
                if diff_pct > 0.02:
                    continue
                
                start = min(idx1, idx2)
                end = max(idx1, idx2)
                neckline = max(highs[start:end+1])
                
                confidence = min(0.9, 0.6 + (0.02 - diff_pct) * 10)
                
                pattern_height = neckline - min(val1, val2)
                target = neckline + pattern_height
                
                return DoublePattern(
                    type="DOUBLE_BOTTOM",
                    direction="BULLISH",
                    confidence=confidence,
                    neckline=neckline,
                    target=target,
                    boost_score=15
                )

        return None

    def _find_pivot_highs(self, data: List[float], window: int = 3) -> List[Tuple[int, float]]:
        pivots = []
        for i in range(window, len(data) - window):
            if all(data[i] >= data[i-j] for j in range(1, window+1)) and \
               all(data[i] >= data[i+j] for j in range(1, window+1)):
                pivots.append((i, data[i]))
        return pivots

    def _find_pivot_lows(self, data: List[float], window: int = 3) -> List[Tuple[int, float]]:
        pivots = []
        for i in range(window, len(data) - window):
            if all(data[i] <= data[i-j] for j in range(1, window+1)) and \
               all(data[i] <= data[i+j] for j in range(1, window+1)):
                pivots.append((i, data[i]))
        return pivots
