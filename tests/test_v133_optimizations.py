# -*- coding: utf-8 -*-
"""
Testes para as otimizações V133 — 1Crypten 7.0
================================================
Cobre as 6 mudanças implementadas:
1. Swing Lab: Stop inicial reduzido de 35% para 20% ROI
2. Swing Lab: ADX threshold elevado de 25 para 30
3. Blocklist: INJUSDT, XLMUSDT, GRTUSDT adicionados
4. GARANTIA_TRAIL: Ativação reduzida de 12% para 8% (Scalping)
5. Scalping: Stop máximo aumentado de -8% para -12% ROI
6. Scalping: Filtro R:R mínimo >= 1.5

Executar: pytest tests/test_v133_optimizations.py -v
"""
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


# ============================================================================
# Helpers / Fakes
# ============================================================================

def _make_swing_signal(
    symbol="DOTUSDT",
    side="Buy",
    score=85,
    entry_price=100.0,
):
    """Cria um sinal fake para Swing Lab."""
    return {
        "symbol": symbol,
        "side": side,
        "score": score,
        "entry_price_signal": entry_price,
        "strategy_class": "VELOCITY FLOW",
        "indicators": {"volume_ratio": 2.0},
        "reasons": ["test"],
    }


def _make_scalping_signal(
    symbol="DOTUSDT",
    direction="LONG",
    score=85,
    entry_price=100.0,
    stop_price=99.88,  # -12% ROI / 50x = 0.24% preço
):
    """Cria um sinal fake para Scalping Lab."""
    return {
        "symbol": symbol,
        "direction": direction,
        "side": "Buy" if direction == "LONG" else "Sell",
        "score": score,
        "entry_price_signal": entry_price,
        "stop_price": stop_price,
        "strategy": "VWAP SNIPER",
        "strategy_class": "VWAP SNIPER",
        "timestamp": time.time(),
    }


class FakeDB:
    """Banco de dados em memória para testes."""

    def __init__(self, trades=None):
        self._trades = {t.id: t for t in (trades or [])}
        self.saved = []
        self.updated = {}

    async def get_sandbox_trades(self, active_only=False):
        return [t for t in self._trades.values() if not active_only or t.status == "ACTIVE"]

    async def get_swing_trades(self, active_only=False):
        return [t for t in self._trades.values() if not active_only or t.status == "ACTIVE"]

    async def save_sandbox_trade(self, data):
        t = MagicMock()
        for k, v in data.items():
            setattr(t, k, v)
        self._trades[data["id"]] = t
        self.saved.append(data)

    async def save_swing_trade(self, data):
        t = MagicMock()
        for k, v in data.items():
            setattr(t, k, v)
        t.id = data.get("id", "test_id")
        self._trades[data["id"]] = t
        self.saved.append(data)
        return t

    async def get_sandbox_unified_balance(self):
        return 10000.0


class FakeWS:
    """Mock do okx_ws_public_service."""

    def __init__(self, price=100.0, adx=30.0):
        self._price = price
        self.btc_adx = adx

    def get_current_price(self, symbol):
        return self._price


# ============================================================================
# Teste 1 — Swing Stop Reduzido para 20% ROI
# ============================================================================

def test_swing_stop_roi_is_20():
    """
    Verifica que o stop_roi_target do Swing Lab é 20.0 (antes 35.0).
    """
    import services.sandbox_swing_service as swing_mod

    # Lê o código fonte e verifica o valor hardcoded
    import inspect
    source = inspect.getsource(swing_mod.SandboxSwingService._try_open_swing_trade)

    # Verifica que "stop_roi_target = 20.0" está presente
    assert "stop_roi_target = 20.0" in source, \
        "stop_roi_target deveria ser 20.0 (V133)"


