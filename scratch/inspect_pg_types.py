# coding: utf-8
import psycopg2

def inspect():
    postgres_url = "postgresql://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"
    try:
        conn = psycopg2.connect(postgres_url)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'slots' 
            ORDER BY ordinal_position;
        """)
        rows = cur.fetchall()
        print("=== POSTGRES SLOTS COLUMNS & TYPES ===")
        for row in rows:
            print(f"{row[0]}: {row[1]}")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect()
