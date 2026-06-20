import psycopg2
import psycopg2.extras

DATABASE_URL = "postgresql://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Listar tabelas
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' ORDER BY table_name
    """)
    tables = [r[0] for r in cur.fetchall()]
    print("=== TABELAS NO POSTGRESQL ===")
    for t in tables:
        cur.execute(f'SELECT COUNT(*) FROM "{t}"')
        cnt = cur.fetchone()[0]
        print(f"  {t}: {cnt} registros")

    conn.close()
except Exception as e:
    print(f"ERRO: {e}")
