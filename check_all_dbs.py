import sqlite3

db_paths = [
    r'c:\Users\spcom\Desktop\1C-8.0\backend\local_sniper.db',
    r'c:\Users\spcom\Desktop\1C-8.0\local_sniper.db',
    r'c:\Users\spcom\Desktop\1C-8.0\backend\backtest_data.db',
    r'c:\Users\spcom\Desktop\1C-8.0\auth.db',
    r'c:\Users\spcom\Desktop\1C-8.0\backend\auth.db',
]

for db_path in db_paths:
    print(f'\n=== {db_path} ===')
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        for t in tables:
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{t}"')
                cnt = cur.fetchone()[0]
                print(f'  {t}: {cnt} registros')
            except Exception as e2:
                print(f'  {t}: ERRO - {e2}')
        conn.close()
    except Exception as e:
        print(f'  ERRO: {e}')
