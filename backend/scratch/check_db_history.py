import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def check_history():
    db_url = "postgresql+asyncpg://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"
    engine = create_async_engine(db_url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT id, symbol, side, entry_price, exit_price, pnl, close_reason FROM trade_history ORDER BY id DESC"))
            rows = result.fetchall()
            print(f"Total rows in trade_history: {len(rows)}")
            for r in rows:
                print(r)
                
            slots_res = await conn.execute(text("SELECT id, symbol, status_risco, entry_price, current_stop FROM slots ORDER BY id"))
            print("\nSlots status:")
            for s in slots_res.fetchall():
                print(s)

            # Query sandbox trades
            print("\nSandbox Stats:")
            sb_res = await conn.execute(text("SELECT status, count(*), sum(pnl_pct) FROM sandbox_trades GROUP BY status"))
            for sb in sb_res.fetchall():
                print(sb)

            print("\nLast 15 Sandbox Trades:")
            sb_trades = await conn.execute(text("SELECT symbol, direction, entry_price, current_price, current_roi, max_roi, status, flash_state FROM sandbox_trades ORDER BY opened_at DESC LIMIT 15"))
            for sbt in sb_trades.fetchall():
                # print symbol, direction, entry_price, current_price, current_roi, max_roi, status, and summary of flash_state history
                hist = sbt[7].get("history", []) if sbt[7] else []
                last_hist = hist[-1] if hist else "No history"
                print(f"{sbt[0]} | {sbt[1]} | Entry: {sbt[2]:.6f} | Current/Exit: {sbt[3]:.6f} | ROI: {sbt[4]:.2f}% | Max: {sbt[5]:.2f}% | Status: {sbt[6]} | Last log: {last_hist}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_history())
