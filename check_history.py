import psycopg2
import psycopg2.extras
import sys

# Forçar output UTF-8 para evitar erros de charmap
sys.stdout.reconfigure(encoding='utf-8')

DATABASE_URL = "postgresql://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("SELECT * FROM trade_history ORDER BY timestamp DESC LIMIT 5")
    rows = cur.fetchall()
    
    print("=== ÚLTIMOS TRADES DO HISTÓRICO ===")
    for r in rows:
        d = dict(r)
        # Limitar visualização de dados grandes
        if 'data' in d:
            d['data'] = {k: v for k, v in d['data'].items() if k not in ['reasoning_report', 'pensamento']}
        print(f"Symbol: {d.get('symbol')} | Side: {d.get('side')} | PnL: {d.get('pnl')} | Strategy: {d.get('strategy')} | Close Reason: {d.get('close_reason')} | Timestamp: {d.get('timestamp')}")

    conn.close()
except Exception as e:
    print(f"ERRO: {e}")
