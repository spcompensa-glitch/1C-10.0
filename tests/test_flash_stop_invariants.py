import asyncio
import logging
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.agents.flash_agent import FlashAgent
from services.execution_protocol import execution_protocol
from services.firebase_service import FirebaseService
from services.okx_rest import okx_rest_service


def test_stop_improvement_direction_is_consistent_for_long_and_short():
    flash = FlashAgent()

    assert flash._stop_improves("buy", 100.0, 102.0) is True
    assert flash._stop_improves("buy", 102.0, 100.0) is False
    assert flash._stop_improves("sell", 100.0, 98.0) is True
    assert flash._stop_improves("sell", 98.0, 100.0) is False


def test_profit_stop_rounding_never_reduces_promised_roi():
    flash = FlashAgent()

    long_stop = flash._round_stop_to_tick(0.42520964, 0.0001, "buy", 6.0)
    short_stop = flash._round_stop_to_tick(0.01518176, 0.00001, "sell", 6.0)

    assert long_stop == pytest.approx(0.4253)
    assert short_stop == pytest.approx(0.01518)
    assert flash._calc_roi(0.4247, long_stop, "buy", 50.0) >= 6.0
    assert flash._calc_roi(0.0152, short_stop, "sell", 50.0) >= 6.0


@pytest.mark.asyncio
async def test_paper_close_uses_authoritative_slot_stop(monkeypatch):
    trades = []
    resets = []

    class FakeRedis:
        async def acquire_lock(self, *args, **kwargs):
            return True

        async def release_lock(self, *args, **kwargs):
            return True

    class FakeDatabase:
        async def get_slot(self, slot_id):
            return {"id": slot_id, "symbol": "KAITOUSDT", "current_stop": 0.4252}

        async def get_moonbags(self):
            return []

    class FakeBankroll:
        async def register_sniper_trade(self, trade_data):
            trades.append(trade_data.copy())

    class FakeFirebase:
        async def get_slot(self, slot_id):
            return {"fleet_intel": {}, "unified_confidence": 50, "pensamento": "test"}

        async def hard_reset_slot(self, slot_id, reason="test", pnl=0, trade_data=None):
            resets.append((slot_id, reason, pnl, trade_data.copy()))
            return True

    monkeypatch.setattr(okx_rest_service, "execution_mode", "PAPER")
    monkeypatch.setattr(okx_rest_service, "redis", FakeRedis())
    monkeypatch.setattr(okx_rest_service, "pending_closures", set())
    monkeypatch.setattr(okx_rest_service, "paper_balance", 20.0)
    monkeypatch.setattr(okx_rest_service, "paper_orders_history", [])
    monkeypatch.setattr(okx_rest_service, "paper_moonbags", [])
    monkeypatch.setattr(okx_rest_service, "paper_positions", [{
        "symbol": "KAITOUSDT",
        "side": "Buy",
        "size": "353",
        "avgPrice": "0.4247",
        "leverage": "50",
        "stopLoss": "0.4242",
        "slot_id": 1,
        "opened_at": 1781074725,
    }])

    async def fake_get_instrument_info(symbol):
        return {"lotSizeFilter": {"ctVal": "1"}}

    async def fake_cleanup(symbol, delay=15):
        return None

    monkeypatch.setattr(okx_rest_service, "get_instrument_info", fake_get_instrument_info)
    monkeypatch.setattr(okx_rest_service, "_cleanup_pending_closure", fake_cleanup)
    monkeypatch.setattr("services.database_service.database_service", FakeDatabase())
    monkeypatch.setattr("services.bankroll.bankroll_manager", FakeBankroll())
    monkeypatch.setattr("services.firebase_service.firebase_service", FakeFirebase())

    ok = await okx_rest_service.close_position("KAITOUSDT", "buy", 353, "FLASH_PROFIT_SL_6%")

    assert ok is True
    assert trades[0]["exit_price"] == pytest.approx(0.4252)
    assert resets[0][3]["exit_price"] == pytest.approx(0.4252)
    assert trades[0]["pnl"] > 0


