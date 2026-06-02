#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migração Simples do Banco de Dados
=================================

Script simples para criar as tabelas de autenticação sem verificações complexas.
"""

import logging
import sys
from pathlib import Path
from sqlalchemy import text

# Adicionar o diretório pai ao path para importar os módulos
sys.path.append(str(Path(__file__).parent))

from database.database_service_secure import get_engine
from database.models_auth import Base

logger = logging.getLogger(__name__)

def create_tables_simple():
    """
    Cria todas as tabelas de autenticação de forma simples
    """
    try:
        # Criar tabelas usando o metadata
        Base.metadata.create_all(bind=get_engine())
        
        logger.info("Tabelas de autenticação criadas com sucesso!")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao criar tabelas: {e}")
        return False

def create_admin_user_simple():
    """
    Cria usuário administrador padrão de forma simples
    """
    try:
        from auth.security.password_handler import password_handler
        from database.models_auth import User
        from sqlalchemy.orm import sessionmaker
        
        engine = get_engine()
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        # Criar sessão
        db = SessionLocal()
        
        try:
            # Verificar se já existe usuário admin
            existing_admin = db.query(User).filter(User.username == 'admin').first()
            
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
                role='admin',  # Usando em vez de is_admin
                email_verified=True,
                created_at='2026-06-01 10:00:00'
            )
            
            db.add(admin_user)
            db.commit()
            
            logger.info("Usuário admin criado com sucesso!")
            logger.info("Username: admin")
            logger.info("Senha: admin123")
            
            return True
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Erro ao criar usuário admin: {e}")
        return False

def main():
    """
    Função principal
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("Iniciando migração simples...")
    
    # Criar tabelas
    if not create_tables_simple():
        logger.error("Falha ao criar tabelas")
        return False
    
    # Criar usuário admin
    if not create_admin_user_simple():
        logger.warning("Falha ao criar usuário admin")
    
    logger.info("Migração concluída com sucesso!")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)