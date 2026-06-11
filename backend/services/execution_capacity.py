import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from config import settings


logger = logging.getLogger("ExecutionCapacityGate")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


class ExecutionCapacityGate:
    """
    Pre-trade liquidity gate.

    It estimates whether the desired contract quantity can be absorbed by the
    visible OKX book before the Captain sends an order.
    """

    def __init__(self) -> None:
        self.max_spread_bps = _safe_float(os.getenv("EXEC_CAPACITY_MAX_SPREAD_BPS"), 20.0)
        self.max_slippage_bps = _safe_float(os.getenv("EXEC_CAPACITY_MAX_SLIPPAGE_BPS"), 25.0)
        self.max_book_usage_pct = _safe_float(os.getenv("EXEC_CAPACITY_MAX_BOOK_USAGE_PCT"), 15.0)
        self.min_fill_ratio = _safe_float(os.getenv("EXEC_CAPACITY_MIN_FILL_RATIO"), 1.0)
        self.orderbook_limit = int(_safe_float(os.getenv("EXEC_CAPACITY_ORDERBOOK_LIMIT"), 50.0))

    def _normalize_side(self, side: str) -> str:
        side_norm = (side or "").strip().lower()
        if side_norm in {"buy", "long"}:
            return "BUY"
        if side_norm in {"sell", "short"}:
            return "SELL"
        return "BUY" if side_norm.startswith("b") or side_norm.startswith("l") else "SELL"

    def _clean_levels(self, levels: List[List[Any]]) -> List[Tuple[float, float]]:
        clean: List[Tuple[float, float]] = []
        for level in levels or []:
            if len(level) < 2:
                continue
            price = _safe_float(level[0])
            size = _safe_float(level[1])
            if price > 0 and size > 0:
                clean.append((price, size))
        return clean

    def _select_book_side(self, orderbook: Dict[str, Any], side: str) -> List[Tuple[float, float]]:
        if side == "BUY":
            return self._clean_levels(orderbook.get("a") or orderbook.get("asks") or [])
        return self._clean_levels(orderbook.get("b") or orderbook.get("bids") or [])

    def _best_prices(self, orderbook: Dict[str, Any]) -> Tuple[float, float, float, float]:
        bids = self._clean_levels(orderbook.get("b") or orderbook.get("bids") or [])
        asks = self._clean_levels(orderbook.get("a") or orderbook.get("asks") or [])
        best_bid = bids[0][0] if bids else 0.0
        best_ask = asks[0][0] if asks else 0.0
        mid = (best_bid + best_ask) / 2.0 if best_bid > 0 and best_ask > 0 else 0.0
        spread_bps = ((best_ask - best_bid) / mid) * 10000.0 if mid > 0 else 0.0
        return best_bid, best_ask, mid, spread_bps

    def _simulate_fill(
        self,
        levels: List[Tuple[float, float]],
        qty: float,
        ct_val: float,
        entry_price: float,
        side: str,
    ) -> Dict[str, float]:
        remaining = max(qty, 0.0)
        filled_qty = 0.0
        filled_notional = 0.0

        for price, level_qty in levels:
            if remaining <= 0:
                break
            take_qty = min(remaining, level_qty)
            filled_qty += take_qty
            filled_notional += take_qty * price * ct_val
            remaining -= take_qty

        avg_fill_price = (
            filled_notional / (filled_qty * ct_val)
            if filled_qty > 0 and ct_val > 0
            else 0.0
        )
        fill_ratio = filled_qty / qty if qty > 0 else 0.0

        if avg_fill_price > 0 and entry_price > 0:
            if side == "BUY":
                slippage_bps = ((avg_fill_price - entry_price) / entry_price) * 10000.0
            else:
                slippage_bps = ((entry_price - avg_fill_price) / entry_price) * 10000.0
        else:
            slippage_bps = 0.0

        return {
            "filled_qty": filled_qty,
            "filled_notional_usd": filled_notional,
            "avg_fill_price": avg_fill_price,
            "fill_ratio": fill_ratio,
            "slippage_bps": max(slippage_bps, 0.0),
        }

    def _estimate_max_safe_qty(
        self,
        levels: List[Tuple[float, float]],
        ct_val: float,
        entry_price: float,
        side: str,
    ) -> Tuple[float, float]:
        safe_qty = 0.0
        safe_notional = 0.0
        filled_qty = 0.0
        filled_notional = 0.0

        for price, level_qty in levels:
            candidate_qty = filled_qty + level_qty
            candidate_notional = filled_notional + (level_qty * price * ct_val)
            avg_price = (
                candidate_notional / (candidate_qty * ct_val)
                if candidate_qty > 0 and ct_val > 0
                else 0.0
            )
            if side == "BUY":
                slip = ((avg_price - entry_price) / entry_price) * 10000.0 if entry_price > 0 else 0.0
            else:
                slip = ((entry_price - avg_price) / entry_price) * 10000.0 if entry_price > 0 else 0.0

            if max(slip, 0.0) > self.max_slippage_bps:
                break

            filled_qty = candidate_qty
            filled_notional = candidate_notional
            safe_qty = candidate_qty
            safe_notional = candidate_notional

        return safe_qty, safe_notional

    def evaluate_orderbook(
        self,
        *,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        leverage: float,
        ct_val: float,
        margin_usd: float = 0.0,
        orderbook: Optional[Dict[str, Any]] = None,
        execution_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        mode = (execution_mode or settings.OKX_EXECUTION_MODE or "PAPER").upper()
        side_norm = self._normalize_side(side)
        qty = max(_safe_float(qty), 0.0)
        entry_price = max(_safe_float(entry_price), 0.0)
        leverage = max(_safe_float(leverage), 1.0)
        ct_val = max(_safe_float(ct_val, 1.0), 1e-12)
        margin_usd = _safe_float(margin_usd)

        if not orderbook or not (orderbook.get("b") or orderbook.get("bids")) or not (orderbook.get("a") or orderbook.get("asks")):
            approved = mode == "PAPER"
            reason = "BOOK_UNAVAILABLE"
            return {
                "approved": approved,
                "reasons": [] if approved else [reason],
                "warnings": [f"{reason}_PAPER_BYPASS"] if approved else [],
                "symbol": symbol,
                "side": side_norm,
                "mode": mode,
                "thresholds": self.thresholds(),
                "metrics": {
                    "qty": qty,
                    "entry_price": entry_price,
                    "ct_val": ct_val,
                    "leverage": leverage,
                    "margin_usd": margin_usd,
                    "notional_usd": qty * entry_price * ct_val,
                    "spread_bps": None,
                    "slippage_bps": None,
                    "fill_ratio": 0.0,
                    "book_usage_pct": None,
                },
            }

        levels = self._select_book_side(orderbook, side_norm)
        best_bid, best_ask, mid_price, spread_bps = self._best_prices(orderbook)
        visible_depth_qty = sum(level_qty for _, level_qty in levels)
        visible_depth_notional = sum(price * level_qty * ct_val for price, level_qty in levels)
        fill = self._simulate_fill(levels, qty, ct_val, entry_price, side_norm)
        book_usage_pct = (qty / visible_depth_qty) * 100.0 if visible_depth_qty > 0 else 100.0
        max_safe_qty, max_safe_notional = self._estimate_max_safe_qty(
            levels, ct_val, entry_price, side_norm
        )

        reasons: List[str] = []
        warnings: List[str] = []

        if fill["fill_ratio"] < self.min_fill_ratio:
            reasons.append(
                f"FILL_RATIO {fill['fill_ratio'] * 100:.2f}% < {self.min_fill_ratio * 100:.2f}%"
            )
        if spread_bps > self.max_spread_bps:
            reasons.append(f"SPREAD {spread_bps:.2f}bps > {self.max_spread_bps:.2f}bps")
        if fill["slippage_bps"] > self.max_slippage_bps:
            reasons.append(
                f"SLIPPAGE {fill['slippage_bps']:.2f}bps > {self.max_slippage_bps:.2f}bps"
            )
        if book_usage_pct > self.max_book_usage_pct:
            reasons.append(
                f"BOOK_USAGE {book_usage_pct:.2f}% > {self.max_book_usage_pct:.2f}%"
            )

        if max_safe_qty < qty:
            warnings.append(
                f"MAX_SAFE_QTY {max_safe_qty:.8f} < REQUESTED_QTY {qty:.8f}"
            )

        metrics = {
            "qty": qty,
            "entry_price": entry_price,
            "ct_val": ct_val,
            "leverage": leverage,
            "margin_usd": margin_usd,
            "notional_usd": qty * entry_price * ct_val,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": mid_price,
            "spread_bps": spread_bps,
            "visible_depth_qty": visible_depth_qty,
            "visible_depth_notional_usd": visible_depth_notional,
            "book_usage_pct": book_usage_pct,
            "filled_qty": fill["filled_qty"],
            "filled_notional_usd": fill["filled_notional_usd"],
            "avg_fill_price": fill["avg_fill_price"],
            "fill_ratio": fill["fill_ratio"],
            "slippage_bps": fill["slippage_bps"],
            "max_safe_qty": max_safe_qty,
            "max_safe_notional_usd": max_safe_notional,
        }

        return {
            "approved": not reasons,
            "reasons": reasons,
            "warnings": warnings,
            "symbol": symbol,
            "side": side_norm,
            "mode": mode,
            "thresholds": self.thresholds(),
            "metrics": metrics,
        }

    async def evaluate_order_capacity(
        self,
        *,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        leverage: float,
        ct_val: float,
        margin_usd: float = 0.0,
        orderbook: Optional[Dict[str, Any]] = None,
        execution_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        if orderbook is None:
            try:
                from services.okx_rest import okx_rest_service

                orderbook = await okx_rest_service.get_orderbook(
                    symbol, limit=self.orderbook_limit
                )
            except Exception as exc:
                logger.warning("[EXEC-CAPACITY-GATE] orderbook fetch failed for %s: %s", symbol, exc)
                orderbook = None

        return self.evaluate_orderbook(
            symbol=symbol,
            side=side,
            qty=qty,
            entry_price=entry_price,
            leverage=leverage,
            ct_val=ct_val,
            margin_usd=margin_usd,
            orderbook=orderbook,
            execution_mode=execution_mode,
        )

    def thresholds(self) -> Dict[str, float]:
        return {
            "max_spread_bps": self.max_spread_bps,
            "max_slippage_bps": self.max_slippage_bps,
            "max_book_usage_pct": self.max_book_usage_pct,
            "min_fill_ratio": self.min_fill_ratio,
            "orderbook_limit": float(self.orderbook_limit),
        }

    async def check_slippage_with_fallback(
        self,
        *,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        leverage: float,
        ct_val: float,
        margin_usd: float = 0.0,
        execution_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        [ECC llm-trading-agent-security] Analisa o livro de ofertas L2 e verifica
        se o slippage projetado é > 0.2% (20bps).

        Retorna:
          - use_post_only: True se deve usar Limit Post-Only
          - adjusted_qty: quantidade reduzida se necessário
          - slippage_pct: slippage percentual calculado
          - recommendation: 'MARKET' | 'POST_ONLY' | 'REDUCE_QTY'
        """
        SLIPPAGE_POST_ONLY_THRESHOLD_PCT = 0.002   # 0.2% = 20bps
        SLIPPAGE_POST_ONLY_THRESHOLD_BPS = 20.0

        result = {
            "use_post_only": False,
            "adjusted_qty": qty,
            "slippage_pct": 0.0,
            "slippage_bps": 0.0,
            "recommendation": "MARKET",
            "reason": "L2_BOOK_OK",
        }

        try:
            from services.okx_rest import okx_rest_service
            orderbook = await okx_rest_service.get_orderbook(symbol, limit=self.orderbook_limit)
        except Exception as exc:
            logger.warning("[SLIPPAGE-L2] Falha ao obter livro de ofertas para %s: %s", symbol, exc)
            return result

        if not orderbook:
            return result

        side_norm = self._normalize_side(side)
        levels = self._select_book_side(orderbook, side_norm)

        if not levels:
            return result

        fill = self._simulate_fill(levels, qty, ct_val, entry_price, side_norm)
        slippage_bps = fill.get("slippage_bps", 0.0)
        slippage_pct = slippage_bps / 10000.0

        result["slippage_pct"] = round(slippage_pct * 100, 4)  # em %
        result["slippage_bps"] = round(slippage_bps, 2)

        if slippage_bps > SLIPPAGE_POST_ONLY_THRESHOLD_BPS:
            # Calcula a quantidade máxima que seria executável dentro do threshold
            max_safe_qty, _ = self._estimate_max_safe_qty(levels, ct_val, entry_price, side_norm)

            if max_safe_qty > 0 and max_safe_qty < qty:
                result["adjusted_qty"] = max_safe_qty
                result["recommendation"] = "REDUCE_QTY"
                result["use_post_only"] = False
                result["reason"] = (
                    f"SLIPPAGE_REDUZ_QTY: {slippage_pct*100:.3f}% > {SLIPPAGE_POST_ONLY_THRESHOLD_PCT*100:.1f}% | "
                    f"qty_original={qty:.4f} ajustada para {max_safe_qty:.4f}"
                )
                logger.warning(
                    "[SLIPPAGE-L2] %s %s slippage=%.2fbps > %.0fbps. Reduzindo qty: %.4f→%.4f",
                    symbol, side_norm, slippage_bps, SLIPPAGE_POST_ONLY_THRESHOLD_BPS, qty, max_safe_qty
                )
            else:
                # Livro muito raso — converter para Limit Post-Only
                result["use_post_only"] = True
                result["recommendation"] = "POST_ONLY"
                result["reason"] = (
                    f"SLIPPAGE_POST_ONLY: {slippage_pct*100:.3f}% > {SLIPPAGE_POST_ONLY_THRESHOLD_PCT*100:.1f}% | "
                    f"Livro L2 raso para {symbol}. Convertendo para Limit Post-Only."
                )
                logger.warning(
                    "[SLIPPAGE-L2] %s %s slippage=%.2fbps > %.0fbps. Livro raso → POST-ONLY.",
                    symbol, side_norm, slippage_bps, SLIPPAGE_POST_ONLY_THRESHOLD_BPS
                )
        else:
            result["reason"] = (
                f"SLIPPAGE_OK: {slippage_pct*100:.3f}% <= {SLIPPAGE_POST_ONLY_THRESHOLD_PCT*100:.1f}%"
            )

        return result


execution_capacity_gate = ExecutionCapacityGate()

