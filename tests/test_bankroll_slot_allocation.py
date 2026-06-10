import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.bankroll import BankrollManager
from services.okx_rest import okx_rest_service
from services.database_service import database_service


def _slot(slot_id, symbol=None, qty=0, entry_price=0, status_risco="IDLE"):
    return {
        "id": slot_id,
        "symbol": symbol,
        "side": "Buy",
        "qty": qty,
        "entry_price": entry_price,
        "current_stop": 0,
        "leverage": 50,
        "status": None,
        "status_risco": status_risco,
    }


def test_paper_equity_snapshot_uses_postgres_projection_totals():
    manager = BankrollManager()

    snapshot = manager._paper_equity_snapshot(
        base_balance=20.0,
        realized_pnl=-10.6063,
        active_slots=[
            {"symbol": "SENTUSDT", "qty": 1, "projection": {"pnl_usd": -0.315}},
            {"symbol": "ATOMUSDT", "qty": 1, "projection": {"pnl_usd": -1.204}},
            {"symbol": None, "qty": 0, "projection": {"pnl_usd": 999}},
            {"symbol": "INJUSDT", "qty": 1, "projection": {"pnl_usd": -3.0525}},
        ],
        active_moonbags=[
            {"symbol": "KAITOUSDT", "qty": 1, "projection": {"pnl_usd": 12.309}},
            {"symbol": "OPNUSDT", "qty": 1, "projection": {"pnl_usd": 47.573}},
        ],
    )

    assert snapshot["open_slots_pnl"] == pytest.approx(-4.5715)
    assert snapshot["open_moonbags_pnl"] == pytest.approx(59.882)
    assert snapshot["calculated_equity"] == pytest.approx(64.7042)
    assert snapshot["active_slots"] == 3
    assert snapshot["active_moonbags"] == 2


@pytest.mark.asyncio
async def test_paper_capacity_uses_postgres_slots_not_stale_memory(monkeypatch):
    manager = BankrollManager()
    manager.pending_slots.clear()

    monkeypatch.setattr(okx_rest_service, "execution_mode", "PAPER")
    monkeypatch.setattr(
        okx_rest_service,
        "paper_positions",
        [
            {"symbol": "DASHUSDT.P", "status": "RECOVERED"},
            {"symbol": "APTUSDT", "status": "RECOVERED"},
            {"symbol": "KAITOUSDT", "status": "RECOVERED"},
            {"symbol": "OPNUSDT", "status": "RECOVERED"},
        ],
    )

    async def fake_get_active_slots():
        return [
            _slot(1, "DASHUSDT.P", qty=100, entry_price=35.78, status_risco="ATIVO"),
            _slot(2, "APTUSDT", qty=10, entry_price=0.6744, status_risco="ATIVO"),
            _slot(3),
            _slot(4),
        ]

    async def fake_get_moonbags():
        return [
            {"symbol": "KAITOUSDT"},
            {"symbol": "OPNUSDT"},
        ]

    async def fake_balance():
        return 20.0

    monkeypatch.setattr(database_service, "get_active_slots", fake_get_active_slots)
    monkeypatch.setattr(database_service, "get_moonbags", fake_get_moonbags)
    monkeypatch.setattr(manager, "get_live_operating_equity", fake_balance)

    assert await manager.can_open_new_slot(symbol="CRVUSDT", slot_type="BLITZ_30M") == 3


@pytest.mark.asyncio
async def test_paper_capacity_still_blocks_when_postgres_slots_are_full(monkeypatch):
    manager = BankrollManager()
    manager.pending_slots.clear()

    monkeypatch.setattr(okx_rest_service, "execution_mode", "PAPER")
    monkeypatch.setattr(okx_rest_service, "paper_positions", [])

    async def fake_get_active_slots():
        return [
            _slot(1, "DASHUSDT.P", qty=100, entry_price=35.78, status_risco="ATIVO"),
            _slot(2, "APTUSDT", qty=10, entry_price=0.6744, status_risco="ATIVO"),
            _slot(3, "CRVUSDT", qty=10, entry_price=0.3, status_risco="ATIVO"),
            _slot(4, "INJUSDT", qty=10, entry_price=12.0, status_risco="ATIVO"),
        ]

    async def fake_get_moonbags():
        return []

    async def fake_balance():
        return 20.0

    monkeypatch.setattr(database_service, "get_active_slots", fake_get_active_slots)
    monkeypatch.setattr(database_service, "get_moonbags", fake_get_moonbags)
    monkeypatch.setattr(manager, "get_live_operating_equity", fake_balance)

    assert await manager.can_open_new_slot(symbol="SUIUSDT", slot_type="BLITZ_30M") is None


@pytest.mark.asyncio
async def test_paper_capacity_blocks_on_critical_live_equity(monkeypatch):
    manager = BankrollManager()
    manager.pending_slots.clear()

    monkeypatch.setattr(okx_rest_service, "execution_mode", "PAPER")
    monkeypatch.setattr(okx_rest_service, "paper_positions", [])

    async def fake_get_active_slots():
        return [_slot(1), _slot(2), _slot(3), _slot(4)]

    async def fake_get_moonbags():
        return []

    async def fake_live_equity():
        return 1.75

    monkeypatch.setattr(database_service, "get_active_slots", fake_get_active_slots)
    monkeypatch.setattr(database_service, "get_moonbags", fake_get_moonbags)
    monkeypatch.setattr(manager, "get_live_operating_equity", fake_live_equity)

    assert await manager.can_open_new_slot(symbol="SUIUSDT", slot_type="BLITZ_30M") is None
