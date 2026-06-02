#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verificação direta do banco de dados
"""

import logging
import sys
from pathlib import Path
from sqlalchemy import text, inspect

# Adicionar o diretório pai ao path para importar os módulos
sys.path.append(str(Path(__file__).parent))

from database.database_service_secure import get_engine

logger = logging.getLogger(__name__)

def check_database_direct():
    """
    Verifica diretamente o banco de dados
    """
    try:
        engine = get_engine()
        inspector = inspect(engine)
        
        print("Engine criado com sucesso")
        
        # Listar todas as tabelas
        tables = inspector.get_table_names()
        print(f"Tabelas encontradas: {tables}")
        
        # Verificar tabelas específicas
        expected_tables = ['users', 'user_okx_tokens', 'audit_log', 'user_sessions']
        
        for table in expected_tables:
            if table in tables:
                print(f"✅ Tabela {table} existe")
                
                # Tentar contar registros
                try:
                    with engine.connect() as conn:
                        result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                        count = result.scalar()
                        print(f"   - Registros: {count}")
                except Exception as e:
                    print(f"   - Erro ao contar registros: {e}")
            else:
                print(f"❌ Tabela {table} não existe")
        
        # Verificar usuário admin
        if 'users' in tables:
            try:
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT username, email FROM users WHERE username = 'admin'"))
                    user = result.fetchone()
                    if user:
                        print(f"✅ Usuário admin existe: {user}")
                    else:
                        print("❌ Usuário admin não encontrado")
            except Exception as e:
                print(f"❌ Erro ao verificar usuário admin: {e}")
        
        return True
        
    except Exception as e:
        print(f"Erro: {e}")
        return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = check_database_direct()
    sys.exit(0 if success else 1)