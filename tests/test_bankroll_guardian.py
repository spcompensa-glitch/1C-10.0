import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.agents.bankroll_guardian import BankrollGuardian


async def _trending_market():
    """Retorna dados de mercado em tendência para que os testes
    de autorização passem pelo filtro MERCADO MORTO."""
    return {
        "adx": 27.0,
        "direction": "UP",
        "is_ranging": False,
        "is_trending": True,
        "is_strong_trend": False,
    }

def _guardian_report(min_score=80.0, active_slots=1, max_slots=4):
    return {
        "mode": "ACUMULACAO_PROTEGIDA",
        "health_score": 94,
        "active_slots": active_slots,
        "max_slots_allowed": max_slots,
        "min_score_required": min_score,
        "suspended_symbols": [],
    }


def test_profitable_moonbag_keeps_accumulation_protected_when_below_profit_floor():
    guardian = BankrollGuardian()
    guardian.peak_equity = 45.7288

    health = guardian._health_mode(
        equity=36.6753,
        base_balance=20.0,
        active_slots=2,
        active_moonbags=1,
        open_moonbags_pnl=29.606,
    )

    assert health["mode"] == "ACUMULACAO_PROTEGIDA"
    assert health["max_slots"] == 20
    assert health["min_score"] < 999.0
    assert "Moonbag lucrativa ativa" in health["reasons"][0]


def test_unsecured_equity_peak_does_not_create_profit_floor():
    guardian = BankrollGuardian()
    guardian.peak_equity = 20.9

    health = guardian._health_mode(
        equity=20.7,
        base_balance=20.0,
        active_slots=2,
        active_moonbags=0,
        open_moonbags_pnl=0.0,
    )

    assert health["mode"] == "ACUMULACAO"
    assert health["max_slots"] == 20
    assert health["locked_profit"] == 0.0
    assert health["protected_floor"] == 20.0


def test_guardian_locks_only_realized_or_stop_secured_profit():
    guardian = BankrollGuardian()
    guardian.peak_equity = 23.2086

    health = guardian._health_mode(
        equity=20.637,
        base_balance=20.0,
        active_slots=4,
        active_moonbags=0,
        open_moonbags_pnl=0.0,
        protected_slots=1,
        realized_pnl=0.7672,
        secured_open_pnl=0.25,
    )

    assert health["mode"] == "ACUMULACAO_PROTEGIDA"
    assert guardian.protected_profit_peak == pytest.approx(0.637)
    assert health["locked_profit"] == pytest.approx(0.4459)
    assert health["protected_floor"] == pytest.approx(20.4459)
    assert health["locked_profit"] < 1.0


def test_small_unprotected_peak_does_not_pause_slot_factory():
    guardian = BankrollGuardian()
    guardian.peak_equity = 20.2189

    health = guardian._health_mode(
        equity=20.0199,
        base_balance=20.0,
        active_slots=1,
        active_moonbags=0,
        open_moonbags_pnl=0.0,
        protected_slots=0,
    )

    assert health["mode"] == "ACUMULACAO"
    assert health["max_slots"] == 20
    assert health["min_score"] < 999.0
    assert health["locked_profit"] == 0.0
    assert health["protected_floor"] == 20.0


def test_critical_live_equity_triggers_operational_kill_switch():
    guardian = BankrollGuardian()

    health = guardian._health_mode(
        equity=1.75,
        base_balance=20.0,
        active_slots=0,
        active_moonbags=0,
        open_moonbags_pnl=0.0,
    )

    assert health["mode"] == "PRESERVACAO_TOTAL"
    assert health["max_slots"] == 0
    assert health["min_score"] == 999.0
    assert "Equity viva critica" in health["reasons"][0]


def test_protected_slot_keeps_accumulation_protected_when_below_profit_floor():
    guardian = BankrollGuardian()
    guardian.peak_equity = 45.7288

    health = guardian._health_mode(
        equity=36.6753,
        base_balance=20.0,
        active_slots=2,
        active_moonbags=0,
        open_moonbags_pnl=0.0,
        protected_slots=1,
    )

    assert health["mode"] == "ACUMULACAO_PROTEGIDA"
    assert health["max_slots"] == 20
    assert health["min_score"] < 999.0
    assert "stop em break-even/lucro" in health["reasons"][0]


def test_position_stop_roi_detects_long_and_short_profit_lock():
    guardian = BankrollGuardian()

    long_stop_roi = guardian._position_stop_roi({
        "side": "buy",
        "entry_price": 1.0,
        "current_stop": 1.01,
        "leverage": 50,
    })
    short_stop_roi = guardian._position_stop_roi({
        "side": "sell",
        "entry_price": 1.0,
        "current_stop": 0.99,
        "leverage": 50,
    })

    assert long_stop_roi == pytest.approx(50.0)
    assert short_stop_roi == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_guardian_uses_radar_score_not_unified_confidence_for_minimum(monkeypatch):
    guardian = BankrollGuardian()

    async def fake_health():
        return _guardian_report(min_score=80.0)

    monkeypatch.setattr(guardian, "evaluate_bank_health", fake_health)
    monkeypatch.setattr(guardian, "_get_market_data", _trending_market)

    decision = await guardian.authorize_new_trade({
        "symbol": "TIAUSDT",
        "score": 99,
        "unified_confidence": 59.7,
    })

    assert decision["approved"] is True
    assert decision["score"] == pytest.approx(99.0)
    assert decision["radar_score"] == pytest.approx(99.0)
    assert decision["unified_confidence"] == pytest.approx(59.7)


@pytest.mark.asyncio
async def test_guardian_still_blocks_low_radar_score(monkeypatch):
    guardian = BankrollGuardian()

    async def fake_health():
        return _guardian_report(min_score=80.0)

    monkeypatch.setattr(guardian, "evaluate_bank_health", fake_health)
    monkeypatch.setattr(guardian, "_get_market_data", _trending_market)

    decision = await guardian.authorize_new_trade({
        "symbol": "AVAXUSDT",
        "score": 69,
        "unified_confidence": 95.0,
    })

    assert decision["approved"] is False
    assert "Score 69.0 abaixo do minimo da banca" in decision["reasons"][0]
