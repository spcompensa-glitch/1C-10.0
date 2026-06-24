"""
===============================================================
SIMULAÇÃO V112.12 — Escadinha Refinada + MACRO_BYPASS +
DECOR em TRENDING + Mean Reversion + CVD Exhaustion
===============================================================

Compara o comportamento do sistema ANTES (V112.11) vs DEPOIS (V112.12)
para verificar se as mudanças permitem operar AMBOS os lados (LONG + SHORT)
em vez de apenas SHORT.

Cenários testados:
  1. BTC em BEARISH + TRENDING → V112.11: só SHORT | V112.12: LONG se CVD exhausted
  2. BTC em BEARISH + TRENDING + DECOR descolado → V112.11: bloqueado | V112.12: permitido
  3. BTC em BULLISH + TRENDING + CVD exhaustion → V112.11: SHORT bloqueado | V112.12: SHORT permitido
  4. Cenário misto com 1000 simulações de Monte Carlo
"""

import random
import math
from typing import Dict, List, Tuple

# ===============================================================
# CONFIGURAÇÕES
# ===============================================================
SEED = 42
NUM_SIMULACOES = 2000
LEVERAGE = 50

random.seed(SEED)

# ===============================================================
# SIMULAÇÃO DAS ESTRATÉGIAS
# ===============================================================

def simular_macro_trend(btc_price: float, ema50: float, sma200: float) -> str:
    """Simula o filtro macro diário."""
    above_200sma = btc_price > sma200
    pct_from_ema50 = ((btc_price - ema50) / ema50) * 100
    
    if pct_from_ema50 > 1.0 and above_200sma:
        return "BULLISH"
    elif pct_from_ema50 < -1.0 and not above_200sma:
        return "BEARISH"
    elif pct_from_ema50 > 0.3:
        return "BULLISH"
    elif pct_from_ema50 < -0.3:
        return "BEARISH"
    else:
        return "NEUTRAL"

def simular_regime(adx: float) -> str:
    """Simula detecção de regime."""
    if adx >= 25:
        return "TRENDING"
    else:
        return "LATERAL"

def simular_cvd() -> Tuple[float, float, float]:
    """
    Simula CVD total, 5m e 15m.
    Retorna (cvd_total, cvd_5m, cvd_15m)
    """
    cvd_total = random.gauss(0, 150000)
    cvd_5m = random.gauss(0, 50000)
    cvd_15m = random.gauss(0, 80000)
    return cvd_total, cvd_5m, cvd_15m

def simular_cvd_exhaustion(cvd_total: float, cvd_5m: float, cvd_15m: float, side: str) -> bool:
    """Simula o detect_cvd_exhaustion do V112.12."""
    if side.lower() in ("buy", "long"):
        # Compradores exaustos
        return (cvd_total > 100000 and cvd_5m < 30000) or (cvd_5m < -10000 and cvd_15m < 0)
    else:
        # Vendedores exaustos
        return (cvd_total < -100000 and cvd_5m > -30000) or (cvd_5m > 10000 and cvd_15m > 0)

def simular_zones() -> Tuple[bool, bool]:
    """
    Simula zonas de suporte/resistência.
    Retorna (near_support, near_resistance)
    """
    return random.random() < 0.3, random.random() < 0.3

def simular_decorrelation() -> Tuple[bool, float]:
    """
    Simula detecção de descorrelação.
    Retorna (is_decorrelated, correlation)
    """
    corr = random.gauss(0.5, 0.3)
    corr = max(-1, min(1, corr))
    is_decor = corr < 0.45
    return is_decor, corr

def simular_score() -> float:
    """Simula score do sinal."""
    return random.randint(50, 100)

