import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.order_projection_service import order_projection_service


BASE_CONTRACT = {"tick_size": 0.01, "ct_val": 0.1, "qty_step": 1.0, "min_qty": 1.0}


@pytest.mark.asyncio
async def test_trending_order_does_not_emancipate_at_150_roi():
    order = {
        "symbol": "ZECUSDT",
        "side": "BUY",
        "entry_price": 100.0,
        "current_stop": 0.0,
        "leverage": 50.0,
        "qty": 10.0,
        "contract_meta": BASE_CONTRACT,
    }

    projection = await order_projection_service.build_projection(
        order,
        current_price=103.0,
        phase_hint="SLOT",
        fetch_contract=False,
        is_ranging=False,
    )

    assert projection["roi_percent"] == pytest.approx(150.0)
    assert projection["phase"] == "TRAILING"
    assert projection["active_level"]["name"] == "ALVO_150"
    assert projection["active_level"]["stop_roi"] == 110.0
    assert projection["recommended_stop"] == pytest.approx(102.2)
    assert projection["next_level"]["name"] == "WAVE"
    assert projection["should_emancipate"] is False


@pytest.mark.asyncio
async def test_short_order_uses_same_ladder_without_container_change():
    order = {
        "symbol": "ZECUSDT",
        "side": "SELL",
        "entry_price": 100.0,
        "current_stop": 0.0,
        "leverage": 50.0,
        "qty": 10.0,
        "contract_meta": BASE_CONTRACT,
    }

    projection = await order_projection_service.build_projection(
        order,
        current_price=97.0,
        phase_hint="SLOT",
        fetch_contract=False,
        is_ranging=False,
    )

    assert projection["roi_percent"] == pytest.approx(150.0)
    assert projection["phase"] == "TRAILING"
    assert projection["recommended_stop"] == pytest.approx(97.8)
    assert projection["active_level"]["phase"] == "TRAILING"
    assert projection["should_emancipate"] is False


@pytest.mark.asyncio
async def test_ranging_ladder_protects_earlier_than_trending():
    order = {
        "symbol": "SOLUSDT",
        "side": "BUY",
        "entry_price": 100.0,
        "current_stop": 0.0,
        "leverage": 50.0,
        "qty": 10.0,
        "contract_meta": BASE_CONTRACT,
    }

    ranging = await order_projection_service.build_projection(
        order,
        current_price=101.4,
        phase_hint="SLOT",
        fetch_contract=False,
        is_ranging=True,
    )
    trending = await order_projection_service.build_projection(
        order,
        current_price=101.4,
        phase_hint="SLOT",
        fetch_contract=False,
        is_ranging=False,
    )

    assert ranging["roi_percent"] == pytest.approx(70.0)
    # [V127.2] Dynamic trailing levels extend above static ladder; at ROI 70%,
    # TRAIL_70 (trigger=70, stop=68) is active with ranging adaptation (stop_roi = roi - 2)
    assert ranging["active_level"]["name"] == "TRAIL_70"
    assert ranging["active_level"]["stop_roi"] == 68.0
    assert trending["active_level"]["name"] == "LUCRO_MEDIO"
    assert trending["active_level"]["stop_roi"] == 40.0


@pytest.mark.asyncio
async def test_projection_continues_after_apex_on_same_order():
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
        phase_hint="SLOT",
        fetch_contract=False,
        is_ranging=False,
    )

    assert projection["roi_percent"] == pytest.approx(1700.0)
    assert projection["phase"] == "TRAILING"
    assert projection["active_level"]["name"] == "ULTRA_1600"
    assert projection["active_level"]["stop_roi"] == 1400.0
    assert projection["recommended_stop"] == pytest.approx(0.09504)
    assert projection["next_level"]["name"] == "ULTRA_1800"
