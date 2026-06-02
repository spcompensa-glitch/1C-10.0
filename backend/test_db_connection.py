#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testar conexão com o banco de dados
"""

import os
import logging
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_connection():
    """
    Testar conexão com o banco de dados
    """
    try:
        # Obter URL do banco de dados
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            raise ValueError("DATABASE_URL não encontrada")
        
        logger.info(f"Tentando conectar com: {database_url}")
        
        # Criar engine
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=300,
            echo=True  # Mostrar queries SQL para debug
        )
        
        # Testar conexão
        with engine.connect() as conn:
            logger.info("✅ Conexão estabelecida com sucesso")
            
            # Executar query simples
            result = conn.execute("SELECT 1")
            value = result.scalar()
            logger.info(f"✅ Query de teste executada com resultado: {value}")
            
            # Listar tabelas
            result = conn.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            tables = [row[0] for row in result.fetchall()]
            logger.info(f"Tabelas encontradas: {tables}")
            
            # Verificar tabela users
            if 'users' in tables:
                result = conn.execute("SELECT COUNT(*) FROM users")
                count = result.scalar()
                logger.info(f"✅ Tabela users existe com {count} registros")
                
                # Verificar usuário admin
                result = conn.execute("SELECT username, email FROM users WHERE username = 'admin'")
                admin = result.fetchone()
                if admin:
                    logger.info(f"✅ Usuário admin encontrado: {admin}")
                else:
                    logger.info("❌ Usuário admin não encontrado")
            else:
                logger.warning("❌ Tabela users não encontrada")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Erro ao conectar ao banco de dados: {e}")
        return False

if __name__ == "__main__":
    success = test_connection()
    exit(0 if success else 1)