@pytest.mark.asyncio
async def test_hard_reset_preserves_explicit_exit_price(monkeypatch):
    service = FirebaseService()
    captured = []

    async def fake_get_slot(slot_id):
        return {
            "id": slot_id,
            "symbol": "KAITOUSDT",
            "side": "Buy",
            "qty": 353,
            "entry_price": 0.4247,
            "entry_margin": 3.0,
            "current_stop": 0.4252,
            "opened_at": 1781074725,
        }

    async def fake_log_trade(trade_data):
        captured.append(trade_data.copy())

    async def noop(*args, **kwargs):
        return True

    async def no_genesis(*args, **kwargs):
        return {}

    monkeypatch.setattr(service, "get_slot", fake_get_slot)
    monkeypatch.setattr(service, "get_order_genesis", no_genesis)
    monkeypatch.setattr(service, "log_trade", fake_log_trade)
    monkeypatch.setattr(service, "register_sl_cooldown", noop)
    monkeypatch.setattr(service, "update_slot", noop)
    monkeypatch.setattr(service, "log_event", noop)
    service.rtdb = None

    await service._hard_reset_slot_full(
        1,
        reason="PAPER_CLOSE_ATOMIC_FLASH_PROFIT_SL_6%",
        pnl=0.10,
        trade_data={
            "symbol": "KAITOUSDT",
            "side": "Buy",
            "entry_price": 0.4247,
            "exit_price": 0.4252,
            "qty": 353,
            "pnl": 0.10,
            "pnl_percent": 5.89,
            "final_roi": 5.89,
            "order_id": "KAITOUSDT_1781074725",
            "slot_id": 1,
            "entry_margin": 3.0,
            "leverage": 50.0,
        },
    )

    assert captured[0]["exit_price"] == pytest.approx(0.4252)
    assert captured[0]["current_stop_at_close"] == pytest.approx(0.4252)


def test_moonbag_hard_lock_never_drops_below_emancipation():
    flash = FlashAgent()

    assert flash._moonbag_hard_lock_roi({}) == pytest.approx(110.0)
    assert flash._moonbag_hard_lock_roi({"flash_last_stop_roi": 25}) == pytest.approx(110.0)
    assert flash._moonbag_hard_lock_roi({"flash_last_stop_roi": 500}) == pytest.approx(500.0)


def test_flash_slot_tracking_log_exposes_stop_context(caplog):
    flash = FlashAgent()
    caplog.set_level(logging.INFO, logger="FlashAgent")

    projection = {
        "phase": "ESCADINHA",
        "recommended_stop": 0.5029,
        "active_level": {
            "name": "RISCO_ZERO",
            "trigger_roi": 70.0,
            "stop_roi": 45.0,
        },
        "next_level": {
            "name": "PROFIT_LOCK",
            "trigger_roi": 110.0,
            "stop_roi": 80.0,
        },
    }

    flash._log_slot_tracking(
        slot_id=2,
        symbol="WLDUSDT",
        side="sell",
        entry_price=0.5075,
        current_price=0.4968,
        current_stop=0.5252625,
        leverage=50.0,
        roi=105.4,
        effective_roi=105.4,
        projection=projection,
    )

    line = caplog.records[-1].message
    assert "[FLASH-TRACK][SLOT]" in line
    assert "symbol=WLDUSDT" in line
    assert "active=RISCO_ZERO/trigger=70%/stop=45%" in line
    assert "next=PROFIT_LOCK/trigger=110%/stop=80%" in line
    assert "stop_db=" in line
    assert "stop_db_roi=-175.0%" in line
    assert "stop_target=" in line
    assert "stop_target_roi=+45.3%" in line
    assert "action=APPLY_STOP" in line


def test_flash_moonbag_tracking_log_exposes_hard_lock_context(caplog):
    flash = FlashAgent()
    caplog.set_level(logging.INFO, logger="FlashAgent")

    projection = {
        "phase": "MOONBAG",
        "recommended_stop": 0.1056,
        "active_level": {
            "name": "APEX",
            "trigger_roi": 1200.0,
            "stop_roi": 1000.0,
        },
        "next_level": {
            "name": "ULTRA_1400",
            "trigger_roi": 1400.0,
            "stop_roi": 1200.0,
        },
    }

    flash._log_moonbag_tracking(
        moon_uuid="OPNUSDT_1780848528",
        symbol="OPNUSDT",
        side="sell",
        entry_price=0.132,
        current_price=0.0979,
        current_stop=0.1056,
        leverage=50.0,
        roi=1291.7,
        effective_roi=1291.7,
        projection=projection,
        hard_lock_stop=0.1291,
        hard_lock_roi=110.0,
        hard_lock_improves=False,
    )

    line = caplog.records[-1].message
    assert "[FLASH-TRACK][MOONBAG]" in line
    assert "symbol=OPNUSDT" in line
    assert "peak_roi=+1291.7%" in line
    assert "active=APEX/trigger=1200%/stop=1000%" in line
    assert "next=ULTRA_1400/trigger=1400%/stop=1200%" in line
    assert "stop_db=" in line
    assert "stop_db_roi=+1000.0%" in line
    assert "hard_lock=" in line
    assert "hard_lock_roi=+110.0%" in line
    assert "stop_target=" in line
    assert "action=MONITOR" in line


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
async def test_moonbag_close_does_not_remove_when_close_and_forensic_fail(monkeypatch):
    flash = FlashAgent()
    removed = []

    class FakeOkx:
        async def close_position(self, symbol, side, qty, reason):
            return False

    class FakeDatabase:
        async def remove_moonbag(self, moon_uuid):
            removed.append(moon_uuid)
            return True

    async def fake_forensic(*args, **kwargs):
        return False

    monkeypatch.setattr("services.okx_rest.okx_rest_service", FakeOkx())
    monkeypatch.setattr("services.agents.flash_agent.database_service", FakeDatabase())
    monkeypatch.setattr(flash, "_forensic_close_paper_moonbag", fake_forensic)

    await flash._close_moonbag("OPNUSDT_1", "OPNUSDT", "sell", 10, "MOONBAG_TRAIL_SL_1600%")

    assert removed == []


