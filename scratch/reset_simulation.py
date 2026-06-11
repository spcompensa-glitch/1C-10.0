import sys
import os
from pathlib import Path
from sqlalchemy import create_engine, text

# URL do Banco de dados PostgreSQL no Railway
db_url = "postgresql://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"

def reset_simulation():
    print("[RESET] Iniciando reset completo da simulação (Postgres Railway)...")
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            # 1. Limpar tabela trade_history
            print("Limpando histórico de trades...")
            conn.execute(text("TRUNCATE TABLE trade_history RESTART IDENTITY CASCADE"))
            
            # 2. Resetar slots ativos para SCANNING
            print("Resetando slots ativos para SCANNING...")
            conn.execute(text("""
                UPDATE slots 
                SET symbol = NULL, 
                    status_risco = 'LIVRE', 
                    entry_price = 0, 
                    qty = 0, 
                    entry_margin = 0, 
                    current_stop = 0, 
                    target_price = 0, 
                    pnl_percent = 0,
                    side = 'Buy',
                    opened_at = NULL,
                    sentinel_first_hit_at = 0
            """))
            
            # 3. Limpar Moonbags ativas
            print("Limpando Moonbags ativas...")
            conn.execute(text("DELETE FROM moonbags"))
            
            # 4. Resetar banca status para $20.00 iniciais
            print("Resetando banca de simulação para $20.00...")
            # Verifica se já existe um registro para atualizar, senão insere
            result = conn.execute(text("SELECT COUNT(*) FROM banca_status"))
            count = result.scalar()
            
            if count > 0:
                conn.execute(text("""
                    UPDATE banca_status 
                    SET saldo_total = 20.00, 
                        configured_balance = 20.00,
                        updated_at = NOW()
                """))
            else:
                conn.execute(text("""
                    INSERT INTO banca_status (saldo_total, configured_balance, status, updated_at)
                    VALUES (20.00, 20.00, 'Preservacao total', NOW())
                """))
            
            conn.commit()
            print("[RESET] Simulação resetada com sucesso no PostgreSQL!")
            
    except Exception as e:
        print(f"Erro ao resetar simulação no Postgres: {e}")

if __name__ == "__main__":
    reset_simulation()
