#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serviço de Banco de Dados Seguro
=================================

Gerencia conexão com o banco de dados para o sistema de autenticação.

Author: Sistema 1Crypten
Version: 1.0
"""

import logging
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from config import settings

logger = logging.getLogger(__name__)

# Criar engine de banco de dados (lazy loading)
engine = None
SessionLocal = None
Base = declarative_base()

def get_engine():
    """Retorna engine de banco de dados (cria se necessário)"""
    global engine, SessionLocal
    if engine is None:
        db_url = settings.DATABASE_URL
        # Converter string de conexão assíncrona para síncrona se necessário para o SQLAlchemy tradicional
        if db_url and "sqlite+aiosqlite" in db_url:
            db_url = db_url.replace("sqlite+aiosqlite", "sqlite")
        # Ignorar placeholders inválidos do Windows
        if db_url and "<sua_url_do_postgres>" in db_url:
            logger.warning(f"DATABASE_URL contém placeholder inválido. Usando SQLite local.")
            db_url = "sqlite:///./auth.db"
        # Configurar engine baseado no tipo de banco de dados
        if db_url.startswith('sqlite'):
            engine = create_engine(
                db_url,
                connect_args={"check_same_thread": False},
                echo=settings.DEBUG
            )
        else:
            engine = create_engine(
                db_url,
                pool_pre_ping=True,
                pool_recycle=300,
                echo=settings.DEBUG
            )
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine

def get_db() -> Generator[Session, None, None]:
    """
    Gerador para obter sessão de banco de dados (compatível com FastAPI Depends)

    Yields:
        Sessão do SQLAlchemy
    """
    # Garantir que o engine foi inicializado
    get_engine()
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
        Base.metadata.create_all(bind=get_engine())
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
        Base.metadata.drop_all(bind=get_engine())
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
        with get_engine().connect() as conn:
            result = conn.execute(text("SELECT 1"))
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