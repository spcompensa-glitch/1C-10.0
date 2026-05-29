# coding: utf-8
import sqlite3
import psycopg2
import sys
import os
from datetime import datetime

def get_postgres_columns_with_types(pg_cur, table_name):
    query = f"""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = '{table_name}';
    """
    pg_cur.execute(query)
    return {row[0]: row[1] for row in pg_cur.fetchall()}

def clean_value_for_postgres(val, pg_type, col_name):
    if val is None:
        return None
        
    # Tratamento especial para booleanos (SQLite usa 0/1, Postgres exige True/False)
    if "boolean" in pg_type:
        if isinstance(val, int):
            return val != 0
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes", "t")
        return bool(val)

    # Tratamento especial de data string para double precision (Epoch float)
    if "double precision" in pg_type or "numeric" in pg_type or "real" in pg_type:
        if isinstance(val, str):
            try:
                # Se for uma string de data tipo '2026-05-29 16:01:42.843479'
                if "-" in val and ":" in val:
                    date_str = val.split(".")[0] if "." in val else val
                    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    return float(dt.timestamp())
                return float(val)
            except Exception:
                return None
        return float(val)

    if "integer" in pg_type:
        try:
            return int(val)
        except Exception:
            return None

    if "timestamp" in pg_type:
        if isinstance(val, str):
            try:
                if "." in val:
                    val = val.split(".")[0]
                return val
            except Exception:
                return None

    return val

def migrate():
    sqlite_db = "local_sniper.db"
    postgres_url = "postgresql://postgres:JSLsEfBVPywKuYJSAypuNPVvIgYwGXzz@centerbeam.proxy.rlwy.net:54059/railway"
    
    if not os.path.exists(sqlite_db):
        print("Erro: Arquivo SQLite local_sniper.db nao encontrado na raiz!")
        return

    print("Conectando ao SQLite local...")
    lite_conn = sqlite3.connect(sqlite_db)
    lite_cur = lite_conn.cursor()
    
    print("Conectando ao Postgres de Producao (Railway)...")
    try:
        pg_conn = psycopg2.connect(postgres_url)
        pg_cur = pg_conn.cursor()
    except Exception as e:
        print(f"Erro ao conectar no Postgres: {e}")
        lite_conn.close()
        return

    try:
        # --- 1. MIGRAR TABELA DE SLOTS ---
        print("Obtendo colunas e tipos de slots em producao...")
        pg_cols_types = get_postgres_columns_with_types(pg_cur, "slots")
        if not pg_cols_types:
            print("Erro: Tabela slots nao encontrada no Postgres!")
            return
        
        print("Lendo slots do SQLite local...")
        lite_cur.execute("SELECT * FROM slots;")
        lite_columns = [desc[0] for desc in lite_cur.description]
        lite_rows = lite_cur.fetchall()
        
        common_columns = [col for col in lite_columns if col in pg_cols_types]
        print(f"Colunas comuns para slots ({len(common_columns)}): {common_columns}")
        
        print("Limpando slots no Postgres de Producao...")
        pg_cur.execute("DELETE FROM slots;")
        
        print("Inserindo slots compativeis no Postgres de Producao...")
        for row in lite_rows:
            row_dict = dict(zip(lite_columns, row))
            row_values = []
            
            for col in common_columns:
                val = row_dict[col]
                pg_type = pg_cols_types[col]
                clean_val = clean_value_for_postgres(val, pg_type, col)
                row_values.append(clean_val)
            
            placeholders = ", ".join(["%s"] * len(common_columns))
            columns_str = ", ".join(common_columns)
            query = f"INSERT INTO slots ({columns_str}) VALUES ({placeholders});"
            pg_cur.execute(query, row_values)

        # --- 2. MIGRAR TABELA DE BANCA STATUS ---
        print("Obtendo colunas e tipos de banca_status em producao...")
        pg_banca_types = get_postgres_columns_with_types(pg_cur, "banca_status")
        if pg_banca_types:
            print("Lendo banca_status do SQLite local...")
            lite_cur.execute("SELECT * FROM banca_status;")
            lite_banca_cols = [desc[0] for desc in lite_cur.description]
            lite_banca_rows = lite_cur.fetchall()
            
            common_banca_cols = [col for col in lite_banca_cols if col in pg_banca_types]
            
            print("Limpando banca_status no Postgres...")
            pg_cur.execute("DELETE FROM banca_status;")
            print("Inserindo banca_status compativeis no Postgres...")
            for row in lite_banca_rows:
                row_dict = dict(zip(lite_banca_cols, row))
                row_values = []
                for col in common_banca_cols:
                    val = row_dict[col]
                    pg_type = pg_banca_types[col]
                    clean_val = clean_value_for_postgres(val, pg_type, col)
                    row_values.append(clean_val)
                
                placeholders = ", ".join(["%s"] * len(common_banca_cols))
                columns_str = ", ".join(common_banca_cols)
                query = f"INSERT INTO banca_status ({columns_str}) VALUES ({placeholders});"
                pg_cur.execute(query, row_values)

        # --- 3. MIGRAR TABELA DE MOONBAGS ---
        print("Obtendo colunas e tipos de moonbags em producao...")
        pg_moon_types = get_postgres_columns_with_types(pg_cur, "moonbags")
        if pg_moon_types:
            print("Lendo moonbags do SQLite local...")
            lite_cur.execute("SELECT * FROM moonbags;")
            lite_moon_cols = [desc[0] for desc in lite_cur.description]
            lite_moon_rows = lite_cur.fetchall()
            
            common_moon_cols = [col for col in lite_moon_cols if col in pg_moon_types]
            
            print("Limpando moonbags no Postgres...")
            pg_cur.execute("DELETE FROM moonbags;")
            print("Inserindo moonbags compativeis no Postgres...")
            for row in lite_moon_rows:
                row_dict = dict(zip(lite_moon_cols, row))
                row_values = []
                for col in common_moon_cols:
                    val = row_dict[col]
                    pg_type = pg_moon_types[col]
                    clean_val = clean_value_for_postgres(val, pg_type, col)
                    row_values.append(clean_val)
                
                placeholders = ", ".join(["%s"] * len(common_moon_cols))
                columns_str = ", ".join(common_moon_cols)
                query = f"INSERT INTO moonbags ({columns_str}) VALUES ({placeholders});"
                pg_cur.execute(query, row_values)

        pg_conn.commit()
        print("MIGRATION COMPLETED SUCCESSFULLY! All boolean and timestamp types synced with Railway Postgres!")
        
    except Exception as e:
        pg_conn.rollback()
        print(f"Erro durante a migracao: {e}")
    finally:
        lite_cur.close()
        lite_conn.close()
        pg_cur.close()
        pg_conn.close()

if __name__ == "__main__":
    migrate()
