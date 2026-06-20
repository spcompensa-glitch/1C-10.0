import psycopg2
import psycopg2.extras
from collections import defaultdict
import json

DATABASE_URL = "postgresql://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# 0. Status distintos
cur.execute("SELECT status, COUNT(*) as cnt FROM sandbox_trades GROUP BY status ORDER BY cnt DESC")
print("=== STATUS DISTINTOS ===")
statuses = []
for r in cur.fetchall():
    print(f"  {r['status']}: {r['cnt']}")
    statuses.append(r['status'])

# Trades fechados = tudo que nao e ACTIVE
closed_filter = "status NOT IN ('ACTIVE')"

# 1. Estatísticas gerais dos fechados
cur.execute(f"""
SELECT
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
    COUNT(*) FILTER (WHERE pnl_pct <= 0) as losses,
    ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl,
    ROUND(MAX(pnl_pct)::numeric, 2) as max_win,
    ROUND(MIN(pnl_pct)::numeric, 2) as max_loss,
    ROUND(SUM(pnl_pct)::numeric, 2) as total_pnl_sum,
    ROUND(AVG(max_roi)::numeric, 2) as avg_max_roi
FROM sandbox_trades WHERE {closed_filter}
""")
stats = cur.fetchone()
win_rate = round(stats['wins'] / stats['total'] * 100, 1) if stats['total'] > 0 else 0
print(f"\n=== TRADES FECHADOS (Win Rate Analysis) ===")
print(f"Total fechados: {stats['total']} | Wins: {stats['wins']} | Losses: {stats['losses']}")
print(f"Win Rate: {win_rate}%")
print(f"PnL medio: {stats['avg_pnl']}% | Total acumulado: {stats['total_pnl_sum']}%")
print(f"Maior ganho: {stats['max_win']}% | Maior perda: {stats['max_loss']}%")
print(f"Avg ROI pico (antes de fechar): {stats['avg_max_roi']}%")

# 2. Por status (tipo de fechamento)
cur.execute(f"""
SELECT status,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
    ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl,
    ROUND(SUM(pnl_pct)::numeric, 2) as total_pnl
FROM sandbox_trades WHERE {closed_filter}
GROUP BY status ORDER BY total DESC
""")
print(f"\n=== POR TIPO DE FECHAMENTO ===")
for r in cur.fetchall():
    wr = round(r['wins']/r['total']*100,1) if r['total']>0 else 0
    print(f"  {r['status']}: {r['total']} trades | WR: {wr}% | Avg: {r['avg_pnl']}% | Total: {r['total_pnl']}%")

# 3. Por direção
cur.execute(f"""
SELECT direction,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
    ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl,
    ROUND(SUM(pnl_pct)::numeric, 2) as total_pnl
FROM sandbox_trades WHERE {closed_filter}
GROUP BY direction
""")
print(f"\n=== POR DIRECAO ===")
for r in cur.fetchall():
    wr = round(r['wins']/r['total']*100,1) if r['total']>0 else 0
    print(f"  {r['direction']}: {r['total']} | WR: {wr}% | Avg: {r['avg_pnl']}% | Total: {r['total_pnl']}%")

# 4. Por estratégia
cur.execute(f"""
SELECT strategy,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
    ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl,
    ROUND(SUM(pnl_pct)::numeric, 2) as total_pnl
FROM sandbox_trades WHERE {closed_filter}
GROUP BY strategy ORDER BY total DESC
""")
print(f"\n=== POR ESTRATEGIA ===")
for r in cur.fetchall():
    wr = round(r['wins']/r['total']*100,1) if r['total']>0 else 0
    print(f"  {r['strategy']}: {r['total']} | WR: {wr}% | Avg: {r['avg_pnl']}% | Total: {r['total_pnl']}%")

# 5. Top 15 pares mais lucrativos
cur.execute(f"""
SELECT symbol,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
    ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl,
    ROUND(SUM(pnl_pct)::numeric, 2) as total_pnl,
    ROUND(MAX(pnl_pct)::numeric, 2) as best
FROM sandbox_trades WHERE {closed_filter}
GROUP BY symbol HAVING COUNT(*) >= 3 ORDER BY total_pnl DESC LIMIT 15
""")
print(f"\n=== TOP 15 PARES (min 3 trades, por PnL total) ===")
for r in cur.fetchall():
    wr = round(r['wins']/r['total']*100,1) if r['total']>0 else 0
    print(f"  {r['symbol']}: {r['total']} trades | WR: {wr}% | Avg: {r['avg_pnl']}% | Total: {r['total_pnl']}% | Best: {r['best']}%")

# 6. Bottom 15 pares (piores)
cur.execute(f"""
SELECT symbol,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE pnl_pct > 0) as wins,
    ROUND(AVG(pnl_pct)::numeric, 2) as avg_pnl,
    ROUND(SUM(pnl_pct)::numeric, 2) as total_pnl,
    ROUND(MIN(pnl_pct)::numeric, 2) as worst
FROM sandbox_trades WHERE {closed_filter}
GROUP BY symbol HAVING COUNT(*) >= 3 ORDER BY total_pnl ASC LIMIT 15
""")
print(f"\n=== BOTTOM 15 PARES (piores, min 3 trades) ===")
for r in cur.fetchall():
    wr = round(r['wins']/r['total']*100,1) if r['total']>0 else 0
    print(f"  {r['symbol']}: {r['total']} trades | WR: {wr}% | Avg: {r['avg_pnl']}% | Total: {r['total_pnl']}% | Worst: {r['worst']}%")