@pytest.mark.asyncio
async def test_forensic_paper_moonbag_close_registers_ledger_and_saves_state(monkeypatch):
    flash = FlashAgent()
    trades = []

    class FakeDatabase:
        async def get_moonbag(self, moon_uuid):
            return {
                "uuid": moon_uuid,
                "symbol": "OPNUSDT",
                "side": "Sell",
                "qty": 113.0,
                "entry_price": 0.132,
                "entry_margin": 3.0,
                "current_stop": 0.0898,
                "leverage": 50.0,
                "opened_at": 1780848528,
                "genesis_id": "SWG-1780848528-OPNU-66067F",
                "flash_last_action": "ULTRA_1800",
                "flash_last_stop_roi": 1600.0,
                "projection": {"contract": {"ct_val": 10.0}},
            }

    class FakeOkx:
        execution_mode = "PAPER"
        paper_balance = 20.0
        paper_moonbags = [{"symbol": "OPNUSDT"}]

        def normalize_symbol(self, symbol):
            return (symbol or "").replace(".P", "").upper()

        async def get_instrument_info(self, symbol):
            return {"lotSizeFilter": {"ctVal": "10"}}

        async def _save_paper_state(self):
            self.saved = True

    class FakeBankroll:
        async def register_sniper_trade(self, trade_data):
            trades.append(trade_data)

    fake_okx = FakeOkx()
    monkeypatch.setattr("services.agents.flash_agent.database_service", FakeDatabase())
    monkeypatch.setattr("services.okx_rest.okx_rest_service", fake_okx)
    monkeypatch.setattr("services.bankroll.bankroll_manager", FakeBankroll())

    ok = await flash._forensic_close_paper_moonbag(
        "OPNUSDT_1780848528", "OPNUSDT", "Sell", 113.0, "MOONBAG_TRAIL_SL_1800%"
    )

    assert ok is True
    assert len(trades) == 1
    assert trades[0]["slot_type"] == "MOONBAG"
    assert trades[0]["close_reason"].startswith("MOONBAG_FORENSIC_CLOSE_")
    assert trades[0]["pnl"] == pytest.approx(
        execution_protocol.calculate_pnl(0.132, 0.0898, 113.0, "Sell", 10.0)
    )
    assert fake_okx.paper_moonbags == []
    assert fake_okx.saved is True


@pytest.mark.asyncio
async def test_moonbag_uses_recent_peak_to_apply_broken_post_apex_stop(monkeypatch):
    flash = FlashAgent()
    updated = []
    checked_stops = []

    moon = {
        "uuid": "OPNUSDT_1780848528",
        "symbol": "OPNUSDT",
        "side": "Sell",
        "qty": 113.0,
        "entry_price": 0.132,
        "current_stop": 0.1056,
        "leverage": 50.0,
        "flash_last_stop_roi": 1000.0,
        "contract_meta": {"tick_size": 0.0001, "ct_val": 10.0, "qty_step": 1.0, "min_qty": 1.0},
    }

    async def fake_get_current_price(symbol):
        assert symbol == "OPNUSDT"
        return 0.0932  # ~1469% ROI: current price already pulled back below the broken peak

    def fake_get_peak_price(symbol, side, current_price):
        assert symbol == "OPNUSDT"
        assert side == "sell"
        return 0.08712  # 1700% ROI: ULTRA_1600 was touched inside the recent WS window

    async def fake_check_stop_hit(side, stop_price, symbol):
        checked_stops.append(stop_price)
        return False

    async def fake_update_moonbag_sl(moon_uuid, symbol, sl_price, roi, flash_action="MOONBAG_TRAIL", stop_roi=None):
        updated.append((moon_uuid, symbol, sl_price, flash_action, stop_roi))

    monkeypatch.setattr(flash, "_get_current_price", fake_get_current_price)
    monkeypatch.setattr(flash, "_get_peak_price", fake_get_peak_price)
    monkeypatch.setattr(flash, "_check_stop_hit", fake_check_stop_hit)
    monkeypatch.setattr(flash, "_update_moonbag_sl", fake_update_moonbag_sl)

    await flash._process_moonbag(moon)

    assert checked_stops == [pytest.approx(0.1056), pytest.approx(0.095)]
    assert updated == [("OPNUSDT_1780848528", "OPNUSDT", pytest.approx(0.095), "ULTRA_1600", 1400.0)]


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

    async def fake_get_rest_price(symbol):
        assert symbol == "ZECUSDT"
        return 0.0

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
    monkeypatch.setattr(flash, "_get_rest_price", fake_get_rest_price)
    monkeypatch.setattr(flash, "_get_peak_price", fake_get_peak_price)
    monkeypatch.setattr(flash, "_check_stop_hit", fake_check_stop_hit)
    monkeypatch.setattr(flash, "_update_slot_sl", fake_update_slot_sl)
    monkeypatch.setattr(flash, "_emancipate_slot", fake_emancipate_slot)
    monkeypatch.setattr(flash, "_update_pnl", lambda *args, **kwargs: None)

    await flash._process_slot(slot)

    assert checked_stops == [pytest.approx(426.24), pytest.approx(431.74)]
    assert updated == [(3, "ZECUSDT", pytest.approx(431.74), "PROFIT_LOCK", "buy", 35.0)]
    assert emancipated == [(3, "ZECUSDT", pytest.approx(431.74))]