def v112_11_gate(
    macro_trend: str,
    side: str,
    strategy: str,
    regime: str,
) -> Tuple[bool, str]:
    """
    Comportamento V112.11 (ANTES):
    - DECOR SHADOW bloqueado em TRENDING
    - LONG bloqueado se macro BEARISH + TRENDING
    - SHORT bloqueado se macro BULLISH + TRENDING
    """
    # Regime gate
    if regime == "LATERAL":
        if strategy in ("VELOCITY FLOW", "ALPHA SHIELD"):
            return False, "REGIME_BLOCK_LATERAL"
    else:
        if strategy == "DECOR SHADOW":
            return False, "DECOR_BLOCKED_TRENDING"
    
    # Macro filter
    if strategy != "DECOR SHADOW" and regime != "LATERAL":
        if macro_trend == "BEARISH" and side.lower() in ("buy", "long"):
            return False, "MACRO_BLOCK_LONG_BEARISH"
        elif macro_trend == "BULLISH" and side.lower() in ("sell", "short"):
            return False, "MACRO_BLOCK_SHORT_BULLISH"
    
    return True, "APPROVED"

def v112_12_gate(
    macro_trend: str,
    side: str,
    strategy: str,
    regime: str,
    score: float,
    cvd_total: float,
    cvd_5m: float,
    cvd_15m: float,
    corr: float,
    is_decor: bool,
) -> Tuple[bool, str]:
    """
    Comportamento V112.12 (DEPOIS):
    - DECOR SHADOW permitido em TRENDING se descolado (corr < 0.45)
    - MACRO_BYPASS: LONG em BEARISH permitido se score >= 75 + CVD exhaustion ou suporte
    - SHORT em BULLISH permitido se score >= 75 + CVD exhaustion ou resistência
    """
    # Regime gate com bypass DECOR em TRENDING
    if regime == "LATERAL":
        if strategy in ("VELOCITY FLOW", "ALPHA SHIELD"):
            return False, "REGIME_BLOCK_LATERAL"
    else:
        if strategy == "DECOR SHADOW":
            if is_decor:
                return True, "DECOR_APPROVED_TRENDING"
            else:
                return False, "DECOR_BLOCKED_TRENDING"
    
    # Macro filter com bypass
    if strategy != "DECOR SHADOW" and regime != "LATERAL":
        if macro_trend == "BEARISH" and side.lower() in ("buy", "long"):
            if score >= 75:
                cvd_exhausted = simular_cvd_exhaustion(cvd_total, cvd_5m, cvd_15m, "sell")
                _, near_support = simular_zones()
                _, near_support = simular_zones()
                if cvd_exhausted or near_support:
                    return True, "MACRO_BYPASS_LONG"
            return False, "MACRO_BLOCK_LONG_BEARISH"
        elif macro_trend == "BULLISH" and side.lower() in ("sell", "short"):
            if score >= 75:
                cvd_exhausted = simular_cvd_exhaustion(cvd_total, cvd_5m, cvd_15m, "buy")
                near_resistance, _ = simular_zones()
                if cvd_exhausted or near_resistance:
                    return True, "MACRO_BYPASS_SHORT"
            return False, "MACRO_BLOCK_SHORT_BULLISH"
    
    return True, "APPROVED"

# ===============================================================
# CENÁRIOS DE TESTE
# ===============================================================

cenarios = [
    {"nome": "BTC BEARISH + TRENDING + VELOCITY FLOW LONG", "btc_price": 55000, "ema50": 65000, "sma200": 60000, "adx": 30, "side": "buy", "strategy": "VELOCITY FLOW"},
    {"nome": "BTC BEARISH + TRENDING + VELOCITY FLOW SHORT", "btc_price": 55000, "ema50": 65000, "sma200": 60000, "adx": 30, "side": "sell", "strategy": "VELOCITY FLOW"},
    {"nome": "BTC BULLISH + TRENDING + VELOCITY FLOW LONG", "btc_price": 65000, "ema50": 58000, "sma200": 55000, "adx": 30, "side": "buy", "strategy": "VELOCITY FLOW"},
    {"nome": "BTC BULLISH + TRENDING + ALPHA SHIELD SHORT", "btc_price": 65000, "ema50": 58000, "sma200": 55000, "adx": 30, "side": "sell", "strategy": "ALPHA SHIELD"},
    {"nome": "BTC BEARISH + LATERAL + DECOR SHADOW SHORT", "btc_price": 55000, "ema50": 65000, "sma200": 60000, "adx": 20, "side": "sell", "strategy": "DECOR SHADOW"},
    {"nome": "BTC BEARISH + LATERAL + DECOR SHADOW LONG", "btc_price": 55000, "ema50": 65000, "sma200": 60000, "adx": 20, "side": "buy", "strategy": "DECOR SHADOW"},
    {"nome": "BTC BEARISH + TRENDING + DECOR SHADOW LONG (descolado)", "btc_price": 55000, "ema50": 65000, "sma200": 60000, "adx": 30, "side": "buy", "strategy": "DECOR SHADOW"},
]

