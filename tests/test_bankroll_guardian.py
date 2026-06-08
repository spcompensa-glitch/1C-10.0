import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.agents.bankroll_guardian import BankrollGuardian


def _guardian_report(min_score=80.0, active_slots=1, max_slots=4):
    return {
        "mode": "ACUMULACAO_PROTEGIDA",
        "health_score": 94,
        "active_slots": active_slots,
        "max_slots_allowed": max_slots,
        "min_score_required": min_score,
        "suspended_symbols": [],
    }


@pytest.mark.asyncio
async def test_guardian_uses_radar_score_not_unified_confidence_for_minimum(monkeypatch):
    guardian = BankrollGuardian()

    async def fake_health():
        return _guardian_report(min_score=80.0)

    monkeypatch.setattr(guardian, "evaluate_bank_health", fake_health)

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

    decision = await guardian.authorize_new_trade({
        "symbol": "AVAXUSDT",
        "score": 69,
        "unified_confidence": 95.0,
    })

    assert decision["approved"] is False
    assert "Score 69.0 abaixo do minimo da banca" in decision["reasons"][0]
