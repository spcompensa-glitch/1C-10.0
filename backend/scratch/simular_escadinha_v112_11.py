# -*- coding: utf-8 -*-
"""
SIMULACAO RAPIDA: Comparacao Escadinha V112.10 vs V112.11
"""
import random
import statistics
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class StopLevel:
    name: str
    trigger_roi: float
    stop_roi: float


ESCADA_V112_10: List[StopLevel] = [
    StopLevel("MICRO_LOCK", 20.0, 5.0),
    StopLevel("RISCO_ZERO", 50.0, 25.0),
    StopLevel("PROFIT_BRIDGE", 65.0, 40.0),
    StopLevel("LUCRO_80", 80.0, 50.0),
    StopLevel("LUCRO_100", 100.0, 75.0),
    StopLevel("SUCESSO", 130.0, 110.0),
]

ESCADA_V112_11: List[StopLevel] = [
    StopLevel("BREAKEVEN", 10.0, 0.0),
    StopLevel("LUCRO_INICIAL", 30.0, 15.0),
    StopLevel("LUCRO_MEDIO", 45.0, 30.0),
    StopLevel("LUCRO_80", 80.0, 50.0),
    StopLevel("LUCRO_100", 100.0, 75.0),
    StopLevel("SUCESSO", 130.0, 110.0),
]

LEVERAGE = 50.0


def roi_from_price(entry, current, side):
    if side == "buy":
        return (current - entry) / entry * LEVERAGE * 100
    return (entry - current) / entry * LEVERAGE * 100


def price_from_roi(entry, roi, side):
    offset = roi / (LEVERAGE * 100)
    return entry * (1 + offset) if side == "buy" else entry * (1 - offset)


def simular_trade(drift, vol, escada, stop_inicial, max_candles=100):
    entry = 100.0
    side = "buy"
    price = entry
    stop_roi = stop_inicial
    stop_p = price_from_roi(entry, stop_roi, side)
    max_roi = 0.0
    degraus = 0

    for _ in range(max_candles):
        var = drift + random.gauss(0, vol)
        price *= (1 + var / 100)

        roi = roi_from_price(entry, price, side)
        max_roi = max(max_roi, roi)

        if price <= stop_p:
            return roi, max_roi, "SL", degraus

        for n in escada:
            if roi >= n.trigger_roi and n.stop_roi > stop_roi:
                stop_roi = n.stop_roi
                stop_p = price_from_roi(entry, stop_roi, side)
                degraus += 1

    return roi, max_roi, "FIM", degraus


def simular(n_trades, escada, stop_inicial, label):
    random.seed(42)
    resultados = []
    perfis = [(0.08, 0.55, 30), (0.15, 0.65, 45), (0.28, 0.80, 25)]

    for _ in range(n_trades):
        r = random.random()
        cum = 0
        for d, v, p in perfis:
            cum += p / 100
            if r <= cum:
                drift, vol = d, v
                break
        res = simular_trade(drift, vol, escada, stop_inicial)
        resultados.append(res)

    rois = [r[0] for r in resultados]
    maxs = [r[1] for r in resultados]
    wins = [r for r in rois if r > 0]
    losses = [r for r in rois if r <= 0]
    alcancou_30 = sum(1 for m in maxs if m >= 30)
    fechados_cedo = sum(1 for i, m in enumerate(maxs) if m >= 50 and rois[i] < 30)
    manteve_100 = sum(1 for m in maxs if m >= 100)
    roi_acu = sum(rois)

    return {
        "label": label,
        "total": n_trades,
        "win_rate": len(wins) / n_trades * 100,
        "roi_medio": statistics.mean(rois),
        "roi_win": statistics.mean(wins) if wins else 0,
        "roi_loss": statistics.mean(losses) if losses else 0,
        "max_roi_medio": statistics.mean(maxs),
        "alcancou_30plus": alcancou_30,
        "fechados_cedo": fechados_cedo,
        "manteve_100plus": manteve_100,
        "roi_acumulado": roi_acu,
    }


def rodar():
    print("=" * 90)
    print("  SIMULACAO: Escadinha V112.10 (ANTIGA) vs V112.11 (NOVA)")
    print("  Mercado: TENDENCIA (ADX >= 25) | Alavancagem: 50x")
    print("=" * 90)

    for n in [500]:
        print(f"\n--- {n} TRADES POR ESCADA ---\n")

        random.seed(42)
        r1 = simular(n, ESCADA_V112_10, -25.0, "V112.10 ANTIGA")
        random.seed(42)
        r2 = simular(n, ESCADA_V112_11, -40.0, "V112.11 NOVA")

        for r in [r1, r2]:
            print(f"[{r['label']}]")
            print(f"  Win Rate:          {r['win_rate']:>7.2f}%")
            print(f"  ROI Medio:         {r['roi_medio']:>+9.2f}%")
            print(f"  ROI Medio (Win):   {r['roi_win']:>+9.2f}%")
            print(f"  ROI Medio (Loss):  {r['roi_loss']:>+9.2f}%")
            print(f"  Max ROI Medio:     {r['max_roi_medio']:>+9.2f}%")
            print(f"  Atingiram 30%+:    {r['alcancou_30plus']:>4d}")
            print(f"  Fechados Cedo:     {r['fechados_cedo']:>4d} (tiveram 50%+ mas fecharam <30%)")
            print(f"  Mantiveram 100%+:  {r['manteve_100plus']:>4d}")
            print(f"  ROI Acumulado:     {r['roi_acumulado']:>+10.2f}%")
            print()

        print("  DIFERENCA (V112.11 - V112.10):")
        print(f"    Win Rate:          {r2['win_rate'] - r1['win_rate']:>+8.2f} pp")
        print(f"    ROI Medio:         {r2['roi_medio'] - r1['roi_medio']:>+8.2f} pp")
        print(f"    ROI Acumulado:     {r2['roi_acumulado'] - r1['roi_acumulado']:>+10.2f}%")
        print(f"    Cedo reducao:      {r1['fechados_cedo'] - r2['fechados_cedo']:>+4d} trades (menos prematuros)")
        print(f"    100%+ aumento:     {r2['manteve_100plus'] - r1['manteve_100plus']:>+4d} trades (mais campeoes)")
        print()


if __name__ == "__main__":
    rodar()