def executar_simulacao():
    """Executa simulação completa."""
    
    print("=" * 80)
    print("SIMULAÇÃO V112.11 (ANTES) vs V112.12 (DEPOIS)")
    print("=" * 80)
    
    resultados_cenario = []
    
    for cenario in cenarios:
        nome = cenario["nome"]
        macro_trend = simular_macro_trend(cenario["btc_price"], cenario["ema50"], cenario["sma200"])
        regime = simular_regime(cenario["adx"])
        side = cenario["side"]
        strategy = cenario["strategy"]
        
        # Estatísticas acumuladas para Monte Carlo
        v112_11_approved = 0
        v112_12_approved = 0
        v112_12_bypass_count = 0
        v112_12_bypass_reasons = {}
        
        for _ in range(NUM_SIMULACOES):
            score = simular_score()
            cvd_total, cvd_5m, cvd_15m = simular_cvd()
            is_decor, corr = simular_decorrelation()
            
            # V112.11
            aprovado_11, motivo_11 = v112_11_gate(macro_trend, side, strategy, regime)
            if aprovado_11:
                v112_11_approved += 1
            
            # V112.12
            aprovado_12, motivo_12 = v112_12_gate(
                macro_trend, side, strategy, regime,
                score, cvd_total, cvd_5m, cvd_15m, corr, is_decor
            )
            if aprovado_12:
                v112_12_approved += 1
                if "BYPASS" in motivo_12 or "DECOR_APPROVED" in motivo_12:
                    v112_12_bypass_count += 1
                    v112_12_bypass_reasons[motivo_12] = v112_12_bypass_reasons.get(motivo_12, 0) + 1
        
        resultados_cenario.append({
            "nome": nome,
            "macro": macro_trend,
            "regime": regime,
            "v112_11_rate": v112_11_approved / NUM_SIMULACOES * 100,
            "v112_12_rate": v112_12_approved / NUM_SIMULACOES * 100,
            "v112_12_bypass": v112_12_bypass_count / NUM_SIMULACOES * 100,
            "bypass_reasons": v112_12_bypass_reasons,
        })
    
    print(f"\nResultados baseados em {NUM_SIMULACOES} simulações por cenário:\n")
    print(f"{'Cenário':<55} {'Regime':<12} {'V112.11':<10} {'V112.12':<10} {'Bypass':<10}")
    print("-" * 100)
    
    for r in resultados_cenario:
        print(f"{r['nome']:<55} {r['regime']:<12} {r['v112_11_rate']:>6.1f}%  {r['v112_12_rate']:>6.1f}%  {r['v112_12_bypass']:>6.1f}%")
        if r['bypass_reasons']:
            for motivo, qtd in sorted(r['bypass_reasons'].items(), key=lambda x: x[1], reverse=True):
                print(f"  -> {motivo}: {qtd/NUM_SIMULACOES*100:.1f}%")
    
    # ===============================================================
    # SIMULAÇÃO DE MONTE CARLO: COMPARAÇÃO GERAL
    # ===============================================================
    
    print("\n" + "=" * 80)
    print("SIMULAÇÃO MONTE CARLO GERAL (2000 trades)")
    print("=" * 80)
    
    # Cenário: BTC BEARISH + TRENDING, sinais aleatórios LONG/SHORT
    v112_11_longs = 0
    v112_11_shorts = 0
    v112_11_blocked = 0
    
    v112_12_longs = 0
    v112_12_shorts = 0
    v112_12_blocked = 0
    v112_12_bypass_total = 0
    
    for _ in range(NUM_SIMULACOES):
        side = random.choice(["buy", "sell"])
        strategy = random.choice(["VELOCITY FLOW", "ALPHA SHIELD", "DECOR SHADOW"])
        score = random.randint(60, 100)
        cvd_total, cvd_5m, cvd_15m = simular_cvd()
        is_decor, corr = simular_decorrelation()
        
        macro_trend = "BEARISH"
        regime = "TRENDING"
        
        # V112.11
        aprovado_11, motivo_11 = v112_11_gate(macro_trend, side, strategy, regime)
        if aprovado_11:
            if side.lower() in ("buy", "long"):
                v112_11_longs += 1
            else:
                v112_11_shorts += 1
        else:
            v112_11_blocked += 1
        
        # V112.12
        aprovado_12, motivo_12 = v112_12_gate(
            macro_trend, side, strategy, regime,
            score, cvd_total, cvd_5m, cvd_15m, corr, is_decor
        )
        if aprovado_12:
            if side.lower() in ("buy", "long"):
                v112_12_longs += 1
            else:
                v112_12_shorts += 1
            if "BYPASS" in motivo_12 or "DECOR_APPROVED" in motivo_12:
                v112_12_bypass_total += 1
        else:
            v112_12_blocked += 1
    
    total_11 = v112_11_longs + v112_11_shorts
    total_12 = v112_12_longs + v112_12_shorts
    
    print(f"\n{'Métrica':<40} {'V112.11 (Antes)':<20} {'V112.12 (Depois)':<20}")
    print("-" * 80)
    print(f"{'Total aprovados':<40} {total_11:>10.0f} ({total_11/NUM_SIMULACOES*100:>5.1f}%)  {total_12:>10.0f} ({total_12/NUM_SIMULACOES*100:>5.1f}%)")
    print(f"{'  LONG':<40} {v112_11_longs:>10.0f} ({v112_11_longs/max(total_11,1)*100:>5.1f}%)  {v112_12_longs:>10.0f} ({v112_12_longs/max(total_12,1)*100:>5.1f}%)")
    print(f"{'  SHORT':<40} {v112_11_shorts:>10.0f} ({v112_11_shorts/max(total_11,1)*100:>5.1f}%)  {v112_12_shorts:>10.0f} ({v112_12_shorts/max(total_12,1)*100:>5.1f}%)")
    print(f"{'Bloqueados':<40} {v112_11_blocked:>10.0f} ({v112_11_blocked/NUM_SIMULACOES*100:>5.1f}%)  {v112_12_blocked:>10.0f} ({v112_12_blocked/NUM_SIMULACOES*100:>5.1f}%)")
    print(f"{'Bypass (MACRO_BYPASS+DECOR_TREND)':<40} {'N/A':>20} {v112_12_bypass_total:>10.0f} ({v112_12_bypass_total/NUM_SIMULACOES*100:>5.1f}%)")
    
    # Resumo
    print("\n" + "=" * 80)
    print("RESUMO DAS MUDANÇAS V112.12")
    print("=" * 80)
    
    mudancas = [
        ("DECOR SHADOW em TRENDING", 
         "DECOR SHADOW agora permitido em mercado em TENDÊNCIA quando o par",
         "estiver descolado do BTC (Pearson < 0.45, confidence >= 60)"),
        ("MACRO_BYPASS - LONG em BEARISH",
         "LONG permitido mesmo com MACRO BEARISH se score >= 75 E",
         "(CVD exhaustion de venda OU preço em zona de suporte)"),
        ("MACRO_BYPASS - SHORT em BULLISH",
         "SHORT permitido mesmo com MACRO BULLISH se score >= 75 E",
         "(CVD exhaustion de compra OU preço em zona de resistência)"),
        ("Mean Reversion Module",
         "Novo detector de reversão à média combinando:",
         "RSI + Zonas S/R + V-Recovery + CVD Exhaustion + Price Rejection"),
        ("CVD Exhaustion Detector",
         "Detecta exaustão do fluxo de ordens:",
         "CVD total divergente do CVD 5m/15m (compradores ou vendedores exaustos)"),
    ]
    
    for titulo, desc1, desc2 in mudancas:
        print(f"\n✅ {titulo}")
        print(f"   {desc1}")
        print(f"   {desc2}")
    
    print(f"\n📊 Resultado esperado: A V112.12 deve operar AMBOS os lados")
    print(f"   (LONG + SHORT) em vez de apenas SHORT, aumentando as")
    print(f"   oportunidades de lucro e a adaptabilidade do sistema.")

if __name__ == "__main__":
    executar_simulacao()
