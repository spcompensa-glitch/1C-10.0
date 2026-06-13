import os
import psycopg2
from dotenv import load_dotenv

# Define local .env path explicitly to backend/.env where the real DATABASE_URL is defined
load_dotenv('backend/.env', override=True)

def check():
    url = os.getenv("DATABASE_URL")
    if not url or url == "<sua_url_do_postgres>":
        # Force exact connection string from backend/.env if override failed
        url = "postgresql://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"
    
    try:
        conn = psycopg2.connect(url)
        cur = conn.cursor()
        
        # 1. Active slots
        cur.execute("SELECT id, symbol, side, entry_price, current_stop, status_risco, pnl_percent FROM slots;")
        slots = cur.fetchall()
        print("\n=== POSTGRES SLOTS ===")
        for s in slots:
            print(f"Slot {s[0]}: {s[1]} | {s[2]} | Entry: ${s[3]} | Stop: ${s[4]} | Status: {s[5]} | PnL: {s[6]}%")
            
        # 2. Moonbags
        cur.execute("SELECT uuid, symbol, side, entry_price, current_stop, pnl_percent FROM moonbags;")
        moons = cur.fetchall()
        print("\n=== POSTGRES MOONBAGS ===")
        for m in moons:
            print(f"Moonbag {m[0]}: {m[1]} | {m[2]} | Entry: ${m[3]} | Stop: ${m[4]} | PnL: {m[5]}%")
            
        # 3. Sandbox trades (Active & Closed)
        cur.execute("SELECT symbol, direction, entry_price, current_price, current_roi, pnl_pct, status, closed_at FROM sandbox_trades ORDER BY opened_at DESC LIMIT 30;")
        sand = cur.fetchall()
        print("\n=== POSTGRES SANDBOX TRADES (Last 30) ===")
        for sd in sand:
            print(f"Symbol: {sd[0]} | Dir: {sd[1]} | Entry: ${sd[2]} | Curr: ${sd[3]} | ROI: {sd[4]}% | PnL: {sd[5]}% | Status: {sd[6]} | Closed: {sd[7]}")

        # 4. Trade History (Real/Paper Results)
        cur.execute("SELECT symbol, side, entry_price, exit_price, pnl, pnl_percent, close_reason, timestamp FROM trade_history ORDER BY timestamp DESC LIMIT 15;")
        history = cur.fetchall()
        print("\n=== POSTGRES TRADE HISTORY (Last 15 Trades) ===")
        for h in history:
            print(f"{h[7]} | {h[0]} | {h[1]} | Entry: ${h[2]} | Exit: ${h[3]} | PnL: ${h[4]:.2f} ({h[5]}%) | Reason: {h[6]}")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check()
