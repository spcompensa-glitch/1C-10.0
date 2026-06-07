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
