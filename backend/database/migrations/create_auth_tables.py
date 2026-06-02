#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migração do Banco de Dados - Tabelas de Autenticação
====================================================

Script para criar as tabelas de autenticação e usuários.

Author: Sistema 1Crypten
Version: 1.0
"""

import logging
import sys
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

# Adicionar o diretório pai ao path para importar os módulos
sys.path.append(str(Path(__file__).parent.parent.parent))

from database.database_service_secure import get_engine, get_db
from database.models_auth import (
    Base,
    User,
    UserOKXTokens,
    AuditLog,
    UserSession
)

logger = logging.getLogger(__name__)

def create_tables():
    """
    Cria todas as tabelas de autenticação
    """
    try:
        # Criar tabelas
        Base.metadata.create_all(bind=get_engine())

        logger.info("Tabelas de autenticação criadas com sucesso!")
        return True

    except SQLAlchemyError as e:
        logger.error(f"Erro ao criar tabelas: {e}")
        return False

def check_tables_exist():
    """
    Verifica se as tabelas já existem
    """
    try:
        from database.database_service_secure import get_engine
        engine = get_engine()
        
        # Lista das tabelas esperadas
        expected_tables = ['users', 'user_okx_tokens', 'audit_log', 'user_sessions']

        # Verificar se as tabelas existem
        tables_exist = {}
        for table in expected_tables:
            try:
                with engine.connect() as conn:
                    result = conn.execute(text(f"""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables
                            WHERE table_schema = 'public'
                            AND table_name = '{table}'
                        )
                    """)).scalar()
                    tables_exist[table] = result
                    logger.info(f"Tabela '{table}': {'Existe' if result else 'Não existe'}")
            except Exception as e:
                logger.error(f"Erro ao verificar tabela '{table}': {e}")
                tables_exist[table] = False

        return tables_exist

    except Exception as e:
        logger.error(f"Erro ao verificar tabelas: {e}")
        return {}

def create_admin_user():
    """
    Cria usuário administrador padrão
    """
    try:
        from auth.security.password_handler import password_handler
        from database.database_service_secure import get_engine

        engine = get_engine()

        # Verificar se já existe usuário admin
        with engine.connect() as conn:
            existing_admin = conn.execute(text("""
                SELECT id FROM users WHERE username = 'admin'
            """)).scalar()

        if existing_admin:
            logger.info("Usuário admin já existe")
            return True

        # Criar hash da senha
        password_hash = password_handler.hash_password('admin123', rounds=12)

        # Criar usuário admin
        admin_user = User(
            username='admin',
            email='admin@1crypten.com',
            password_hash=password_hash,
            is_active=True,
            is_admin=True,
            email_verified=True,
            created_at='2026-06-01 10:00:00'
        )

        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO users (username, email, password_hash, is_active, is_admin, email_verified, created_at)
                VALUES (:username, :email, :password_hash, :is_active, :is_admin, :email_verified, :created_at)
            """), {
                'username': admin_user.username,
                'email': admin_user.email,
                'password_hash': password_hash,
                'is_active': admin_user.is_active,
                'is_admin': admin_user.is_admin,
                'email_verified': admin_user.email_verified,
                'created_at': admin_user.created_at
            })
            conn.commit()

        logger.info("Usuário admin criado com sucesso!")
        logger.info("Username: admin")
        logger.info("Senha: admin123")

        return True

    except Exception as e:
        logger.error(f"Erro ao criar usuário admin: {e}")
        return False

def create_user_tables_indexes():
    """
    Cria índices para melhor performance
    """
    try:
        from database.database_service_secure import get_engine

        engine = get_engine()

        # Índices para tabela users
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
            "CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active)",
            "CREATE INDEX IF NOT EXISTS idx_users_is_admin ON users(is_admin)",

            # Índices para tabela user_okx_tokens
            "CREATE INDEX IF NOT EXISTS idx_user_okx_tokens_user_id ON user_okx_tokens(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_okx_tokens_exchange_name ON user_okx_tokens(exchange_name)",
            "CREATE INDEX IF NOT EXISTS idx_user_okx_tokens_is_active ON user_okx_tokens(is_active)",
            "CREATE INDEX IF NOT EXISTS idx_user_okx_tokens_created_at ON user_okx_tokens(created_at)",

            # Índices para tabela audit_log
            "CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action)",
            "CREATE INDEX IF NOT EXISTS idx_audit_log_resource ON audit_log(resource)",
            "CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_audit_log_ip_address ON audit_log(ip_address)",

            # Índices para tabela user_sessions
            "CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_sessions_session_type ON user_sessions(session_type)",
            "CREATE INDEX IF NOT EXISTS idx_user_sessions_is_active ON user_sessions(is_active)",
            "CREATE INDEX IF NOT EXISTS idx_user_sessions_created_at ON user_sessions(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at ON user_sessions(expires_at)"
        ]

        for index_sql in indexes:
            try:
                with engine.connect() as conn:
                    conn.execute(text(index_sql))
                    logger.info(f"Índice criado com sucesso")
            except Exception as e:
                logger.warning(f"Índice já existe ou erro ao criar: {e}")

        logger.info("Índices criados com sucesso!")
        return True

    except Exception as e:
        logger.error(f"Erro ao criar índices: {e}")
        return False

def migrate_database():
    """
    Executa a migração completa do banco de dados
    """
    logger.info("Iniciando migração do banco de dados...")

    # Tentar verificar tabelas existentes
    try:
        tables_exist = check_tables_exist()
        if tables_exist:
            if not all(tables_exist.values()):
                logger.info("Criando tabelas de autenticação...")
                if not create_tables():
                    logger.error("Falha ao criar tabelas")
                    return False
            else:
                logger.info("Todas as tabelas já existem")
        else:
            logger.info("Não foi possível verificar tabelas, criando...")
            if not create_tables():
                logger.error("Falha ao criar tabelas")
                return False
    except Exception as e:
        logger.info(f"Erro ao verificar tabelas, criando novas: {e}")
        if not create_tables():
            logger.error("Falha ao criar tabelas")
            return False

    # Criar índices
    logger.info("Criando índices...")
    if not create_user_tables_indexes():
        logger.warning("Falha ao criar alguns índices")

    # Criar usuário admin
    logger.info("Criando usuário admin...")
    if not create_admin_user():
        logger.warning("Falha ao criar usuário admin")

    logger.info("Migração concluída com sucesso!")
    return True

def rollback_migration():
    """
    Desfaz a migração (apaga as tabelas)
    """
    try:
        logger.info("Desfazendo migração...")
        from database.database_service_secure import get_engine

        engine = get_engine()

        # Apagar tabelas em ordem reversa para evitar problemas de dependência
        tables_to_drop = [
            'user_sessions',
            'audit_log',
            'user_okx_tokens',
            'users'
        ]

        for table in tables_to_drop:
            try:
                with engine.connect() as conn:
                    conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                    logger.info(f"Tabela {table} apagada com sucesso")
            except Exception as e:
                logger.warning(f"Erro ao apagar tabela {table}: {e}")

        logger.info("Migração desfeita com sucesso!")
        return True

    except Exception as e:
        logger.error(f"Erro ao desfazer migração: {e}")
        return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Gerenciador de migração do banco de dados")
    parser.add_argument("action", choices=["migrate", "rollback"], help="Ação a ser executada")
    parser.add_argument("--verbose", "-v", action="store_true", help="Modo verbose")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    else:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    if args.action == "migrate":
        success = migrate_database()
    elif args.action == "rollback":
        success = rollback_migration()
    
    sys.exit(0 if success else 1)