import psycopg2

DATABASE_URL = "postgresql://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # 1. Limpar histórico de trades e sandbox
    cur.execute("DELETE FROM trade_history")
    deleted_history = cur.rowcount
    
    cur.execute("DELETE FROM sandbox_trades")
    deleted_sandbox = cur.rowcount
    
    cur.execute("DELETE FROM moonbags")
    deleted_moonbags = cur.rowcount

    # 2. Resetar vault_cycles
    cur.execute("DELETE FROM vault_cycles")
    
    # Inserir ciclo inicial limpo
    initial_cycle_data = '{"sniper_wins": 0, "cycle_number": 1, "cycle_profit": 0.0, "cycle_losses": 0.0, "mega_cycle_wins": 0, "mega_cycle_number": 1, "accumulated_vault": 0.0, "vault_total": 0.0, "used_symbols_in_cycle": "[]", "cycle_start_bankroll": 100.0}'
    cur.execute(
        "INSERT INTO vault_cycles (id, data, updated_at) VALUES (1, %s, NOW())",
        (initial_cycle_data,)
    )
    print("DONE: vault_cycles resetado para ciclo 1.")

    # 3. Limpar os slots ativos para ficarem LIVREs
    cur.execute("""
        UPDATE slots 
        SET symbol = NULL, 
            side = NULL, 
            qty = 0.0, 
            entry_price = 0.0, 
            entry_margin = 0.0, 
            current_stop = 0.0, 
            initial_stop = 0.0, 
            order_id = NULL, 
            target_price = 0.0, 
            status_risco = 'LIVRE', 
            pnl_percent = 0.0, 
            pensamento = NULL
    """)
    updated_slots = cur.rowcount

    conn.commit()
    conn.close()
    
    print(f"=== SUCESSO ===")
    print(f"Postgres limpo com sucesso!")
    print(f"  - {deleted_history} registros de trade_history deletados.")
    print(f"  - {deleted_sandbox} registros de sandbox_trades deletados.")
    print(f"  - {deleted_moonbags} registros de moonbags deletados.")
    print(f"  - {updated_slots} slots limpos para status LIVRE.")
except Exception as e:
    print(f"ERRO POSTGRES: {e}")
