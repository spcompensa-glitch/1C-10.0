import logging
import time
import math
import asyncio
from typing import Dict, Any, List

from services.agents.aios_adapter import AIOSAgent
from services.firebase_service import firebase_service
from services.okx_service import okx_service
from services.okx_ws_public import okx_ws_public_service

logger = logging.getLogger("ExecutionAuditor")

class ExecutionAuditorAgent(AIOSAgent):
    """
    [V124.4] ExecutionAuditorAgent (Sentinel)
    Masters OKX contract specs constraints, sanitizes raw signals,
    calculates precise order sizes, and alerts Firebase of any system failures.
    """
    def __init__(self):
        super().__init__(
            agent_id="execution_auditor_sentinel",
            role="execution_auditor",
            capabilities=["signal_sanitization", "order_validation", "okx_contract_intelligence", "health_reporting"]
        )
        self._contract_details_cache: Dict[str, Dict[str, Any]] = {}

    async def on_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """AIOS adapter incoming messages handler."""
        try:
            msg_type = message.get("type")
            data = message.get("data", {})
            if msg_type == "SANITIZE_SIGNAL":
                result = await self.sanitize_signal(data)
                return {"status": "SUCCESS", "data": result}
            elif msg_type == "VALIDATE_ORDER":
                result = await self.validate_order(
                    symbol=data.get("symbol"),
                    direction=data.get("direction"),
                    entry_price=data.get("entry_price"),
                    stop_price=data.get("stop_price"),
                    balance=data.get("balance"),
                    leverage=data.get("leverage", 50.0)
                )
                return {"status": "SUCCESS", "data": result}
            return {"status": "ERROR", "message": f"Unknown message type: {msg_type}"}
        except Exception as e:
            logger.error(f"ExecutionAuditor on_message Error: {e}")
            return {"status": "ERROR", "message": str(e)}

    async def sanitize_signal(self, raw_signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitizes raw incoming signals (e.g. from TradingView or webhooks)
        mapping various key configurations into a standardized format.
        """
        symbol = raw_signal.get("symbol", "").upper().strip()
        direction = raw_signal.get("direction", "").upper().strip()
        
        # Mapping variants of direction (LONG/BUY -> LONG)
        if direction in ["BUY", "LONG"]:
            direction = "LONG"
        elif direction in ["SELL", "SHORT"]:
            direction = "SHORT"

        # Mapping variations of price keys
        entry_price = float(
            raw_signal.get("price") or 
            raw_signal.get("entry_price") or 
            raw_signal.get("entry_price_signal") or 
            raw_signal.get("currentPrice") or 
            0.0
        )

        # Fallback to current WebSocket price if still 0
        if entry_price <= 0.0 and symbol:
            try:
                entry_price = okx_ws_public_service.get_current_price(symbol)
                if entry_price <= 0.0:
                    # Sync topics and fallback to REST price if WS not available yet
                    from services.okx_rest import okx_rest_service
                    ticker = await okx_rest_service.get_tickers(symbol=symbol)
                    ticker_list = ticker.get("result", {}).get("list", [{}])
                    entry_price = float(ticker_list[0].get("lastPrice", 0))
            except Exception as pe:
                logger.debug(f"[SENTINEL] Fallback price fetch error for {symbol}: {pe}")
                entry_price = 0.0

        # Standardizing Stop Loss
        stop_price = float(
            raw_signal.get("stop_loss") or 
            raw_signal.get("stop_price") or 
            raw_signal.get("sl") or 
            0.0
        )

        return {
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_price,
            "stop_price": stop_price,
            "strategy": raw_signal.get("strategy", "UNKNOWN"),
            "valid": bool(symbol and direction and entry_price > 0.0)
        }

    async def validate_order(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_price: float,
        balance: float,
        leverage: float = 50.0
    ) -> Dict[str, Any]:
        """
        Mastering OKX contract specs: fetches details, calculates correct quantities,
        verifies margin requirements, and pre-checks for failures.
        """
        if not symbol or entry_price <= 0.0:
            return {"valid": False, "reason": f"Dados inválidos: symbol={symbol}, entry={entry_price}"}

        try:
            # 1. Fetch OKX Contract Specs
            details = await okx_service.get_instrument_details(symbol)
            ct_val = float(details.get("ctVal", "1.0"))
            lot_size = float(details.get("lotSize", "1.0"))
            min_sz = float(details.get("minSz", "1.0"))
            tick_size = float(details.get("tickSize", "0.01"))
            
            # 2. Calculate Margins and Slots (Allocating 40% of balance divided across 16 slots)
            raw_margin = (balance * 0.40) / 16.0
            margin = max(0.50, min(1.00, round(raw_margin, 2)))
            
            # 3. Calculate Quantity based on contract sizing
            raw_qty = (margin * leverage) / (entry_price * ct_val)
            qty = float(math.floor(raw_qty / lot_size) * lot_size)
            
            # Bound quantity to minimum size
            is_min_sz_adjusted = False
            if qty < min_sz:
                qty = min_sz
                is_min_sz_adjusted = True

            # Round Stop Loss to nearest OKX tickSize
            rounded_sl = stop_price
            if tick_size > 0:
                rounded_sl = round(stop_price / tick_size) * tick_size

            # 4. Calculate actual margin required by OKX for this quantity
            actual_notional = qty * entry_price * ct_val
            actual_margin_required = actual_notional / leverage
            
            # 5. Verify against available balance
            if actual_margin_required > balance:
                reason = f"Margem real necessária (${actual_margin_required:.2f}) excede o saldo (${balance:.2f}) para {symbol}."
                await self.report_health_alert(symbol, "ORDER_MARGIN_LIMIT", reason)
                return {"valid": False, "reason": reason}

            return {
                "valid": True,
                "qty": qty,
                "margin": margin,
                "actual_margin": actual_margin_required,
                "notional": actual_notional,
                "sl_price": rounded_sl,
                "is_min_sz_adjusted": is_min_sz_adjusted,
                "details": {
                    "ctVal": ct_val,
                    "lotSize": lot_size,
                    "minSz": min_sz,
                    "tickSize": tick_size
                }
            }
        except Exception as err:
            reason = f"Erro ao auditar limites OKX para {symbol}: {err}"
            logger.error(f"❌ [SENTINEL-AUDIT-ERROR] {reason}", exc_info=True)
            await self.report_health_alert(symbol, "AUDIT_EXCEPTION", reason)
            return {"valid": False, "reason": reason}

    async def report_health_alert(self, symbol: str, action: str, error_msg: str):
        """Reports a system health warning or failure directly to Firebase Realtime Database."""
        logger.warning(f"🚨 [SENTINEL-ALERT] Symbol={symbol} | Action={action} | Error={error_msg}")
        try:
            if firebase_service.is_active and firebase_service.rtdb:
                alert_data = {
                    "symbol": symbol,
                    "action": action,
                    "error_msg": error_msg,
                    "timestamp": time.time(),
                    "date": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                # Pushes the alert to /system_health/alerts
                await asyncio.to_thread(
                    firebase_service.rtdb.child("system_health").child("alerts").push,
                    alert_data
                )
        except Exception as e:
            logger.error(f"Failed to submit Sentinel alert to Firebase: {e}")

# Instantiate the Sentinel Agent globally
execution_auditor_agent = ExecutionAuditorAgent()
