#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para inicializar o banco de dados de autenticação Railway
"""

import os
import sys
import logging
from pathlib import Path

# Adiciona backend ao path
backend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
sys.path.append(backend_path)

# Importar serviços
from backend.config import settings
from backend.database.database_service_secure import get_engine, Base as AuthBase
from backend.database import models_auth  # noqa: F401 - registra modelos no metadata
from backend.auth.security.password_handler import password_handler
from sqlalchemy import text as _sql_text
from datetime import datetime as _dt

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AuthDBInit")

def init_auth_db():
    """Cria tabelas de auth e garante admin/admin123"""
    try:
        engine = get_engine()
        logger.info(f"🔐 [AUTH] DATABASE_URL: {engine.url.drivername}://***")
        
        # Criar tabelas
        AuthBase.metadata.create_all(bind=engine)
        logger.info("✅ [AUTH] Tabelas criadas com sucesso")
        
        # Garantir usuário admin
        pwd_hash = password_handler.hash_password("admin123", rounds=12)
        now = _dt.utcnow()
        dialect = engine.dialect.name
        
        with engine.begin() as conn:
            if dialect == "postgresql":
                # UPSERT nativo do Postgres
                conn.execute(_sql_text("""
                    INSERT INTO users (username, email, password_hash, is_active, role, created_at, updated_at)
                    VALUES (:username, :email, :password_hash, :is_active, :role, :created_at, :updated_at)
                    ON CONFLICT (username) DO UPDATE
                      SET password_hash = EXCLUDED.password_hash,
                          email = EXCLUDED.email,
                          is_active = EXCLUDED.is_active,
                          role = EXCLUDED.role,
                          updated_at = EXCLUDED.updated_at
                """), {
                    "username": "admin",
                    "email": "admin@1crypten.com",
                    "password_hash": pwd_hash,
                    "is_active": True,
                    "role": "admin",
                    "created_at": now,
                    "updated_at": now,
                })
                logger.info("✅ [AUTH] Usuário admin garantido (Postgres UPSERT)")
            else:
                # SQLite
                existing = conn.execute(
                    _sql_text("SELECT id FROM users WHERE username = :u"),
                    {"u": "admin"},
                ).scalar()
                if not existing:
                    conn.execute(_sql_text("""
                        INSERT INTO users (username, email, password_hash, is_active, role, created_at, updated_at)
                        VALUES (:username, :email, :password_hash, :is_active, :role, :created_at, :updated_at)
                    """), {
                        "username": "admin",
                        "email": "admin@1crypten.com",
                        "password_hash": pwd_hash,
                        "is_active": True,
                        "role": "admin",
                        "created_at": now,
                        "updated_at": now,
                    })
                    logger.info("✅ [AUTH] Usuário admin criado (SQLite)")
                else:
                    conn.execute(
                        _sql_text("""
                            UPDATE users
                            SET password_hash = :h, email = :e, is_active = 1, role = 'admin', updated_at = :u
                            WHERE username = 'admin'
                        """),
                        {"h": pwd_hash, "e": "admin@1crypten.com", "u": now},
                    )
                    logger.info("✅ [AUTH] Usuário admin atualizado (SQLite)")
        
        logger.info("🎉 [AUTH] Banco de dados inicializado com sucesso!")
        
    except Exception as e:
        logger.error(f"❌ [AUTH] Erro ao inicializar banco: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise

if __name__ == "__main__":
    init_auth_db()