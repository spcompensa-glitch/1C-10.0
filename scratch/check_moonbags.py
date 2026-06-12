import sys
from pathlib import Path
from sqlalchemy import create_engine, text

db_url = "postgresql://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"

def check_moonbags():
    engine = create_engine(db_url)
    with engine.connect() as conn:
        print("--- ACTIVE MOONBAGS ---")
        result = conn.execute(text("SELECT uuid, symbol, side, entry_price, current_stop, target_price, leverage, pnl_percent, promoted_at FROM moonbags"))
        rows = list(result)
        if not rows:
            print("No active moonbags.")
        for row in rows:
            print(f"UUID: {row[0]} | Symbol: {row[1]} | Side: {row[2]} | Entry: {row[3]} | Stop: {row[4]} | Target: {row[5]} | Leverage: {row[6]} | PnL%: {row[7]}% | Promoted: {row[8]}")

if __name__ == "__main__":
    check_moonbags()
