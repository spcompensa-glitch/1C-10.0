import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.execution_audit import ExecutionAuditService
from services.database_service import Slot


def _service() -> ExecutionAuditService:
    service = ExecutionAuditService()
    service.max_slippage_bps = 35.0
    service.max_latency_ms = 3000.0
    service.min_fill_ratio = 0.999
    service.taker_fee_rate = 0.0005
    return service


def test_buy_execution_audit_calculates_slippage_fee_and_funding():
    audit = _service().build_open_order_audit(
        symbol="BTCUSDT",
        side="Buy",
        requested_qty=10,
        expected_price=100.0,
        ct_val=1,
        leverage=50,
        order_response={"result": {"avgPrice": "100.10", "filledQty": "10"}},
        capacity_report={"metrics": {"slippage_bps": 5.0}},
        started_at=100.0,
        completed_at=100.2,
        funding_rate=0.0001,
    )

    metrics = audit["metrics"]
    assert audit["status"] == "OK"
    assert metrics["slippage_bps"] == pytest.approx(10.0)
    assert metrics["estimated_taker_fee_usd"] == pytest.approx(0.5005)
    assert metrics["estimated_funding_cost_usd"] == pytest.approx(0.1001)
    assert metrics["slippage_delta_vs_capacity_bps"] == pytest.approx(5.0)
    assert metrics["latency_ms"] == pytest.approx(200.0)


def test_sell_execution_audit_calculates_short_slippage_direction():
    audit = _service().build_open_order_audit(
        symbol="ETHUSDT",
        side="Sell",
        requested_qty=5,
        expected_price=100.0,
        ct_val=1,
        leverage=50,
        order_response={"result": {"avgPrice": "99.80", "filledQty": "5"}},
        started_at=10.0,
        completed_at=10.5,
        funding_rate=0.0002,
    )

    assert audit["status"] == "OK"
    assert audit["metrics"]["slippage_bps"] == pytest.approx(20.0)
    assert audit["metrics"]["estimated_funding_cost_usd"] == pytest.approx(-0.0998)


def test_partial_fill_is_warned():
    audit = _service().build_open_order_audit(
        symbol="THINUSDT",
        side="Buy",
        requested_qty=100,
        expected_price=10.0,
        ct_val=1,
        leverage=50,
        order_response={"result": {"avgPrice": "10.0", "filledQty": "80"}},
    )

    assert audit["status"] == "WARN"
    assert audit["metrics"]["fill_ratio"] == pytest.approx(0.8)
    assert any(reason.startswith("PARTIAL_FILL") for reason in audit["reasons"])


def test_latency_above_threshold_is_warned():
    audit = _service().build_open_order_audit(
        symbol="SLOWUSDT",
        side="Buy",
        requested_qty=1,
        expected_price=10.0,
        ct_val=1,
        leverage=50,
        order_response={"result": {"avgPrice": "10.0", "filledQty": "1"}},
        started_at=10.0,
        completed_at=14.0,
    )

    assert audit["status"] == "WARN"
    assert any(reason.startswith("LATENCY") for reason in audit["reasons"])


def test_position_snapshot_confirms_fill_when_order_response_has_no_average():
    audit = _service().build_open_order_audit(
        symbol="REALUSDT",
        side="Buy",
        requested_qty=3,
        expected_price=20.0,
        ct_val=2,
        leverage=50,
        order_response={"result": {"orderId": "abc"}},
        position_snapshot={"avgPrice": "20.05", "size": "3"},
    )

    assert audit["status"] == "OK"
    assert audit["metrics"]["fill_source"] == "position_snapshot"
    assert audit["metrics"]["notional_usd"] == pytest.approx(120.3)
    assert audit["metrics"]["slippage_bps"] == pytest.approx(25.0)


def test_missing_fill_confirmation_warns_but_uses_expected_price():
    audit = _service().build_open_order_audit(
        symbol="UNKNOWNUSDT",
        side="Buy",
        requested_qty=2,
        expected_price=10.0,
        ct_val=1,
        leverage=50,
        order_response={"result": {"orderId": "abc"}},
    )

    assert audit["status"] == "WARN"
    assert audit["warnings"] == ["FILL_CONFIRMATION_UNAVAILABLE"]
    assert audit["metrics"]["avg_fill_price"] == pytest.approx(10.0)
    assert audit["metrics"]["filled_qty"] == pytest.approx(2.0)


def test_slot_model_persists_execution_audit_json():
    assert "execution_audit" in Slot.__table__.columns
