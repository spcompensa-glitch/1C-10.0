import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.execution_capacity import ExecutionCapacityGate


def _gate() -> ExecutionCapacityGate:
    gate = ExecutionCapacityGate()
    gate.max_spread_bps = 20.0
    gate.max_slippage_bps = 25.0
    gate.max_book_usage_pct = 15.0
    gate.min_fill_ratio = 1.0
    return gate


def test_approves_small_order_on_deep_tight_book():
    gate = _gate()
    report = gate.evaluate_orderbook(
        symbol="BTCUSDT",
        side="Buy",
        qty=10,
        entry_price=100.0,
        leverage=50,
        ct_val=1,
        margin_usd=20,
        execution_mode="REAL",
        orderbook={
            "b": [[99.99, 1000]],
            "a": [[100.01, 1000]],
        },
    )

    assert report["approved"] is True
    assert report["reasons"] == []
    assert report["metrics"]["fill_ratio"] == pytest.approx(1.0)
    assert report["metrics"]["spread_bps"] == pytest.approx(2.0)
    assert report["metrics"]["slippage_bps"] == pytest.approx(1.0)
    assert report["metrics"]["book_usage_pct"] == pytest.approx(1.0)


def test_blocks_order_that_cannot_fill_visible_depth():
    gate = _gate()
    report = gate.evaluate_orderbook(
        symbol="THINUSDT",
        side="Buy",
        qty=150,
        entry_price=100.0,
        leverage=50,
        ct_val=1,
        execution_mode="REAL",
        orderbook={
            "b": [[99.99, 100]],
            "a": [[100.01, 100]],
        },
    )

    assert report["approved"] is False
    assert report["metrics"]["fill_ratio"] == pytest.approx(100 / 150)
    assert any(reason.startswith("FILL_RATIO") for reason in report["reasons"])
    assert any(reason.startswith("BOOK_USAGE") for reason in report["reasons"])


def test_blocks_order_when_estimated_slippage_is_too_high():
    gate = _gate()
    report = gate.evaluate_orderbook(
        symbol="WIDEUSDT",
        side="Buy",
        qty=10,
        entry_price=100.0,
        leverage=50,
        ct_val=1,
        execution_mode="REAL",
        orderbook={
            "b": [[99.99, 100]],
            "a": [[100.50, 100]],
        },
    )

    assert report["approved"] is False
    assert report["metrics"]["slippage_bps"] == pytest.approx(50.0)
    assert any(reason.startswith("SPREAD") for reason in report["reasons"])
    assert any(reason.startswith("SLIPPAGE") for reason in report["reasons"])


def test_sell_order_consumes_bids_for_slippage():
    gate = _gate()
    gate.max_slippage_bps = 15.0
    report = gate.evaluate_orderbook(
        symbol="SHORTUSDT",
        side="Sell",
        qty=20,
        entry_price=100.0,
        leverage=50,
        ct_val=1,
        execution_mode="REAL",
        orderbook={
            "b": [[99.90, 10], [99.70, 10]],
            "a": [[100.01, 1000]],
        },
    )

    assert report["approved"] is False
    assert report["metrics"]["avg_fill_price"] == pytest.approx(99.80)
    assert report["metrics"]["slippage_bps"] == pytest.approx(20.0)
    assert any(reason.startswith("SLIPPAGE") for reason in report["reasons"])


def test_missing_book_bypasses_only_in_paper_mode():
    gate = _gate()

    paper = gate.evaluate_orderbook(
        symbol="APIUSDT",
        side="Buy",
        qty=1,
        entry_price=10,
        leverage=50,
        ct_val=1,
        execution_mode="PAPER",
        orderbook=None,
    )
    real = gate.evaluate_orderbook(
        symbol="APIUSDT",
        side="Buy",
        qty=1,
        entry_price=10,
        leverage=50,
        ct_val=1,
        execution_mode="REAL",
        orderbook=None,
    )

    assert paper["approved"] is True
    assert paper["warnings"] == ["BOOK_UNAVAILABLE_PAPER_BYPASS"]
    assert real["approved"] is False
    assert real["reasons"] == ["BOOK_UNAVAILABLE"]
