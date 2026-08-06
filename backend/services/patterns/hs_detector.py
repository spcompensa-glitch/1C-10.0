# -*- coding: utf-8 -*-
"""
[V136-SWING] Head & Shoulders Pattern Detector
Detecta Head & Shoulders e Inverse Head & Shoulders em dados OHLC.

Metodologia:
- H&S: três picos — o central ≥ 5% maior que os laterais + neckline rompido
- Inverse H&S: três vales — o central ≥ 5% menor que os laterais + neckline rompido
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class HeadShouldersPattern:
    """Resultado da detecção de um padrão H&S."""
    type: str           # "HEAD_SHOULDERS" ou "INVERSE_HEAD_SHOULDERS"
    direction: str      # "BEARISH" (H&S) ou "BULLISH" (Inverse H&S)
    confidence: float   # 0.0 a 1.0
    neckline: float     # Preço do neckline
    head_price: float   # Preço da cabeça
    left_shoulder: float  # Preço do ombro esquerdo
    right_shoulder: float  # Preço do ombro direito
    target: float       # Preço alvo projetado
    boost_score: int    # Bonus para o score do sinal (+15 a +25)


class HeadShouldersDetector:
    """
    Detecta padrões Head & Shoulders em dados de preço.
    Usado para Swing Lab (2H).
    """

    def detect(self, highs: List[float], lows: List[float], closes: List[float],
               window: int = 40) -> List[HeadShouldersPattern]:
        """
        Detecta H&S nos últimos N períodos.
        """
        if len(highs) < window or len(lows) < window:
            return []

        recent_highs = highs[-window:]
        recent_lows = lows[-window:]
        recent_closes = closes[-window:]

        patterns = []

        # Detecta H&S (topo)
        hs = self._detect_head_shoulders(recent_highs, recent_lows, recent_closes)
        if hs:
            patterns.append(hs)

        # Detecta Inverse H&S (fundo)
        ihs = self._detect_inverse_head_shoulders(recent_highs, recent_lows, recent_closes)
        if ihs:
            patterns.append(ihs)

        return patterns

    def _detect_head_shoulders(self, highs: List[float], lows: List[float],
                                closes: List[float]) -> Optional[HeadShouldersPattern]:
        """
        Detecta Head & Shoulders (padrão de reversão de alta para baixa).
        Condições:
        1. Três máximos locais (ombro-esquerdo, cabeça, ombro-direito)
        2. Cabeça ≥ 5% maior que os ombros
        3. Ombros within 3% um do outro
        4. Neckline definido (mínimo entre ombro-esquerdo e cabeça)
        """
        pivot_highs = self._find_pivot_highs(highs, window=3)
        
        if len(pivot_highs) < 3:
            return None

        # Verifica sequências de 3 pivôs
        for i in range(len(pivot_highs) - 2):
            idx_ls, ls = pivot_highs[i]      # Left shoulder
            idx_head, head = pivot_highs[i+1]  # Head
            idx_rs, rs = pivot_highs[i+2]    # Right shoulder

            # Cabeça deve ser maior que os ombros
            if head <= ls or head <= rs:
                continue

            # Cabeça deve ser pelo menos 5% maior que os ombros
            avg_shoulder = (ls + rs) / 2
            head_premium = (head - avg_shoulder) / avg_shoulder
            if head_premium < 0.05:
                continue

            # Ombros devem ser similares (diferença < 10%)
            shoulder_diff = abs(ls - rs) / max(ls, rs)
            if shoulder_diff > 0.10:
                continue

            # Neckline: mínimo entre ombro-esquerdo e cabeça
            neckline_idx = min(idx_ls, idx_head)
            neckline = min(lows[neckline_idx:idx_rs+1])

            # Confiança baseada na simetria e proporção
            confidence = min(0.9, 0.5 + head_premium * 2 + (0.10 - shoulder_diff) * 2)

            # Alvo: neckline - altura do padrão
            pattern_height = head - neckline
            target = neckline - pattern_height

            return HeadShouldersPattern(
                type="HEAD_SHOULDERS",
                direction="BEARISH",
                confidence=confidence,
                neckline=neckline,
                head_price=head,
                left_shoulder=ls,
                right_shoulder=rs,
                target=target,
                boost_score=20
            )

        return None

    def _detect_inverse_head_shoulders(self, highs: List[float], lows: List[float],
                                        closes: List[float]) -> Optional[HeadShouldersPattern]:
        """
        Detecta Inverse Head & Shoulders (padrão de reversão de baixa para alta).
        """
        pivot_lows = self._find_pivot_lows(lows, window=3)
        
        if len(pivot_lows) < 3:
            return None

        for i in range(len(pivot_lows) - 2):
            idx_ls, ls = pivot_lows[i]
            idx_head, head = pivot_lows[i+1]
            idx_rs, rs = pivot_lows[i+2]

            # Cabeça deve ser menor que os ombros
            if head >= ls or head >= rs:
                continue

            # Cabeça deve ser pelo menos 5% menor que os ombros
            avg_shoulder = (ls + rs) / 2
            head_discount = (avg_shoulder - head) / avg_shoulder
            if head_discount < 0.05:
                continue

            # Ombros devem ser similares
            shoulder_diff = abs(ls - rs) / min(ls, rs)
            if shoulder_diff > 0.10:
                continue

            # Neckline: máximo entre ombro-esquerdo e cabeça
            neckline_idx = min(idx_ls, idx_head)
            neckline = max(highs[neckline_idx:idx_rs+1])

            confidence = min(0.9, 0.5 + head_discount * 2 + (0.10 - shoulder_diff) * 2)

            pattern_height = neckline - head
            target = neckline + pattern_height

            return HeadShouldersPattern(
                type="INVERSE_HEAD_SHOULDERS",
                direction="BULLISH",
                confidence=confidence,
                neckline=neckline,
                head_price=head,
                left_shoulder=ls,
                right_shoulder=rs,
                target=target,
                boost_score=20
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
