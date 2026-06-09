import asyncio
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.agents.flash_agent import FlashAgent
from services.order_projection_service import order_projection_service


def _price_from_roi(entry_price, roi_percent, side, leverage, tick_size):
    raw = order_projection_service.raw_price_from_roi(
        entry_price,
        roi_percent,
        side,
        leverage,
    )
    return order_projection_service.round_to_tick(raw, tick_size)


@pytest.mark.asyncio
async def test_flash_scans_100_moonbags_with_peak_trailing_and_okx_contract_ticks(monkeypatch):
    flash = FlashAgent()
    updated = []
    closed = []
    stop_checks = {}

    tick_sizes = [0.0001, 0.0005, 0.001, 0.005, 0.01]
    peak_rois = [1400.0, 1600.0, 1800.0, 2000.0, 2200.0]
    moons = []
    expected_updates = {}
    expected_closed = set()
    current_prices = {}
    peak_prices = {}
    contract_by_symbol = {}

    for index in range(100):
        side = "buy" if index % 2 == 0 else "sell"
        side_label = "Buy" if side == "buy" else "Sell"
        symbol = f"SIM{index:03d}USDT"
        leverage = 50.0
        entry_price = 0.25 + (index * 0.017)
        qty = 10.0 + index
        tick_size = tick_sizes[index % len(tick_sizes)]
        peak_roi = peak_rois[index % len(peak_rois)]
        target_stop_roi = peak_roi - 200.0
        current_stop_roi = max(1000.0, target_stop_roi - 400.0)
        current_roi = peak_roi - 250.0

        contract_meta = {
            "tick_size": tick_size,
            "ct_val": [0.01, 0.1, 1.0, 10.0][index % 4],
            "qty_step": [0.1, 1.0, 10.0][index % 3],
            "min_qty": [0.1, 1.0][index % 2],
        }
        contract_by_symbol[symbol] = contract_meta

        current_stop = _price_from_roi(
            entry_price,
            current_stop_roi,
            side,
            leverage,
            tick_size,
        )
        expected_stop = _price_from_roi(
            entry_price,
            target_stop_roi,
            side,
            leverage,
            tick_size,
        )

        moon = {
            "uuid": f"{symbol}_stress_{index}",
            "symbol": symbol,
            "side": side_label,
            "qty": qty,
            "entry_price": entry_price,
            "current_stop": current_stop,
            "leverage": leverage,
            "flash_last_stop_roi": current_stop_roi,
            "pnl_percent": current_roi,
            "contract_meta": contract_meta,
        }
        moons.append(moon)

        current_prices[symbol] = order_projection_service.raw_price_from_roi(
            entry_price,
            current_roi,
            side,
            leverage,
        )
        peak_prices[symbol] = order_projection_service.raw_price_from_roi(
            entry_price,
            peak_roi,
            side,
            leverage,
        )
        expected_updates[moon["uuid"]] = {
            "symbol": symbol,
            "side": side,
            "stop_price": expected_stop,
            "stop_roi": target_stop_roi,
            "action": f"ULTRA_{int(peak_roi)}",
        }
        if index % 4 == 0:
            expected_closed.add(moon["uuid"])

    async def fake_get_moonbags():
        return moons

    async def fake_get_current_price(symbol):
        return current_prices[symbol]

    def fake_get_peak_price(symbol, side, current_price):
        return peak_prices[symbol]

    async def fake_calc_stop_price(entry_price, stop_roi, side, leverage, symbol):
        return _price_from_roi(
            entry_price,
            stop_roi,
            side,
            leverage,
            contract_by_symbol[symbol]["tick_size"],
        )

    async def fake_check_stop_hit(side, stop_price, symbol):
        stop_checks[symbol] = stop_checks.get(symbol, 0) + 1
        index = int(symbol[3:6])
        return stop_checks[symbol] == 2 and index % 4 == 0

    async def fake_update_moonbag_sl(moon_uuid, symbol, sl_price, roi, flash_action="MOONBAG_TRAIL", stop_roi=None):
        updated.append(
            {
                "uuid": moon_uuid,
                "symbol": symbol,
                "sl_price": sl_price,
                "roi": roi,
                "flash_action": flash_action,
                "stop_roi": stop_roi,
            }
        )

    async def fake_close_moonbag(moon_uuid, symbol, side, qty, reason):
        closed.append(
            {
                "uuid": moon_uuid,
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "reason": reason,
            }
        )

    monkeypatch.setattr("services.agents.flash_agent.database_service.get_moonbags", fake_get_moonbags)
    monkeypatch.setattr(flash, "_get_current_price", fake_get_current_price)
    monkeypatch.setattr(flash, "_get_peak_price", fake_get_peak_price)
    monkeypatch.setattr(flash, "_calc_stop_price", fake_calc_stop_price)
    monkeypatch.setattr(flash, "_check_stop_hit", fake_check_stop_hit)
    monkeypatch.setattr(flash, "_update_moonbag_sl", fake_update_moonbag_sl)
    monkeypatch.setattr(flash, "_close_moonbag", fake_close_moonbag)

    flash._last_moonbags_refresh = 0.0
    flash._moonbags_cache_ttl = 0.0

    await flash._scan_all_moonbags()
    await asyncio.sleep(0)

    assert len(updated) == 100
    assert len(closed) == 25
    assert set(stop_checks.values()) == {2}

    updates_by_uuid = {item["uuid"]: item for item in updated}
    assert set(updates_by_uuid) == set(expected_updates)

    for moon_uuid, expected in expected_updates.items():
        actual = updates_by_uuid[moon_uuid]
        assert actual["symbol"] == expected["symbol"]
        assert actual["flash_action"] == expected["action"]
        assert actual["stop_roi"] == pytest.approx(expected["stop_roi"])
        assert actual["sl_price"] == pytest.approx(expected["stop_price"])

    closed_by_uuid = {item["uuid"]: item for item in closed}
    assert set(closed_by_uuid) == expected_closed
    for moon_uuid in expected_closed:
        assert closed_by_uuid[moon_uuid]["reason"].startswith("MOONBAG_TRAIL_SL_")
