"""
Cleanup Ghost Slots - Direct SQLite approach
Resets the 4 ghost slots to LIVRE and banca to $20.00
"""
import sqlite3
import os
import sys

# Find the database file
possible_paths = [
    os.path.join("backend", "local_sniper.db"),
    os.path.join("..", "backend", "local_sniper.db"),
    "local_sniper.db",
]

db_path = None
for p in possible_paths:
    if os.path.exists(p):
        db_path = p
        break

if not db_path:
    for root, dirs, files in os.walk("."):
        for f in files:
            if f == "local_sniper.db":
                db_path = os.path.join(root, f)
                break
        if db_path:
            break

if not db_path:
    print("[ERROR] Could not find the database file!")
    sys.exit(1)

print(f"[DB] Database found at: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Show current slots
print("\n[CURRENT] Slots before cleanup:")
try:
    cursor.execute("SELECT id, symbol, status_risco, pnl_percent, qty, entry_price FROM slots ORDER BY id")
    rows = cursor.fetchall()
    for row in rows:
        sym = row[1] or "EMPTY"
        print(f"  Slot {row[0]}: Symbol={sym} | Status={row[2]} | PnL={row[3]}% | Qty={row[4]} | Entry={row[5]}")
except sqlite3.OperationalError as e:
    print(f"  Error reading slots: {e}")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print(f"  Available tables: {[t[0] for t in tables]}")

# Reset all 4 slots
print("\n[CLEANUP] Resetting all 4 slots to LIVRE...")
try:
    reset_sql = """
    UPDATE slots SET 
        symbol = NULL,
        side = NULL,
        qty = 0.0,
        entry_price = 0.0,
        entry_margin = 0.0,
        current_stop = 0.0,
        initial_stop = 0.0,
        target_price = 0.0,
        liq_price = 0.0,
        pnl_percent = 0.0,
        status_risco = 'LIVRE',
        order_id = NULL,
        genesis_id = NULL,
        slot_type = NULL,
        pattern = NULL,
        pensamento = 'GHOST CLEANUP',
        score = 0,
        opened_at = NULL,
        rescue_activated = 0,
        rescue_resolved = 0,
        sentinel_first_hit_at = 0.0
    """
    cursor.execute(reset_sql)
    conn.commit()
    print(f"[OK] {cursor.rowcount} slots resetados para LIVRE!")
except sqlite3.OperationalError as e:
    print(f"[ERROR] Resetting slots: {e}")

# Update banca status
print("\n[BANCA] Resetting banca status to $20...")
try:
    cursor.execute("SELECT id, saldo_total FROM banca_status WHERE id = 1")
    banca = cursor.fetchone()
    if banca:
        print(f"  Current banca: ID={banca[0]}, saldo={banca[1]}")
        cursor.execute("""
        UPDATE banca_status SET 
            saldo_total = 20.0,
            configured_balance = 20.0,
            risco_real_percent = 0.0,
            slots_disponiveis = 4,
            status = 'ONLINE'
        WHERE id = 1
        """)
        conn.commit()
        print(f"[OK] Banca resetada para $20.00 ({cursor.rowcount} rows)")
    else:
        print("[WARN] No banca_status row found with id=1")
except sqlite3.OperationalError as e:
    print(f"[WARN] Could not reset banca: {e}")

# Clean moonbags if any
print("\n[MOONBAGS] Checking for ghost moonbags...")
try:
    cursor.execute("SELECT uuid, symbol FROM moonbags")
    moons = cursor.fetchall()
    if moons:
        print(f"  Found {len(moons)} moonbags:")
        for m in moons:
            print(f"    {m[0]}: {m[1]}")
        cursor.execute("DELETE FROM moonbags")
        conn.commit()
        print(f"[OK] {cursor.rowcount} moonbags removidas!")
    else:
        print("[OK] No moonbags found.")
except sqlite3.OperationalError as e:
    print(f"[WARN] Could not check moonbags: {e}")

# Verify final state
print("\n[VERIFY] Slots after cleanup:")
try:
    cursor.execute("SELECT id, symbol, status_risco FROM slots ORDER BY id")
    rows = cursor.fetchall()
    all_clean = True
    for row in rows:
        if row[1]:
            all_clean = False
            print(f"  Slot {row[0]}: [BUSY] {row[1]} ({row[2]})")
        else:
            print(f"  Slot {row[0]}: [OK] LIVRE")
    
    if all_clean:
        print("\n[SUCCESS] ALL SLOTS ARE LIVRE! The Captain should now be able to open orders.")
    else:
        print("\n[WARN] Some slots still occupied.")
except sqlite3.OperationalError as e:
    print(f"  Error verifying: {e}")

# Verify banca
try:
    cursor.execute("SELECT saldo_total, configured_balance FROM banca_status WHERE id = 1")
    b = cursor.fetchone()
    if b:
        print(f"[BANCA] saldo_total=${b[0]:.2f}, configured_balance=${b[1]:.2f}")
except:
    pass

conn.close()