# 7. Distribuição de PnL
cur.execute(f"""
SELECT
    COUNT(*) FILTER (WHERE pnl_pct < -80) as below_minus80,
    COUNT(*) FILTER (WHERE pnl_pct >= -80 AND pnl_pct < -50) as minus80_to_50,
    COUNT(*) FILTER (WHERE pnl_pct >= -50 AND pnl_pct < -20) as minus50_to_20,
    COUNT(*) FILTER (WHERE pnl_pct >= -20 AND pnl_pct < 0) as minus20_to_0,
    COUNT(*) FILTER (WHERE pnl_pct >= 0 AND pnl_pct < 30) as zero_to_30,
    COUNT(*) FILTER (WHERE pnl_pct >= 30 AND pnl_pct < 100) as plus30_to_100,
    COUNT(*) FILTER (WHERE pnl_pct >= 100 AND pnl_pct < 200) as plus100_to_200,
    COUNT(*) FILTER (WHERE pnl_pct >= 200) as above_200
FROM sandbox_trades WHERE {closed_filter}
""")
dist = cur.fetchone()
print(f"\n=== DISTRIBUICAO DE PnL ===")
print(f"  < -80%:       {dist['below_minus80']}")
print(f"  -80% a -50%:  {dist['minus80_to_50']}")
print(f"  -50% a -20%:  {dist['minus50_to_20']}")
print(f"  -20% a 0%:    {dist['minus20_to_0']}")
print(f"  0% a 30%:     {dist['zero_to_30']}")
print(f"  30% a 100%:   {dist['plus30_to_100']}")
print(f"  100% a 200%:  {dist['plus100_to_200']}")
print(f"  > 200%:       {dist['above_200']}")

# 8. Trades com max_roi muito alto mas pnl baixo (missed profits)
cur.execute(f"""
SELECT COUNT(*) as cnt, ROUND(AVG(max_roi)::numeric,2) as avg_max, ROUND(AVG(pnl_pct)::numeric,2) as avg_pnl
FROM sandbox_trades
WHERE {closed_filter} AND max_roi >= 50 AND pnl_pct < 30
""")
missed = cur.fetchone()
print(f"\n=== LUCRO PERDIDO (max_roi>=50% mas fechou com <30%) ===")
print(f"  {missed['cnt']} trades | Avg pico: {missed['avg_max']}% | Avg fechamento: {missed['avg_pnl']}%")

# 9. Duração média
cur.execute(f"""
SELECT
    ROUND(AVG(EXTRACT(EPOCH FROM (TO_TIMESTAMP(closed_at) - TO_TIMESTAMP(opened_at)))/3600)::numeric, 2) as avg_h,
    ROUND(AVG(EXTRACT(EPOCH FROM (TO_TIMESTAMP(closed_at) - TO_TIMESTAMP(opened_at)))/3600) FILTER (WHERE pnl_pct > 0)::numeric, 2) as win_h,
    ROUND(AVG(EXTRACT(EPOCH FROM (TO_TIMESTAMP(closed_at) - TO_TIMESTAMP(opened_at)))/3600) FILTER (WHERE pnl_pct <= 0)::numeric, 2) as loss_h
FROM sandbox_trades WHERE {closed_filter} AND closed_at IS NOT NULL AND opened_at IS NOT NULL
""")
dur = cur.fetchone()
print(f"\n=== DURACAO MEDIA ===")
print(f"  Geral: {dur['avg_h']}h | Wins: {dur['avg_h']}h | Losses: {dur['loss_h']}h")

# 10. Analise de stop loss (onde o stop esta sendo ativado)
cur.execute(f"""
SELECT
    ROUND(AVG(pnl_pct)::numeric, 2) as avg_sl_pnl,
    ROUND(MIN(pnl_pct)::numeric, 2) as worst_sl,
    COUNT(*) as total_sl
FROM sandbox_trades WHERE status = 'CLOSED_SL'
""")
sl = cur.fetchone()
print(f"\n=== STOP LOSS ANALYSIS ===")
print(f"  Total SL hits: {sl['total_sl']} | Avg PnL no SL: {sl['avg_sl_pnl']}% | Pior SL: {sl['worst_sl']}%")

# 11. Posições ativas agora
cur.execute(f"""
SELECT symbol, direction, current_roi, pnl_pct, max_roi, opened_at
FROM sandbox_trades WHERE status='ACTIVE'
ORDER BY current_roi DESC
""")
print(f"\n=== POSICOES ATIVAS AGORA ===")
for r in cur.fetchall():
    print(f"  {r['symbol']} {r['direction']} | ROI atual: {round(r['current_roi'],1)}% | Max: {round(r['max_roi'],1)}%")

conn.close()
print("\nAnalise concluida.")
