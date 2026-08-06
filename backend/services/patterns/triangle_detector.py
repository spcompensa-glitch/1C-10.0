# -*- coding: utf-8 -*-
"""
[V136-SWING] Triangle Pattern Detector
Detecta triângulos (simétrico, ascendente, descendente) em dados OHLC.

Metodologia:
- Triângulo Simétrico: lows sobem + highs descem (convergência)
- Triângulo Ascendente: lows sobem + highs constantes (support forte)
- Triângulo Descendente: lows constantes + highs descem (resistance forte)
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class TrianglePattern:
    """Resultado da detecção de um triângulo."""
    type: str           # "SYMMETRIC", "ASCENDING", "DESCENDING"
    direction: str      # "BULLISH" ou "BEARISH"
    confidence: float   # 0.0 a 1.0
    upper_trendline: float  # Preço da linha de tendência superior
    lower_trendline: float  # Preço da linha de tendência inferior
    convergence_point: float  # Ponto estimado de convergência
    boost_score: int    # Bonus para o score do sinal (+10 a +20)


class TriangleDetector:
    """
    Detecta padrões de triângulo em dados de preço.
    Usado para Swing Lab (2H) — padrões de médio prazo.
    """

    def detect(self, highs: List[float], lows: List[float], closes: List[float],
               window: int = 20) -> List[TrianglePattern]:
        """
        Detecta triângulos nos últimos N períodos.
        
        Args:
            highs: Lista de máximas
            lows: Lista de mínimas
            closes: Lista de fechamentos
            window: Janela de análise (padrão 20 velas = ~40 horas em 2H)
        
        Returns:
            Lista de triângulos detectados
        """
        if len(highs) < window or len(lows) < window:
            return []

        # Últimos N períodos
        recent_highs = highs[-window:]
        recent_lows = lows[-window:]
        recent_closes = closes[-window:]

        patterns = []

        # Detecta pivôs
        pivot_highs = self._find_pivots(recent_highs, is_high=True)
        pivot_lows = self._find_pivots(recent_lows, is_high=False)

        if len(pivot_highs) < 2 or len(pivot_lows) < 2:
            return []

        # Analisa convergência
        pattern = self._analyze_convergence(
            pivot_highs, pivot_lows, recent_highs, recent_lows
        )
        if pattern:
            patterns.append(pattern)

        return patterns

    def _find_pivots(self, data: List[float], is_high: bool = True,
                     window: int = 3) -> List[Tuple[int, float]]:
        """
        Encontra pivôs (máximas ou mínimas locais).
        
        Returns:
            Lista de (índice, valor) dos pivôs
        """
        pivots = []
        for i in range(window, len(data) - window):
            if is_high:
                if all(data[i] >= data[i-j] for j in range(1, window+1)) and \
                   all(data[i] >= data[i+j] for j in range(1, window+1)):
                    pivots.append((i, data[i]))
            else:
                if all(data[i] <= data[i-j] for j in range(1, window+1)) and \
                   all(data[i] <= data[i+j] for j in range(1, window+1)):
                    pivots.append((i, data[i]))
        return pivots

    def _analyze_convergence(self, pivot_highs: List[Tuple[int, float]],
                             pivot_lows: List[Tuple[int, float]],
                             all_highs: List[float],
                             all_lows: List[float]) -> Optional[TrianglePattern]:
        """
        Analisa se os pivôs formam um triângulo.
        """
        if len(pivot_highs) < 2 or len(pivot_lows) < 2:
            return None

        # Calcula inclinação das linhas de tendência
        high_slope = self._calculate_slope(pivot_highs)
        low_slope = self._calculate_slope(pivot_lows)

        # Classifica o padrão
        if high_slope < -0.001 and low_slope > 0.001:
            # Triângulo Simétrico: highs descem, lows sobem
            return self._create_symmetric_triangle(
                pivot_highs, pivot_lows, high_slope, low_slope, all_highs, all_lows
            )
        elif high_slope < -0.001 and abs(low_slope) < 0.001:
            # Triângulo Descendente: highs descem, lows constantes
            return self._create_descending_triangle(
                pivot_highs, pivot_lows, high_slope, all_highs, all_lows
            )
        elif abs(high_slope) < 0.001 and low_slope > 0.001:
            # Triângulo Ascendente: highs constantes, lows sobem
            return self._create_ascending_triangle(
                pivot_highs, pivot_lows, low_slope, all_highs, all_lows
            )

        return None

    def _calculate_slope(self, pivots: List[Tuple[int, float]]) -> float:
        """Calcula a inclinação média entre pivôs."""
        if len(pivots) < 2:
            return 0.0
        
        slopes = []
        for i in range(1, len(pivots)):
            dx = pivots[i][0] - pivots[i-1][0]
            dy = pivots[i][1] - pivots[i-1][1]
            if dx > 0:
                slopes.append(dy / dx)
        
        return sum(slopes) / len(slopes) if slopes else 0.0

    def _create_symmetric_triangle(self, pivot_highs, pivot_lows,
                                    high_slope, low_slope,
                                    all_highs, all_lows) -> TrianglePattern:
        """Cria triângulo simétrico."""
        # Confiança baseada na simetria e convergência
        slope_diff = abs(high_slope + low_slope)  # Quanto mais simétrico, menor a diff
        confidence = min(0.9, 0.5 + slope_diff * 100)
        
        # Direção depende do rompimento futuro (estimado)
        # Por padrão, simétrico é neutro — direção será determinada pelo breakout
        last_high = all_highs[-1]
        last_low = all_lows[-1]
        mid_price = (last_high + last_low) / 2
        
        return TrianglePattern(
            type="SYMMETRIC",
            direction="NEUTRAL",  # Simétrico — aguarda breakout
            confidence=confidence,
            upper_trendline=last_high,
            lower_trendline=last_low,
            convergence_point=mid_price,
            boost_score=10  # Boost neutro
        )

    def _create_ascending_triangle(self, pivot_highs, pivot_lows,
                                    low_slope, all_highs, all_lows) -> TrianglePattern:
        """Cria triângulo ascendente (bullish)."""
        confidence = min(0.85, 0.6 + low_slope * 50)
        
        resistance = max(p[1] for p in pivot_highs)  # Resistência horizontal
        last_low = all_lows[-1]
        
        return TrianglePattern(
            type="ASCENDING",
            direction="BULLISH",
            confidence=confidence,
            upper_trendline=resistance,
            lower_trendline=last_low,
            convergence_point=resistance,
            boost_score=15  # Boost bullish
        )

    def _create_descending_triangle(self, pivot_highs, pivot_lows,
                                     high_slope, all_highs, all_lows) -> TrianglePattern:
        """Cria triângulo descendente (bearish)."""
        confidence = min(0.85, 0.6 + abs(high_slope) * 50)
        
        support = min(p[1] for p in pivot_lows)  # Suporte horizontal
        last_high = all_highs[-1]
        
        return TrianglePattern(
            type="DESCENDING",
            direction="BEARISH",
            confidence=confidence,
            upper_trendline=last_high,
            lower_trendline=support,
            convergence_point=support,
            boost_score=15  # Boost bearish
        )
