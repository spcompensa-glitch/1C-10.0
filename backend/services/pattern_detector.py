# -*- coding: utf-8 -*-
"""
[V136-SWING] PatternDetector — Detecção Unificada de Padrões Gráficos
Detecta triângulos, topo/fundo duplo e Head & Shoulders em dados OHLC.

Uso: Swing Lab (2H) — padrões de médio prazo para confirmação de sinais.
"""

import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("PatternDetector")


@dataclass
class PatternResult:
    """Resultado unificado da detecção de qualquer padrão."""
    pattern_type: str      # "TRIANGLE", "DOUBLE_TOP", "DOUBLE_BOTTOM", "HEAD_SHOULDERS", "INVERSE_HS"
    direction: str         # "BULLISH", "BEARISH", "NEUTRAL"
    confidence: float      # 0.0 a 1.0
    boost_score: int       # Bonus para o score do sinal (+10 a +25)
    details: Dict = field(default_factory=dict)  # Detalhes específicos do padrão


class PatternDetector:
    """
    Detector unificado de padrões gráficos.
    Combina triângulos, duplos e H&S em uma única interface.
    """

    def __init__(self):
        from services.patterns.triangle_detector import TriangleDetector
        from services.patterns.double_detector import DoublePatternDetector
        from services.patterns.hs_detector import HeadShouldersDetector

        self._triangle = TriangleDetector()
        self._double = DoublePatternDetector()
        self._hs = HeadShouldersDetector()

    def detect(self, highs: List[float], lows: List[float], closes: List[float],
               timeframe: str = "2H") -> List[PatternResult]:
        """
        Detecta todos os padrões nos dados fornecidos.
        
        Args:
            highs: Lista de máximas
            lows: Lista de mínimas
            closes: Lista de fechamentos
            timeframe: Timeframe dos dados ("2H", "1H", etc.)
        
        Returns:
            Lista de padrões detectados (ordenados por confiança)
        """
        if not highs or not lows or not closes:
            return []
        
        if len(highs) < 10 or len(lows) < 10 or len(closes) < 10:
            return []

        all_patterns = []

        # Detecta triângulos (janela 20 velas)
        triangles = self._triangle.detect(highs, lows, closes, window=20)
        for t in triangles:
            all_patterns.append(PatternResult(
                pattern_type=f"TRIANGLE_{t.type}",
                direction=t.direction,
                confidence=t.confidence,
                boost_score=t.boost_score,
                details={
                    "upper_trendline": t.upper_trendline,
                    "lower_trendline": t.lower_trendline,
                    "convergence_point": t.convergence_point,
                }
            ))

        # Detecta duplos (janela 30 velas)
        doubles = self._double.detect(highs, lows, closes, window=30)
        for d in doubles:
            all_patterns.append(PatternResult(
                pattern_type=d.type,
                direction=d.direction,
                confidence=d.confidence,
                boost_score=d.boost_score,
                details={
                    "neckline": d.neckline,
                    "target": d.target,
                }
            ))

        # Detecta H&S (janela 40 velas)
        hs_patterns = self._hs.detect(highs, lows, closes, window=40)
        for h in hs_patterns:
            all_patterns.append(PatternResult(
                pattern_type=h.type,
                direction=h.direction,
                confidence=h.confidence,
                boost_score=h.boost_score,
                details={
                    "neckline": h.neckline,
                    "head_price": h.head_price,
                    "left_shoulder": h.left_shoulder,
                    "right_shoulder": h.right_shoulder,
                    "target": h.target,
                }
            ))

        # Ordena por confiança (maior primeiro)
        all_patterns.sort(key=lambda p: p.confidence, reverse=True)

        if all_patterns:
            logger.info(
                f"[PATTERN-DETECTOR] {len(all_patterns)} padrão(ões) detectado(s): "
                + ", ".join(f"{p.pattern_type} ({p.direction}, {p.confidence:.0%})" for p in all_patterns)
            )

        return all_patterns

    def detect_from_klines(self, klines: List, timeframe: str = "2H") -> List[PatternResult]:
        """
        Detecta padrões a partir de klines no formato OKX.
        klines: [[ts, open, high, low, close, vol], ...]
        """
        if not klines or len(klines) < 10:
            return []

        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        closes = [float(k[4]) for k in klines]

        return self.detect(highs, lows, closes, timeframe)

    def get_pattern_boost(self, patterns: List[PatternResult], side: str) -> int:
        """
        Calcula o boost total baseado nos padrões detectados e a direção do trade.
        
        Args:
            patterns: Lista de padrões detectados
            side: "LONG" ou "SHORT"
        
        Returns:
            Boost total (0 a +25)
        """
        if not patterns:
            return 0

        total_boost = 0
        for p in patterns:
            # Só conta padrões alinhados com a direção do trade
            if side == "LONG" and p.direction == "BULLISH":
                total_boost += p.boost_score
            elif side == "SHORT" and p.direction == "BEARISH":
                total_boost += p.boost_score
            elif p.direction == "NEUTRAL":
                # Padrões neutros dão boost menor
                total_boost += max(5, p.boost_score // 2)

        # Limita o boost máximo a 25 pontos
        return min(25, total_boost)
