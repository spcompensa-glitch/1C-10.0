import logging
import os
from typing import Any, Dict, Optional


logger = logging.getLogger("ExecutionAudit")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


class ExecutionAuditService:
    """Post-order execution audit for latency, fill, slippage, fees and funding."""

    def __init__(self) -> None:
        self.max_slippage_bps = _safe_float(os.getenv("EXEC_AUDIT_MAX_SLIPPAGE_BPS"), 35.0)
        self.max_latency_ms = _safe_float(os.getenv("EXEC_AUDIT_MAX_LATENCY_MS"), 3000.0)
        self.min_fill_ratio = _safe_float(os.getenv("EXEC_AUDIT_MIN_FILL_RATIO"), 0.999)
        self.taker_fee_rate = _safe_float(os.getenv("OKX_TAKER_FEE_RATE"), 0.0005)

    def build_open_order_audit(
        self,
        *,
        symbol: str,
        side: str,
        requested_qty: float,
        expected_price: float,
        ct_val: float,
        leverage: float,
        order_response: Optional[Dict[str, Any]],
        capacity_report: Optional[Dict[str, Any]] = None,
        started_at: float = 0.0,
        completed_at: float = 0.0,
        funding_rate: float = 0.0,
        position_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        side_norm = self._normalize_side(side)
        requested_qty = max(_safe_float(requested_qty), 0.0)
        expected_price = max(_safe_float(expected_price), 0.0)
        ct_val = max(_safe_float(ct_val, 1.0), 1e-12)
        leverage = max(_safe_float(leverage, 1.0), 1.0)
        funding_rate = _safe_float(funding_rate)

        fill = self._extract_fill(order_response, position_snapshot)
        avg_fill_price = fill["avg_fill_price"] or expected_price
        filled_qty = fill["filled_qty"] or requested_qty
        fill_source = fill["fill_source"]

        fill_ratio = filled_qty / requested_qty if requested_qty > 0 else 0.0
        notional_usd = filled_qty * avg_fill_price * ct_val
        margin_usd = notional_usd / leverage if leverage > 0 else 0.0
        fee_usd = notional_usd * self.taker_fee_rate

        if expected_price > 0 and avg_fill_price > 0:
            if side_norm == "BUY":
                slippage_bps = ((avg_fill_price - expected_price) / expected_price) * 10000.0
            else:
                slippage_bps = ((expected_price - avg_fill_price) / expected_price) * 10000.0
        else:
            slippage_bps = 0.0

        funding_cost_usd = notional_usd * funding_rate * (1.0 if side_norm == "BUY" else -1.0)
        latency_ms = max((completed_at - started_at) * 1000.0, 0.0) if completed_at and started_at else 0.0

        capacity_metrics = (capacity_report or {}).get("metrics", {})
        capacity_slippage_bps = capacity_metrics.get("slippage_bps")
        capacity_slippage_bps = (
            _safe_float(capacity_slippage_bps)
            if isinstance(capacity_slippage_bps, (int, float))
            else None
        )

        reasons = []
        warnings = []
        if fill_source == "expected_fallback":
            warnings.append("FILL_CONFIRMATION_UNAVAILABLE")
        if fill_ratio < self.min_fill_ratio:
            reasons.append(f"PARTIAL_FILL {fill_ratio * 100:.2f}% < {self.min_fill_ratio * 100:.2f}%")
        if max(slippage_bps, 0.0) > self.max_slippage_bps:
            reasons.append(f"SLIPPAGE {slippage_bps:.2f}bps > {self.max_slippage_bps:.2f}bps")
        if latency_ms > self.max_latency_ms:
            reasons.append(f"LATENCY {latency_ms:.0f}ms > {self.max_latency_ms:.0f}ms")

        audit = {
            "status": "WARN" if reasons or warnings else "OK",
            "symbol": symbol,
            "side": side_norm,
            "reasons": reasons,
            "warnings": warnings,
            "thresholds": {
                "max_slippage_bps": self.max_slippage_bps,
                "max_latency_ms": self.max_latency_ms,
                "min_fill_ratio": self.min_fill_ratio,
                "taker_fee_rate": self.taker_fee_rate,
            },
            "metrics": {
                "requested_qty": requested_qty,
                "filled_qty": filled_qty,
                "fill_ratio": fill_ratio,
                "expected_price": expected_price,
                "avg_fill_price": avg_fill_price,
                "slippage_bps": slippage_bps,
                "latency_ms": latency_ms,
                "ct_val": ct_val,
                "leverage": leverage,
                "notional_usd": notional_usd,
                "margin_usd": margin_usd,
                "estimated_taker_fee_usd": fee_usd,
                "funding_rate": funding_rate,
                "estimated_funding_cost_usd": funding_cost_usd,
                "capacity_estimated_slippage_bps": capacity_slippage_bps,
                "slippage_delta_vs_capacity_bps": (
                    slippage_bps - capacity_slippage_bps
                    if capacity_slippage_bps is not None
                    else None
                ),
                "fill_source": fill_source,
            },
        }

        msg = (
            f"[EXEC-AUDIT] {symbol} {side_norm} "
            f"fill={fill_ratio * 100:.1f}% avg={avg_fill_price:.8f} "
            f"slippage={slippage_bps:.2f}bps latency={latency_ms:.0f}ms "
            f"fee=${fee_usd:.4f} funding8h=${funding_cost_usd:.4f} "
            f"source={fill_source} status={audit['status']}"
        )
        if audit["status"] == "WARN":
            logger.warning(msg + f" | reasons={reasons} warnings={warnings}")
        else:
            logger.info(msg)

        return audit

    def _extract_fill(
        self,
        order_response: Optional[Dict[str, Any]],
        position_snapshot: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        result = (order_response or {}).get("result", {}) if isinstance(order_response, dict) else {}
        avg_fill_price = self._first_float(
            result,
            ["avgFillPrice", "avgPrice", "avgPx", "fillPx", "price"],
        )
        filled_qty = self._first_float(
            result,
            ["filledQty", "fillSz", "accFillSz", "sz", "size", "qty"],
        )
        if avg_fill_price > 0 and filled_qty > 0:
            return {
                "avg_fill_price": avg_fill_price,
                "filled_qty": filled_qty,
                "fill_source": "order_response",
            }

        position_snapshot = position_snapshot or {}
        avg_fill_price = self._first_float(position_snapshot, ["avgPrice", "avgPx", "entry_price"])
        filled_qty = self._first_float(position_snapshot, ["size", "pos", "qty"])
        if avg_fill_price > 0 and filled_qty > 0:
            return {
                "avg_fill_price": avg_fill_price,
                "filled_qty": filled_qty,
                "fill_source": "position_snapshot",
            }

        return {
            "avg_fill_price": 0.0,
            "filled_qty": 0.0,
            "fill_source": "expected_fallback",
        }

    def _first_float(self, payload: Dict[str, Any], keys) -> float:
        for key in keys:
            value = _safe_float(payload.get(key), 0.0)
            if value > 0:
                return value
        return 0.0

    def _normalize_side(self, side: str) -> str:
        side_norm = (side or "").strip().lower()
        return "BUY" if side_norm in {"buy", "long"} else "SELL"


execution_audit_service = ExecutionAuditService()
