#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serviço de Banco de Dados Seguro
=================================

Gerencia conexão com o banco de dados PostgreSQL para o sistema de autenticação.

Author: Sistema 1Crypten
Version: 1.0
"""

import logging
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager

from auth_config import auth_settings as settings

logger = logging.getLogger(__name__)

# Criar engine de banco de dados
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=settings.debug
)

# Criar factory de sessões
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para modelos SQLAlchemy
Base = declarative_base()

@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Context manager para obter sessão de banco de dados
    
    Yields:
        Sessão do SQLAlchemy
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Erro na sessão do banco de dados: {e}")
        db.rollback()
        raise
    finally:
        db.close()

def init_db():
    """
    Inicializa o banco de dados criando todas as tabelas
    """
    try:
        # Importar todos os modelos
        from .models_auth import User, UserOKXTokens, AuditLog, UserSession
        
        # Criar tabelas
        Base.metadata.create_all(bind=engine)
        logger.info("Banco de dados inicializado com sucesso")
        return True
    except Exception as e:
        logger.error(f"Erro ao inicializar banco de dados: {e}")
        return False

def drop_db():
    """
    Remove todas as tabelas do banco de dados
    """
    try:
        # Importar todos os modelos
        from .models_auth import User, UserOKXTokens, AuditLog, UserSession
        
        # Remover tabelas
        Base.metadata.drop_all(bind=engine)
        logger.info("Banco de dados resetado com sucesso")
        return True
    except Exception as e:
        logger.error(f"Erro ao resetar banco de dados: {e}")
        return False

def test_connection() -> bool:
    """
    Testa a conexão com o banco de dados
    
    Returns:
        True se a conexão for bem sucedida
    """
    try:
        with engine.connect() as conn:
            result = conn.execute("SELECT 1")
            if result.scalar() == 1:
                logger.info("Conexão com banco de dados estabelecida com sucesso")
                return True
            return False
    except Exception as e:
        logger.error(f"Erro ao conectar ao banco de dados: {e}")
        return False

# Exportar funções e classes
__all__ = [
    'get_db',
    'init_db', 
    'drop_db',
    'test_connection',
    'Base',
    'SessionLocal',
    'engine'
]