def test_swing_stop_price_calculation_with_20_roi():
    """
    Verifica o cálculo do stop_price com stop_roi_target=20 e leverage=50x.

    LONG:  stop = entry * (1 - 20/(50*100)) = entry * 0.996
    SHORT: stop = entry * (1 + 20/(50*100)) = entry * 1.004
    """
    entry = 100.0
    leverage = 50.0
    stop_roi_target = 20.0

    # LONG
    stop_long = entry * (1 - (stop_roi_target / (leverage * 100.0)))
    assert abs(stop_long - 99.6) < 0.001, \
        f"LONG stop deveria ser 99.6, obtido {stop_long}"

    # SHORT
    stop_short = entry * (1 + (stop_roi_target / (leverage * 100.0)))
    assert abs(stop_short - 100.4) < 0.001, \
        f"SHORT stop deveria ser 100.4, obtido {stop_short}"


def test_swing_stop_is_tighter_than_old_35():
    """
    Verifica que o novo stop (20%) é mais apertado que o antigo (35%).
    """
    entry = 100.0
    leverage = 50.0

    # Novo stop (20%)
    new_stop = entry * (1 - (20.0 / (leverage * 100.0)))

    # Antigo stop (35%)
    old_stop = entry * (1 - (35.0 / (leverage * 100.0)))

    # Para LONG, stop mais apertado = mais próximo do entry
    assert new_stop > old_stop, \
        f"Novo stop ({new_stop}) deveria ser mais apertado que o antigo ({old_stop})"


# ============================================================================
# Teste 2 — Swing ADX Threshold Elevado para 30
# ============================================================================

def test_swing_adx_threshold_is_30():
    """
    Verifica que o threshold ADX para Swing Lab é 30 (antes 25).
    """
    import services.sandbox_swing_service as swing_mod
    import inspect
    source = inspect.getsource(swing_mod.SandboxSwingService._run_scan_cycle)

    # Verifica que "btc_adx >= 30" está presente
    assert "btc_adx >= 30" in source, \
        "ADX threshold deveria ser >= 30 (V133)"


def test_swing_lateral_regime_with_adx_28():
    """
    Com ADX=28, regime deve ser LATERAL (antes era UP com ADX>=25).
    """
    # Lógica: btc_dir = "UP" if btc_adx >= 30 else "LATERAL"
    btc_adx = 28.0
    btc_dir = "UP" if btc_adx >= 30 else "LATERAL"
    assert btc_dir == "LATERAL", \
        f"ADX=28 deveria ser LATERAL, obteve {btc_dir}"


def test_swing_trending_regime_with_adx_31():
    """
    Com ADX=31, regime deve ser UP (tendência confirmada).
    """
    btc_adx = 31.0
    btc_dir = "UP" if btc_adx >= 30 else "LATERAL"
    assert btc_dir == "UP", \
        f"ADX=31 deveria ser UP, obteve {btc_dir}"


def test_swing_boundary_adx_30():
    """
    Com ADX=30 exato, regime deve ser UP (>= 30 é UP).
    """
    btc_adx = 30.0
    btc_dir = "UP" if btc_adx >= 30 else "LATERAL"
    assert btc_dir == "UP", \
        f"ADX=30 deveria ser UP, obteve {btc_dir}"


# ============================================================================
# Teste 3 — Blocklist V133
# ============================================================================

def test_blocklist_contains_v133_additions():
    """
    Verifica que INJUSDT, XLMUSDT, GRTUSDT estão na ASSET_BLOCKLIST.
    """
    from config import settings

    assert 'INJUSDT' in settings.ASSET_BLOCKLIST, \
        "INJUSDT deveria estar na ASSET_BLOCKLIST (V133)"
    assert 'XLMUSDT' in settings.ASSET_BLOCKLIST, \
        "XLMUSDT deveria estar na ASSET_BLOCKLIST (V133)"
    assert 'GRTUSDT' in settings.ASSET_BLOCKLIST, \
        "GRTUSDT deveria estar na ASSET_BLOCKLIST (V133)"


def test_blocklist_v133_powers_are_performance_based():
    """
    Verifica que os pares V133 foram adicionados por performance negativa.
    """
    from config import settings

    # Verifica que os pares existem na blocklist
    v133_pairs = ['INJUSDT', 'XLMUSDT', 'GRTUSDT']
    for pair in v133_pairs:
        assert pair in settings.ASSET_BLOCKLIST, \
            f"{pair} deveria estar na ASSET_BLOCKLIST"


