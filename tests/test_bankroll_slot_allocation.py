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
    monkeypatch.setattr(manager, "_get_operating_balance", fake_balance)

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
    monkeypatch.setattr(manager, "_get_operating_balance", fake_balance)

    assert await manager.can_open_new_slot(symbol="SUIUSDT", slot_type="BLITZ_30M") is None
