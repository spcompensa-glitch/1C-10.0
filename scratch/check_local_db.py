import sqlite3

db_path = "local_sniper.db"

def check_local_db():
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Tables in SQLite: {tables}")
        
        if "trade_history" in tables:
            print("--- LAST 20 TRADES (SQLite) ---")
            cursor.execute("SELECT id, symbol, side, pnl, pnl_percent, exit_price, entry_price, close_reason, timestamp FROM trade_history ORDER BY timestamp DESC LIMIT 20")
            for row in cursor.fetchall():
                print(f"ID: {row[0]} | Symbol: {row[1]} | Side: {row[2]} | PnL: ${row[3]:.2f} ({row[4]}%) | Entry: {row[6]} | Exit: {row[5]} | Reason: {row[7]} | Time: {row[8]}")
                
            print("\n--- ANY TRADES MATCHING 'BAR' ---")
            cursor.execute("SELECT id, symbol, side, pnl, pnl_percent, exit_price, entry_price, close_reason, timestamp FROM trade_history WHERE symbol LIKE '%BAR%' OR symbol LIKE '%HAR%' OR symbol LIKE '%HAB%'")
            for row in cursor.fetchall():
                print(f"ID: {row[0]} | Symbol: {row[1]} | Side: {row[2]} | PnL: ${row[3]:.2f} ({row[4]}%) | Entry: {row[6]} | Exit: {row[5]} | Reason: {row[7]} | Time: {row[8]}")
        else:
            print("trade_history table not found in SQLite.")
            
    except Exception as e:
        print(f"Error checking local DB: {e}")

if __name__ == "__main__":
    check_local_db()
