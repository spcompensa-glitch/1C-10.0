import asyncio
import sys
sys.path.append("backend")

from services.agents.execution_auditor import execution_auditor_agent

async def main():
    print("Testing ExecutionAuditorAgent sanitization...")
    # Signal with entry_price_signal instead of price
    raw_sig = {
        "symbol": "ADA-USDT-SWAP",
        "direction": "buy",
        "entry_price_signal": 0.1812,
        "stop_price": 0.1750,
        "strategy": "DECOR SHADOW"
    }
    
    sanitized = await execution_auditor_agent.sanitize_signal(raw_sig)
    print("Sanitized Signal:", sanitized)
    assert sanitized["entry_price"] == 0.1812
    assert sanitized["direction"] == "LONG"
    print("Sanitization OK!")

    print("\nTesting order validation for ADA-USDT-SWAP...")
    # Validate order with a bankroll of $27
    validation = await execution_auditor_agent.validate_order(
        symbol=sanitized["symbol"],
        direction=sanitized["direction"],
        entry_price=sanitized["entry_price"],
        stop_price=sanitized["stop_price"],
        balance=27.0,
        leverage=50.0
    )
    print("Validation result:", validation)
    assert validation["valid"] is True
    print("Validation OK!")
    
    print("\nTesting validation with insufficient balance ($0.0015)...")
    validation_poor = await execution_auditor_agent.validate_order(
        symbol=sanitized["symbol"],
        direction=sanitized["direction"],
        entry_price=sanitized["entry_price"],
        stop_price=sanitized["stop_price"],
        balance=0.0015,
        leverage=50.0
    )
    print("Validation (Poor) result:", validation_poor)
    assert validation_poor["valid"] is False
    print("Insufficient balance test OK!")

if __name__ == "__main__":
    asyncio.run(main())
