import asyncio
import asyncpg
import json

LOCAL_DSN = "postgresql://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"
PROD_DSN = "postgresql://postgres:JzPWsemUkGYnEaSUcPDYdPonxFJsvlmU@postgres.railway.internal:5432/railway"

async def get_table_names(conn):
    rows = await conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
    )
    return [r['table_name'] for r in rows]

async def main():
    print("Conectando ao banco LOCAL...")
    local = await asyncpg.connect(LOCAL_DSN)
    prod = await asyncpg.connect(PROD_DSN)

    tables_local = await get_table_names(local)
    tables_prod = await get_table_names(prod)
    print(f"Tabelas local: {tables_local}")
    print(f"Tabelas prod:  {tables_prod}")

    # Find sandbox_trades table
    sandbox_table = None
    for t in tables_local:
        if 'sandbox' in t.lower() or 'sandbox_trade' in t.lower():
            sandbox_table = t
            break

    if not sandbox_table:
        print("ERRO: tabela sandbox_trades não encontrada no banco LOCAL.")
        await local.close()
        await prod.close()
        return

    print(f"Tabela encontrada: {sandbox_table}")

    # Get columns
    cols = await local.fetch(
        "SELECT column_name, data_type FROM information_schema.columns WHERE table_name=$1 ORDER BY ordinal_position",
        sandbox_table
    )
    col_names = [c['column_name'] for c in cols]
    print(f"Colunas: {col_names}")

    # Read all rows from local
    rows = await local.fetch(f"SELECT * FROM {sandbox_table} ORDER BY created_at")
    print(f"Total de registros no LOCAL: {len(rows)}")

    inserted = 0
    skipped = 0

    for row in rows:
        row_dict = dict(row)
        trade_id = row_dict.get('id')

        # Check if exists in prod
        exists = await prod.fetchval(f"SELECT COUNT(*) FROM {sandbox_table} WHERE id=$1", trade_id)
        if exists > 0:
            skipped += 1
            continue

        # Build INSERT
        placeholders = ','.join([f'${i+1}' for i in range(len(col_names))])
        values = [row_dict[c] for c in col_names]

        # Convert dict/jsonb fields
        for i, c in enumerate(col_names):
            if isinstance(values[i], (dict, list)):
                values[i] = json.dumps(values[i])

        try:
            await prod.execute(
                f"INSERT INTO {sandbox_table} ({','.join(col_names)}) VALUES ({placeholders})",
                *values
            )
            inserted += 1
            print(f"  + {trade_id} ({row_dict.get('symbol', '?')})")
        except Exception as e:
            print(f"  ERRO ao inserir {trade_id}: {e}")

    print(f"\nInseridos: {inserted} | Pulados (já existem): {skipped} | Total: {len(rows)}")

    await local.close()
    await prod.close()

asyncio.run(main())
