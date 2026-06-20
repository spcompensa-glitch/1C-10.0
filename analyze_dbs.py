import sqlite3
import os
import json

TRADE_TABLE_KEYWORDS = ['trade', 'history', 'signal', 'order', 'backtest', 'result', 'candle', 'tick', 'log']

def analyze_db(db_path):
    report = {}
    report['path'] = db_path
    report['exists'] = os.path.exists(db_path)
    if not report['exists']:
        report['error'] = 'Arquivo não encontrado'
        return report

    report['size_bytes'] = os.path.getsize(db_path)
    report['size_kb'] = round(report['size_bytes'] / 1024, 2)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Lista todas as tabelas
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cursor.fetchall()]
    report['tables'] = []

    for t in tables:
        tinfo = {'name': t}

        # Schema
        cursor.execute(f'PRAGMA table_info("{t}")')
        cols = cursor.fetchall()
        tinfo['columns'] = [
            {'cid': c[0], 'name': c[1], 'type': c[2], 'notnull': bool(c[3]), 'default': c[4], 'pk': bool(c[5])}
            for c in cols
        ]

        # Índices
        cursor.execute(f'PRAGMA index_list("{t}")')
        indexes = cursor.fetchall()
        tinfo['indexes'] = [{'name': ix[1], 'unique': bool(ix[2])} for ix in indexes]

        # Contagem
        try:
            cursor.execute(f'SELECT COUNT(*) FROM "{t}"')
            tinfo['row_count'] = cursor.fetchone()[0]
        except Exception as e:
            tinfo['row_count'] = f'Erro: {e}'

        # Verifica se parece ser tabela de trades/histórico
        is_trade_table = any(kw in t.lower() for kw in TRADE_TABLE_KEYWORDS)

        col_names = [c['name'].lower() for c in tinfo['columns']]
        has_pnl = any(kw in col_names for kw in ['pnl', 'profit', 'gain', 'loss', 'return'])
        has_win = any(kw in col_names for kw in ['win', 'result', 'outcome', 'status', 'side'])
        has_time = any(kw in col_names for kw in ['time', 'date', 'timestamp', 'created', 'open_time', 'close_time'])

        if is_trade_table or has_pnl or has_win:
            tinfo['is_trade_like'] = True
        else:
            tinfo['is_trade_like'] = False

        # Primeiras e últimas 10 linhas para tabelas relevantes
        try:
            if tinfo['row_count'] and isinstance(tinfo['row_count'], int) and tinfo['row_count'] > 0:
                cursor.execute(f'SELECT * FROM "{t}" LIMIT 10')
                rows = cursor.fetchall()
                tinfo['first_10'] = [dict(r) for r in rows]

                cursor.execute(f'SELECT COUNT(*) FROM "{t}"')
                total = cursor.fetchone()[0]
                if total > 10:
                    offset = max(0, total - 10)
                    cursor.execute(f'SELECT * FROM "{t}" LIMIT 10 OFFSET {offset}')
                    rows = cursor.fetchall()
                    tinfo['last_10'] = [dict(r) for r in rows]
                else:
                    tinfo['last_10'] = tinfo['first_10']
        except Exception as e:
            tinfo['sample_error'] = str(e)

        # Estatísticas de PnL se aplicável
        if tinfo['is_trade_like'] and isinstance(tinfo['row_count'], int) and tinfo['row_count'] > 0:
            stats = {}

            # Detecta coluna de PnL
            pnl_col = None
            for poss in ['pnl', 'profit', 'gain', 'net_profit', 'realizedPnl', 'realized_pnl', 'profit_loss']:
                if poss.lower() in col_names:
                    idx = col_names.index(poss.lower())
                    pnl_col = tinfo['columns'][idx]['name']
                    break

            if pnl_col:
                try:
                    cursor.execute(f'''
                        SELECT
                            COUNT(*) as total,
                            SUM(CASE WHEN "{pnl_col}" > 0 THEN 1 ELSE 0 END) as wins,
                            SUM(CASE WHEN "{pnl_col}" < 0 THEN 1 ELSE 0 END) as losses,
                            SUM("{pnl_col}") as total_pnl,
                            AVG("{pnl_col}") as avg_pnl,
                            MAX("{pnl_col}") as max_gain,
                            MIN("{pnl_col}") as max_loss
                        FROM "{t}"
                        WHERE "{pnl_col}" IS NOT NULL
                    ''')
                    r = cursor.fetchone()
                    if r and r[0]:
                        stats['pnl_col'] = pnl_col
                        stats['total_trades'] = r[0]
                        stats['wins'] = r[1] or 0
                        stats['losses'] = r[2] or 0
                        stats['win_rate'] = round((r[1] or 0) / r[0] * 100, 2) if r[0] > 0 else 0
                        stats['total_pnl'] = round(r[3] or 0, 6)
                        stats['avg_pnl'] = round(r[4] or 0, 6)
                        stats['max_gain'] = round(r[5] or 0, 6)
                        stats['max_loss'] = round(r[6] or 0, 6)
                except Exception as e:
                    stats['pnl_error'] = str(e)

            # Detecta coluna de duração ou datas
            open_col = None
            close_col = None
            for poss in ['open_time', 'entry_time', 'created_at', 'timestamp', 'open_at']:
                if poss.lower() in col_names:
                    idx = col_names.index(poss.lower())
                    open_col = tinfo['columns'][idx]['name']
                    break
            for poss in ['close_time', 'exit_time', 'closed_at', 'updated_at']:
                if poss.lower() in col_names:
                    idx = col_names.index(poss.lower())
                    close_col = tinfo['columns'][idx]['name']
                    break

            duration_col = None
            for poss in ['duration', 'duration_sec', 'hold_time', 'trade_duration']:
                if poss.lower() in col_names:
                    idx = col_names.index(poss.lower())
                    duration_col = tinfo['columns'][idx]['name']
                    break

            if duration_col:
                try:
                    cursor.execute(f'SELECT AVG("{duration_col}") FROM "{t}" WHERE "{duration_col}" IS NOT NULL')
                    avg_dur = cursor.fetchone()[0]
                    stats['avg_duration'] = round(avg_dur or 0, 2)
                    stats['avg_duration_col'] = duration_col
                except Exception as e:
                    stats['duration_error'] = str(e)

            tinfo['stats'] = stats

        report['tables'].append(tinfo)

    conn.close()
    return report