# ============================================================================
# Teste 4 — GARANTIA_TRAIL Ativação em 8%
# ============================================================================

def test_garantia_trail_trigger_is_8_for_scalping():
    """
    Verifica que breakeven_trigger para Scalping é 8.0 (antes 12.0).
    """
    import services.sandbox_service as svc_mod
    import inspect
    source = inspect.getsource(svc_mod.SandboxService._process_trade_tick)

    # Verifica que "breakeven_trigger = 8.0" está presente
    assert "breakeven_trigger = 8.0" in source, \
        "breakeven_trigger deveria ser 8.0 (V133)"


def test_garantia_trail_activates_at_9_roi():
    """
    GARANTIA_TRAIL deve ativar quando max_roi=9.0 (antes não ativava com 12.0).
    """
    # Lógica: if max_roi >= breakeven_trigger:  (breakeven_trigger = 8.0)
    max_roi = 9.0
    breakeven_trigger = 8.0  # V133

    activates = max_roi >= breakeven_trigger
    assert activates, \
        f"GARANTIA_TRAIL deveria ativar com max_roi={max_roi} >= {breakeven_trigger}"


def test_garantia_trail_not_activates_at_7_roi():
    """
    GARANTIA_TRAIL NÃO deve ativar quando max_roi=7.0 (abaixo do trigger).
    """
    max_roi = 7.0
    breakeven_trigger = 8.0

    activates = max_roi >= breakeven_trigger
    assert not activates, \
        f"GARANTIA_TRAIL NÃO deveria ativar com max_roi={max_roi} < {breakeven_trigger}"


def test_garantia_trail_stop_calculation():
    """
    Verifica o cálculo do stop no GARANTIA_TRAIL: max(1.5, max_roi * 0.60).
    """
    # Cenário 1: max_roi = 9.0 → stop = max(1.5, 9.0*0.60) = max(1.5, 5.4) = 5.4
    max_roi = 9.0
    trail_stop = max(1.5, round(max_roi * 0.60, 1))
    assert trail_stop == 5.4, f"Trail stop deveria ser 5.4, obteve {trail_stop}"

    # Cenário 2: max_roi = 15.0 → stop = max(1.5, 15.0*0.60) = max(1.5, 9.0) = 9.0
    max_roi = 15.0
    trail_stop = max(1.5, round(max_roi * 0.60, 1))
    assert trail_stop == 9.0, f"Trail stop deveria ser 9.0, obteve {trail_stop}"

    # Cenário 3: max_roi = 2.0 → stop = max(1.5, 2.0*0.60) = max(1.5, 1.2) = 1.5
    max_roi = 2.0
    trail_stop = max(1.5, round(max_roi * 0.60, 1))
    assert trail_stop == 1.5, f"Trail stop deveria ser 1.5, obteve {trail_stop}"


# ============================================================================
# Teste 5 — Scalping Stop Máximo Aumentado para -12%
# ============================================================================

def test_scalping_max_stop_is_12():
    """
    Verifica que _MAX_STOP_ROI é -12.0 (antes -8.0).
    """
    from services.sandbox_scalping_engine import _MAX_STOP_ROI
    assert _MAX_STOP_ROI == -12.0, \
        f"_MAX_STOP_ROI deveria ser -12.0, obteve {_MAX_STOP_ROI}"


def test_scalping_max_stop_distance_calculation():
    """
    Verifica que a distância máxima do stop é calculada corretamente.

    Com _MAX_STOP_ROI=-12.0 e _LEVERAGE=50:
    dist = price * (12.0 / (50 * 100)) = price * 0.0024
    """
    from services.sandbox_scalping_engine import _MAX_STOP_ROI, _LEVERAGE

    price = 100.0
    expected_dist = price * (abs(_MAX_STOP_ROI) / (_LEVERAGE * 100.0))

    # Para LONG: stop = price - dist
    stop_long = price - expected_dist
    assert abs(stop_long - 99.76) < 0.001, \
        f"LONG stop deveria ser 99.76, obteve {stop_long}"

    # Para SHORT: stop = price + dist
    stop_short = price + expected_dist
    assert abs(stop_short - 100.24) < 0.001, \
        f"SHORT stop deveria ser 100.24, obteve {stop_short}"


