import asyncio
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.agents.flash_agent import FlashAgent


def test_stop_improvement_direction_is_consistent_for_long_and_short():
    flash = FlashAgent()

    assert flash._stop_improves("buy", 100.0, 102.0) is True
    assert flash._stop_improves("buy", 102.0, 100.0) is False
    assert flash._stop_improves("sell", 100.0, 98.0) is True
    assert flash._stop_improves("sell", 98.0, 100.0) is False


def test_moonbag_hard_lock_never_drops_below_emancipation():
    flash = FlashAgent()

    assert flash._moonbag_hard_lock_roi({}) == pytest.approx(110.0)
    assert flash._moonbag_hard_lock_roi({"flash_last_stop_roi": 25}) == pytest.approx(110.0)
    assert flash._moonbag_hard_lock_roi({"flash_last_stop_roi": 500}) == pytest.approx(500.0)


@pytest.mark.asyncio
async def test_moonbag_short_uses_hard_lock_stop_when_persisted_stop_regressed(monkeypatch):
    flash = FlashAgent()
    closed = []
    updated = []

    moon = {
        "uuid": "XPLUSDT_1780848480",
        "symbol": "XPLUSDT",
        "side": "Sell",
        "qty": 218.0,
        "entry_price": 0.06876,
        "current_stop": 0.06842,
        "leverage": 50.0,
        "flash_last_stop_roi": 110.0,
    }

    async def fake_get_current_price(symbol):
        assert symbol == "XPLUSDT"
        return 0.06806

    async def fake_calc_stop_price(entry_price, stop_roi, side, leverage, symbol):
        assert stop_roi == pytest.approx(110.0)
        assert side == "sell"
        return 0.06725

    async def fake_check_stop_hit(side, stop_price, symbol):
        assert side == "sell"
        assert stop_price == pytest.approx(0.06725)
        return True

    async def fake_update_moonbag_sl(moon_uuid, symbol, sl_price, roi, flash_action="MOONBAG_TRAIL", stop_roi=None):
        updated.append((moon_uuid, symbol, sl_price, flash_action, stop_roi))

    async def fake_close_moonbag(moon_uuid, symbol, side, qty, reason):
        closed.append((moon_uuid, symbol, side, qty, reason))

    monkeypatch.setattr(flash, "_get_current_price", fake_get_current_price)
    monkeypatch.setattr(flash, "_calc_stop_price", fake_calc_stop_price)
    monkeypatch.setattr(flash, "_check_stop_hit", fake_check_stop_hit)
    monkeypatch.setattr(flash, "_update_moonbag_sl", fake_update_moonbag_sl)
    monkeypatch.setattr(flash, "_close_moonbag", fake_close_moonbag)

    await flash._process_moonbag(moon)
    await asyncio.sleep(0)

    assert updated == [("XPLUSDT_1780848480", "XPLUSDT", 0.06725, "EMANCIPADA", 110.0)]
    assert len(closed) == 1
    assert closed[0][0] == "XPLUSDT_1780848480"
    assert closed[0][1] == "XPLUSDT"
    assert closed[0][2] == "sell"
    assert closed[0][4].startswith("MOONBAG_SL_")


@pytest.mark.asyncio
async def test_slot_uses_recent_peak_roi_to_emancipate_after_pullback(monkeypatch):
    flash = FlashAgent()
    updated = []
    emancipated = []

    slot = {
        "id": 3,
        "symbol": "ZECUSDT",
        "side": "Buy",
        "qty": 35.0,
        "entry_price": 422.44,
        "current_stop": 426.24,
        "leverage": 50.0,
        "pnl_percent": 74.0,
        "genesis_id": "SWG-1780848505-ZECU-40A404",
        "contract_meta": {"tick_size": 0.01, "ct_val": 0.01, "qty_step": 1.0, "min_qty": 1.0},
    }

    async def fake_get_current_price(symbol):
        assert symbol == "ZECUSDT"
        return 428.74  # ~74.6% ROI: current price already pulled back

    def fake_get_peak_price(symbol, side, current_price):
        assert symbol == "ZECUSDT"
        assert side == "buy"
        return 437.64  # ~180% ROI: emancipation was touched recently

    checked_stops = []

    async def fake_check_stop_hit(side, stop_price, symbol):
        checked_stops.append(stop_price)
        return False

    async def fake_update_slot_sl(slot_id, symbol, sl_price, status_risco, side, qty):
        updated.append((slot_id, symbol, sl_price, status_risco, side, qty))

    async def fake_emancipate_slot(slot_id, symbol, sl_price):
        emancipated.append((slot_id, symbol, sl_price))

    monkeypatch.setattr(flash, "_get_current_price", fake_get_current_price)
    monkeypatch.setattr(flash, "_get_peak_price", fake_get_peak_price)
    monkeypatch.setattr(flash, "_check_stop_hit", fake_check_stop_hit)
    monkeypatch.setattr(flash, "_update_slot_sl", fake_update_slot_sl)
    monkeypatch.setattr(flash, "_emancipate_slot", fake_emancipate_slot)
    monkeypatch.setattr(flash, "_update_pnl", lambda *args, **kwargs: None)

    await flash._process_slot(slot)

    assert checked_stops == [pytest.approx(426.24), pytest.approx(431.73)]
    assert updated == [(3, "ZECUSDT", pytest.approx(431.73), "PROFIT_LOCK", "buy", 35.0)]
    assert emancipated == [(3, "ZECUSDT", pytest.approx(431.73))]