@pytest.mark.asyncio
async def test_slot_profit_stop_closes_with_rest_confirmation_when_ws_is_stale(monkeypatch):
    flash = FlashAgent()
    closed = []

    slot = {
        "id": 3,
        "symbol": "ZECUSDT",
        "side": "Buy",
        "qty": 35.0,
        "entry_price": 422.44,
        "current_stop": 426.24,
        "leverage": 50.0,
        "pnl_percent": 27.0,
        "genesis_id": "SWG-1780848505-ZECU-40A404",
        "contract_meta": {"tick_size": 0.01, "ct_val": 0.01, "qty_step": 1.0, "min_qty": 1.0},
    }

    async def fake_get_current_price(symbol):
        assert symbol == "ZECUSDT"
        return 424.75

    async def fake_get_rest_price(symbol):
        assert symbol == "ZECUSDT"
        return 424.75

    async def fake_close_position(slot_id, symbol, side, qty, reason):
        closed.append((slot_id, symbol, side, qty, reason))

    monkeypatch.setattr(flash, "_get_current_price", fake_get_current_price)
    monkeypatch.setattr(flash, "_get_rest_price", fake_get_rest_price)
    monkeypatch.setattr(flash, "_close_position", fake_close_position)
    monkeypatch.setattr(flash, "_update_pnl", lambda *args, **kwargs: None)

    await flash._process_slot(slot)

    assert closed == [(3, "ZECUSDT", "buy", 35.0, "FLASH_PROFIT_SL_27.3%")]


@pytest.mark.asyncio
async def test_check_stop_hit_uses_rest_when_conservative_ws_misses(monkeypatch):
    flash = FlashAgent()

    monkeypatch.setattr(
        "services.agents.flash_agent.okx_ws_public_service.get_conservative_price",
        lambda symbol, side: 430.0,
    )

    async def fake_get_rest_price(symbol):
        assert symbol == "ZECUSDT"
        return 424.75

    monkeypatch.setattr(flash, "_get_rest_price", fake_get_rest_price)

    assert await flash._check_stop_hit("buy", 426.24, "ZECUSDT") is True


@pytest.mark.asyncio
async def test_check_stop_hit_uses_rest_for_short_when_ws_is_stale(monkeypatch):
    flash = FlashAgent()

    monkeypatch.setattr(
        "services.agents.flash_agent.okx_ws_public_service.get_conservative_price",
        lambda symbol, side: 35.88,
    )

    async def fake_get_rest_price(symbol):
        assert symbol == "DASHUSDT.P"
        return 37.03

    monkeypatch.setattr(flash, "_get_rest_price", fake_get_rest_price)

    assert await flash._check_stop_hit("sell", 37.0323, "DASHUSDT.P") is False
    assert await flash._check_stop_hit("sell", 37.03, "DASHUSDT.P") is True


@pytest.mark.asyncio
async def test_get_rest_price_parses_okx_rest_payload(monkeypatch):
    flash = FlashAgent()

    async def fake_get_tickers(symbol=None):
        assert symbol == "DASHUSDT.P"
        return {"retCode": 0, "result": {"list": [{"symbol": "DASHUSDT", "lastPrice": "37.03"}]}}

    monkeypatch.setattr(
        "services.okx_rest.okx_rest_service.get_tickers",
        fake_get_tickers,
    )

    assert await flash._get_rest_price("DASHUSDT.P") == pytest.approx(37.03)