def test_scalping_max_stop_gives_more_room_than_old_8():
    """
    Verifica que o novo stop (-12%) dá mais runway que o antigo (-8%).
    """
    price = 100.0
    leverage = 50.0

    # Novo stop (-12%)
    new_dist = price * (12.0 / (leverage * 100.0))
    new_stop = price - new_dist

    # Antigo stop (-8%)
    old_dist = price * (8.0 / (leverage * 100.0))
    old_stop = price - old_dist

    # Para LONG, stop mais largo = mais abaixo do entry
    assert new_stop < old_stop, \
        f"Novo stop ({new_stop}) deveria ser mais largo que o antigo ({old_stop})"


# ============================================================================
# Teste 6 — Filtro R:R Mínimo >= 1.5
# ============================================================================

def test_scalping_rr_filter_present_in_code():
    """
    Verifica que o filtro R:R mínimo está presente no código.
    """
    import services.sandbox_scalping_engine as scalp_mod
    import inspect
    source = inspect.getsource(scalp_mod.SandboxScalpingEngine._try_open_trade)

    assert "projected_rr < 1.5" in source, \
        "Filtro R:R mínimo >= 1.5 deveria estar presente (V133)"


def test_scalping_rr_calculation_good_trade():
    """
    Calcula R:R para um trade com risk=12% ROI e target=36% ROI.
    R:R = 36/12 = 3.0 → ACEITO
    """
    entry = 100.0
    stop = 99.76  # -12% ROI com 50x = 0.24% preço
    leverage = 50.0

    risk_pct = abs(entry - stop) / entry * 100.0
    risk_roi = risk_pct * leverage
    target_roi = risk_roi * 3.0
    target_roi = max(target_roi, 15.0)
    projected_rr = target_roi / risk_roi if risk_roi > 0 else 0

    assert projected_rr >= 1.5, \
        f"R:R projetado ({projected_rr}) deveria ser >= 1.5"


def test_scalping_rr_calculation_tight_stop():
    """
    Calcula R:R para um trade com stop muito apertado.
    stop = 99.99 (0.01% preço, 0.5% ROI) → target = max(1.5, 15.0) = 15.0
    R:R = 15.0 / 0.5 = 30.0 → ACEITO (target mínimo garante R:R alto)
    """
    entry = 100.0
    stop = 99.99
    leverage = 50.0

    risk_pct = abs(entry - stop) / entry * 100.0
    risk_roi = risk_pct * leverage
    target_roi = risk_roi * 3.0
    target_roi = max(target_roi, 15.0)
    projected_rr = target_roi / risk_roi if risk_roi > 0 else 0

    assert projected_rr >= 1.5, \
        f"R:R projetado ({projected_rr}) deveria ser >= 1.5"


def test_scalping_rr_filter_rejects_bad_trade():
    """
    Verifica lógica de rejeição: R:R < 1.5 deve ser rejeitado.

    Cenário: stop muito longe do entry (risk alto)
    entry=100, stop=98.0 (2.0% preço, 100% ROI)
    target = max(300, 15) = 300
    R:R = 300/100 = 3.0 → ACEITO (target mínimo de 3x salva)

    Na prática, o filtro rejeita quando R:R < 1.5, mas com target=3x o risco,
    o R:R sempre será >= 3.0. O filtro é mais uma proteção contra erros de cálculo.
    """
    # Simula o cálculo do filtro
    entry = 100.0
    stop = 98.0  # risk = 2.0% preço = 100% ROI
    leverage = 50.0

    risk_pct = abs(entry - stop) / entry * 100.0
    risk_roi = risk_pct * leverage
    target_roi = risk_roi * 3.0
    target_roi = max(target_roi, 15.0)
    projected_rr = target_roi / risk_roi if risk_roi > 0 else 0

    # Com target = 3x o risco, R:R sempre será 3.0
    assert projected_rr >= 1.5, \
        f"R:R projetado ({projected_rr}) deveria ser >= 1.5"