def print_report(report):
    print(f"\n{'='*70}")
    print(f"BANCO DE DADOS: {report['path']}")
    print(f"{'='*70}")
    print(f"  Existe: {report['exists']}")
    if not report['exists']:
        print(f"  ERRO: {report.get('error', 'Não encontrado')}")
        return
    print(f"  Tamanho: {report['size_kb']} KB ({report['size_bytes']} bytes)")
    print(f"  Tabelas: {len(report['tables'])}")

    for t in report['tables']:
        print(f"\n{'─'*60}")
        print(f"  TABELA: {t['name']}  ({t['row_count']} registros)  Trade-like: {t.get('is_trade_like')}")
        print(f"{'─'*60}")
        print("  Colunas:")
        for c in t['columns']:
            pk = ' [PK]' if c['pk'] else ''
            nn = ' NOT NULL' if c['notnull'] else ''
            df = f" DEFAULT={c['default']}" if c['default'] else ''
            print(f"    [{c['cid']}] {c['name']} ({c['type']}){pk}{nn}{df}")

        if t.get('indexes'):
            print("  Índices:")
            for ix in t['indexes']:
                u = ' UNIQUE' if ix['unique'] else ''
                print(f"    {ix['name']}{u}")

        if 'stats' in t and t['stats']:
            s = t['stats']
            print(f"\n  📊 ESTATÍSTICAS (coluna PnL: {s.get('pnl_col', 'N/A')}):")
            print(f"    Total trades   : {s.get('total_trades', 'N/A')}")
            print(f"    Wins           : {s.get('wins', 'N/A')}")
            print(f"    Losses         : {s.get('losses', 'N/A')}")
            print(f"    Win Rate       : {s.get('win_rate', 'N/A')}%")
            print(f"    PnL Total      : {s.get('total_pnl', 'N/A')}")
            print(f"    PnL Médio      : {s.get('avg_pnl', 'N/A')}")
            print(f"    Maior Ganho    : {s.get('max_gain', 'N/A')}")
            print(f"    Maior Perda    : {s.get('max_loss', 'N/A')}")
            if 'avg_duration' in s:
                print(f"    Duração Média  : {s['avg_duration']} (col: {s['avg_duration_col']})")

        if 'first_10' in t and t['first_10']:
            print(f"\n  ▶ Primeiras 10 linhas:")
            col_headers = list(t['first_10'][0].keys())
            print(f"    Colunas: {col_headers}")
            for i, row in enumerate(t['first_10'], 1):
                print(f"    [{i:02d}] {dict(row)}")

        if 'last_10' in t and t['last_10'] and t['last_10'] != t.get('first_10'):
            print(f"\n  ◀ Últimas 10 linhas:")
            for i, row in enumerate(t['last_10'], 1):
                print(f"    [{i:02d}] {dict(row)}")

        if 'sample_error' in t:
            print(f"  ⚠ Erro ao amostrar: {t['sample_error']}")


# ANÁLISE DOS TRÊS BANCOS
dbs = [
    r'c:\Users\spcom\Desktop\1C-8.0\local_sniper.db',
    r'c:\Users\spcom\Desktop\1C-8.0\backend\local_sniper.db',
    r'c:\Users\spcom\Desktop\1C-8.0\backend\backtest_data.db',
]

all_reports = []
for db in dbs:
    r = analyze_db(db)
    all_reports.append(r)
    print_report(r)

# Salva JSON bruto para referência
with open(r'c:\Users\spcom\Desktop\1C-8.0\db_analysis_raw.json', 'w', encoding='utf-8') as f:
    json.dump(all_reports, f, ensure_ascii=False, indent=2, default=str)

print("\n\n✅ Análise concluída! JSON salvo em db_analysis_raw.json")
