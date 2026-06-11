import sys
import time
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.bankroll import bankroll_manager
from services.sentinel_auditor import SentinelAuditor
from services.sentinel_auditor import firebase_service, okx_rest_service


def _active_slot(symbol: str):
    return {
        "id": 1,
        "symbol": symbol,
        "side": "Sell",
        "entry_price": 1.0,
        "current_stop": 0.99,
        "qty": 1.0,
        "entry_margin": 0.02,
        "leverage": 50,
        "opened_at": time.time() - 60,
    }


@pytest.mark.asyncio
async def test_pending_closure_is_not_archived_as_orphan(monkeypatch):
    symbol = "MONUSDT"
    auditor = SentinelAuditor()
    reset_calls = []

    async def fake_slots(force_refresh=False):
        return [_active_slot(symbol)]

    async def fake_positions():
        return []

    async def fake_reset(*args, **kwargs):
        reset_calls.append((args, kwargs))

    monkeypatch.setattr(firebase_service, "get_active_slots", fake_slots)
    monkeypatch.setattr(firebase_service, "hard_reset_slot", fake_reset)
    monkeypatch.setattr(okx_rest_service, "get_active_positions", fake_positions)
    monkeypatch.setattr(okx_rest_service, "pending_closures", {symbol})
    bankroll_manager.recently_closed.pop(symbol, None)

    await auditor.reconcile()

    assert reset_calls == []
    assert symbol not in auditor._orphan_missing_since
    assert auditor.divergences_detected == 0


@pytest.mark.asyncio
async def test_transient_position_absence_requires_persistent_divergence(monkeypatch):
    symbol = "TESTUSDT"
    auditor = SentinelAuditor()
    reset_calls = []

    async def fake_slots(force_refresh=False):
        return [_active_slot(symbol)]

    async def fake_positions():
        return []

    async def fake_reset(*args, **kwargs):
        reset_calls.append((args, kwargs))

    monkeypatch.setattr(firebase_service, "get_active_slots", fake_slots)
    monkeypatch.setattr(firebase_service, "hard_reset_slot", fake_reset)
    monkeypatch.setattr(okx_rest_service, "get_active_positions", fake_positions)
    monkeypatch.setattr(okx_rest_service, "pending_closures", set())
    bankroll_manager.recently_closed.pop(symbol, None)

    await auditor.reconcile()

    assert reset_calls == []
    assert symbol in auditor._orphan_missing_since
    assert auditor.divergences_detected == 0
