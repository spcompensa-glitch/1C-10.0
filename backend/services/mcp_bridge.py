# -*- coding: utf-8 -*-
"""
MCP Bridge for 10D-Bybit (Elite Sniper V16.0)
Exposes core trading logic to the AIOS ecosystem via standard MCP Tools.
"""
import logging
import asyncio
from mcp.server.fastmcp import FastMCP

# Core Service Imports
from services.okx_rest import okx_rest_service
from services.bankroll import bankroll_manager
from services.firebase_service import firebase_service

# Setup logging
logger = logging.getLogger("MCPBridge")

# Initialize FastMCP Server
# "10D-Bybit" will be the name of the tool collection in the AIOS registry
mcp = FastMCP("10D-Bybit")

# ---------------------------------------------------------
# ACCOUNT & SYSTEM TOOLS
# ---------------------------------------------------------

@mcp.tool()
async def get_balance():
    """
    Fetches the total wallet balance (Equity) from the Bybit account.
    Returns the balance as a float value.
    """
    try:
        balance = await okx_rest_service.get_wallet_balance()
        return {"status": "success", "balance": balance}
    except Exception as e:
        return {"status": "error", "message": f"Failed to fetch balance: {str(e)}"}

@mcp.tool()
async def get_positions():
    """
    Lists all currently active trading positions.
    Returns a list of positions with their respective symbols, sides, and PnL.
    """
    try:
        positions = await okx_rest_service.get_active_positions()
        return {"status": "success", "positions": positions}
    except Exception as e:
        return {"status": "error", "message": f"Failed to fetch positions: {str(e)}"}

# ---------------------------------------------------------
# EXECUTION TOOLS
# ---------------------------------------------------------

@mcp.tool()
async def close_position(symbol: str, side: str, qty: float):
    """
    Closes a specific trading position at market price.
    - symbol: e.g., 'BTCUSDT' (or '1000PEPEUSDT')
    - side: 'Buy' to close a Short, 'Sell' to close a Long.
    - qty: The quantity to close.
    """
    try:
        success = await okx_rest_service.close_position(symbol, side, qty)
        return {"status": "success" if success else "failed", "symbol": symbol}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def open_sniper(symbol: str, side: str, sl_price: float, tp_price: float = None):
    """
    Executes a new trade using the Elite Sniper Protocol.
    This includes bankroll volume calculation and slot management.
    - symbol: The pair to trade.
    - side: 'Buy' (Long) or 'Sell' (Short).
    - sl_price: The hard stop loss price.
    - tp_price: Optional take profit price.
    """
    try:
        result = await bankroll_manager.open_position(
            symbol=symbol,
            side=side,
            sl_price=sl_price,
            tp_price=tp_price,
            pensamento="Triggered via AIOS MCP Bridge"
        )
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def emergency_stop_all():
    """
    PANIC BUTTON: Closes all open positions and cancels all pending orders immediately.
    """
    try:
        await bankroll_manager.emergency_close_all()
        return {"status": "success", "message": "All positions closed successfully."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ---------------------------------------------------------
# INTELLIGENCE TOOLS
# ---------------------------------------------------------

@mcp.tool()
async def get_system_snapshot():
    """
    Fetches a high-level snapshot of the system state, including BTC Pulse,
    active signals, and API health.
    """
    try:
        # We can leverage existing Captain logic if available
        from services.agents.captain import captain_agent
        snapshot = await captain_agent._get_system_snapshot()
        return {"status": "success", "snapshot": snapshot}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# O servidor MCP agora é exportado de forma nativa e montado no main.py 
# para compartilhar a mesma porta e processo, eliminando a falha de threads.
