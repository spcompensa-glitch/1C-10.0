import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.order_projection_service import order_projection_service


@pytest.mark.asyncio
async def test_long_emancipation_stop_uses_leverage_roi_and_tick_size():
    order = {
        "symbol": "ZECUSDT",
        "side": "BUY",
        "entry_price": 100.0,
        "current_stop": 0.0,
        "leverage": 50.0,
        "qty": 10.0,
        "contract_meta": {"tick_size": 0.01, "ct_val": 0.1, "qty_step": 1.0, "min_qty": 1.0},
    }

    projection = await order_projection_service.build_projection(
        order,
        current_price=103.0,
        phase_hint="SLOT",
        fetch_contract=False,
    )

    assert projection["roi_percent"] == pytest.approx(150.0)
    assert projection["phase"] == "EMANCIPACAO"
    assert projection["recommended_stop"] == pytest.approx(102.2)
    assert projection["active_level"]["stop_roi"] == 110.0
    assert projection["next_level"]["name"] == "WAVE"
    assert projection["should_emancipate"] is True


@pytest.mark.asyncio
async def test_short_emancipation_stop_moves_below_entry():
    order = {
        "symbol": "ZECUSDT",
        "side": "SELL",
        "entry_price": 100.0,
        "current_stop": 0.0,
        "leverage": 50.0,
        "qty": 10.0,
        "contract_meta": {"tick_size": 0.01, "ct_val": 0.1, "qty_step": 1.0, "min_qty": 1.0},
    }

    projection = await order_projection_service.build_projection(
        order,
        current_price=97.0,
        phase_hint="SLOT",
        fetch_contract=False,
    )

    assert projection["roi_percent"] == pytest.approx(150.0)
    assert projection["phase"] == "EMANCIPACAO"
    assert projection["recommended_stop"] == pytest.approx(97.8)
    assert projection["next_level"]["name"] == "WAVE"
    assert projection["should_emancipate"] is True


@pytest.mark.asyncio
async def test_slot_projection_above_200_roi_still_requires_emancipation_first():
    order = {
        "symbol": "ZECUSDT",
        "side": "BUY",
        "entry_price": 100.0,
        "current_stop": 0.0,
        "leverage": 50.0,
        "qty": 10.0,
        "contract_meta": {"tick_size": 0.01, "ct_val": 0.1, "qty_step": 1.0, "min_qty": 1.0},
    }

    projection = await order_projection_service.build_projection(
        order,
        current_price=104.5,
        phase_hint="SLOT",
        fetch_contract=False,
    )

    assert projection["roi_percent"] == pytest.approx(225.0)
    assert projection["phase"] == "EMANCIPACAO"
    assert projection["active_level"]["name"] == "WAVE"
    assert projection["should_emancipate"] is True


@pytest.mark.asyncio
async def test_moonbag_level_uses_same_order_projection():
    order = {
        "symbol": "PEPEUSDT",
        "side": "BUY",
        "entry_price": 0.001,
        "current_stop": 0.0,
        "leverage": 50.0,
        "qty": 1000.0,
        "contract_meta": {"tick_size": 0.000001, "ct_val": 1.0, "qty_step": 1.0, "min_qty": 1.0},
    }

    projection = await order_projection_service.build_projection(
        order,
        current_price=0.00106,
        phase_hint="MOONBAG",
        fetch_contract=False,
    )

    assert projection["roi_percent"] == pytest.approx(300.0)
    assert projection["phase"] == "MOONBAG"
    assert projection["active_level"]["name"] == "ROCKET"
    assert projection["active_level"]["stop_roi"] == 220.0
    assert projection["next_level"]["name"] == "STAR"


@pytest.mark.asyncio
async def test_moonbag_choke_level_closes_gap_before_1200_roi():
    order = {
        "symbol": "OPNUSDT",
        "side": "SELL",
        "entry_price": 0.132,
        "current_stop": 0.0,
        "leverage": 50.0,
        "qty": 100.0,
        "contract_meta": {"tick_size": 0.000001, "ct_val": 1.0, "qty_step": 1.0, "min_qty": 1.0},
    }

    projection = await order_projection_service.build_projection(
        order,
        current_price=0.111318,
        phase_hint="MOONBAG",
        fetch_contract=False,
    )

    assert projection["roi_percent"] == pytest.approx(783.409, abs=0.01)
    assert projection["active_level"]["name"] == "CHOKE_PREP"
    assert projection["active_level"]["stop_roi"] == 600.0
    assert projection["recommended_stop"] == pytest.approx(0.11616)
    assert projection["next_level"]["name"] == "CHOKE"
    assert projection["next_level"]["trigger_roi"] == 800.0
    assert projection["next_level"]["stop_roi"] == 650.0
    assert projection["next_level"]["target_price"] == pytest.approx(0.11088)


@pytest.mark.asyncio
async def test_moonbag_projection_continues_after_1200_roi():
    order = {
        "symbol": "OPNUSDT",
        "side": "SELL",
        "entry_price": 0.132,
        "current_stop": 0.0,
        "leverage": 50.0,
        "qty": 100.0,
        "contract_meta": {"tick_size": 0.000001, "ct_val": 1.0, "qty_step": 1.0, "min_qty": 1.0},
    }

    projection = await order_projection_service.build_projection(
        order,
        current_price=0.08712,
        phase_hint="MOONBAG",
        fetch_contract=False,
    )

    assert projection["roi_percent"] == pytest.approx(1700.0)
    assert projection["active_level"]["name"] == "ULTRA_1600"
    assert projection["active_level"]["stop_roi"] == 1350.0
    assert projection["recommended_stop"] == pytest.approx(0.09636)
    assert projection["next_level"]["name"] == "ULTRA_2000"
    assert projection["next_level"]["trigger_roi"] == 2000.0