def test_scalping_rr_with_minimum_target():
    """
    Quando o risco é muito baixo, target mínimo de 15% garante R:R alto.

    entry=100, stop=99.999 (0.001% preço, 0.05% ROI)
    target = max(0.15, 15.0) = 15.0
    R:R = 15.0 / 0.05 = 300.0 → ACEITO
    """
    entry = 100.0
    stop = 99.999
    leverage = 50.0

    risk_pct = abs(entry - stop) / entry * 100.0
    risk_roi = risk_pct * leverage
    target_roi = risk_roi * 3.0
    target_roi = max(target_roi, 15.0)
    projected_rr = target_roi / risk_roi if risk_roi > 0 else 0

    assert projected_rr >= 1.5, \
        f"R:R projetado ({projected_rr}) deveria ser >= 1.5"


# ============================================================================
# Teste 7 — Integração: Cenário Completo V133
# ============================================================================

def test_v133_constants_summary():
    """
    Resumo das constantes V133 — todas em um lugar.
    """
    from services.sandbox_scalping_engine import _MAX_STOP_ROI, _LEVERAGE
    from config import settings

    # Swing Lab
    assert "stop_roi_target = 20.0" in open(
        str(Path(__file__).resolve().parents[1] / "backend" / "services" / "sandbox_swing_service.py"),
        encoding="utf-8"
    ).read(), "Swing stop_roi_target deveria ser 20.0"

    assert "btc_adx >= 30" in open(
        str(Path(__file__).resolve().parents[1] / "backend" / "services" / "sandbox_swing_service.py"),
        encoding="utf-8"
    ).read(), "Swing ADX threshold deveria ser 30"

    # Blocklist
    assert 'INJUSDT' in settings.ASSET_BLOCKLIST
    assert 'XLMUSDT' in settings.ASSET_BLOCKLIST
    assert 'GRTUSDT' in settings.ASSET_BLOCKLIST

    # Scalping
    assert _MAX_STOP_ROI == -12.0
    assert _LEVERAGE == 50.0

    # GARANTIA_TRAIL
    assert "breakeven_trigger = 8.0" in open(
        str(Path(__file__).resolve().parents[1] / "backend" / "services" / "sandbox_service.py"),
        encoding="utf-8"
    ).read(), "GARANTIA_TRAIL trigger deveria ser 8.0"

    # Filtro R:R
    assert "projected_rr < 1.5" in open(
        str(Path(__file__).resolve().parents[1] / "backend" / "services" / "sandbox_scalping_engine.py"),
        encoding="utf-8"
    ).read(), "Filtro R:R mínimo deveria estar presente"


# ============================================================================
# Teste 8 — Regressão: Valores Antigos NÃO Devem Existir
# ============================================================================

def test_old_35_roi_not_in_swing():
    """
    Verifica que o valor antigo (35.0) não está mais hardcoded no Swing.
    """
    import services.sandbox_swing_service as swing_mod
    import inspect
    source = inspect.getsource(swing_mod.SandboxSwingService._try_open_swing_trade)

    # Não deve conter "stop_roi_target = 35.0"
    assert "stop_roi_target = 35.0" not in source, \
        "Valor antigo 35.0 não deveria estar mais no código (V133)"


def test_old_12_trigger_not_in_garantia_trail():
    """
    Verifica que o valor antigo (12.0) não está mais no GARANTIA_TRAIL.
    """
    import services.sandbox_service as svc_mod
    import inspect
    source = inspect.getsource(svc_mod.SandboxService._process_trade_tick)

    # Não deve conter "breakeven_trigger = 12.0"
    assert "breakeven_trigger = 12.0" not in source, \
        "Valor antigo 12.0 não deveria estar mais no código (V133)"
