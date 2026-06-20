import psycopg2

DATABASE_URL = "postgresql://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Deletar todos os registros da tabela sandbox_trades
    cur.execute("DELETE FROM sandbox_trades")
    deleted_count = cur.rowcount
    conn.commit()
    
    print(f"=== SUCESSO ===")
    print(f"Foram deletados {deleted_count} registros da tabela sandbox_trades.")
    
    conn.close()
except Exception as e:
    print(f"ERRO: {e}")
