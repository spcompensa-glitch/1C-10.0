import sys
import types
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.agents.oracle_agent import OracleAgent


def _install_fake_bankroll(monkeypatch):
    fake_module = types.ModuleType("services.bankroll")

    class _FakeBankrollManager:
        hedge_active = False

        async def auto_close_hedge(self, reason: str):
            return reason

    fake_module.bankroll_manager = _FakeBankrollManager()
    monkeypatch.setitem(sys.modules, "services.bankroll", fake_module)


@pytest.mark.asyncio
async def test_oracle_derives_transition_regime_and_up_direction(monkeypatch):
    _install_fake_bankroll(monkeypatch)
    agent = OracleAgent()

    await agent.update_market_data(
        "test",
        {
            "btc_adx": 23.4,
            "btc_variation_1h": 0.61,
            "btc_variation_15m": 0.18,
        },
    )

    ctx = agent.get_validated_context()
    assert ctx["regime"] == "TRANSITION"
    assert ctx["btc_direction"] == "UP"


@pytest.mark.asyncio
async def test_oracle_derives_roaring_regime_and_down_direction(monkeypatch):
    _install_fake_bankroll(monkeypatch)
    agent = OracleAgent()

    await agent.update_market_data(
        "test",
        {
            "btc_adx": 31.2,
            "btc_variation_1h": -1.4,
            "btc_variation_15m": -0.52,
        },
    )

    ctx = agent.get_validated_context()
    assert ctx["regime"] == "ROARING"
    assert ctx["btc_direction"] == "DOWN"


@pytest.mark.asyncio
async def test_oracle_keeps_last_valid_adx_when_zero_update_arrives(monkeypatch):
    _install_fake_bankroll(monkeypatch)
    agent = OracleAgent()

    await agent.update_market_data(
        "test",
        {
            "btc_adx": 28.0,
            "btc_variation_1h": 0.4,
            "btc_variation_15m": -0.1,
        },
    )
    await agent.update_market_data("test", {"btc_adx": 0.0})

    ctx = agent.get_validated_context()
    assert ctx["btc_adx"] == pytest.approx(28.0)
    assert ctx["regime"] == "TRENDING"


@pytest.mark.asyncio
async def test_oracle_restores_15m_variation_from_lkg(monkeypatch):
    _install_fake_bankroll(monkeypatch)
    agent = OracleAgent()

    async def fake_get_oracle_context():
        return {
            "btc_adx": 26.3,
            "btc_variation_1h": -0.8,
            "btc_variation_15m": -0.22,
            "btc_variation_24h": -1.9,
            "btc_price": 65000.0,
            "dominance": 58.2,
        }

    monkeypatch.setattr("services.agents.oracle_agent.firebase_service.get_oracle_context", fake_get_oracle_context)
    def _discard_task(coro):
        coro.close()
        return None

    monkeypatch.setattr("services.agents.oracle_agent.asyncio.create_task", _discard_task)

    await agent.initialize()

    ctx = agent.get_validated_context()
    assert ctx["btc_variation_15m"] == pytest.approx(-0.22)
    assert ctx["btc_direction"] == "DOWN"
    assert ctx["regime"] == "TRENDING"
