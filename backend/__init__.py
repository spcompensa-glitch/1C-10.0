#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backend do Sistema 1Crypten
===========================

Módulo principal do backend com configurações e inicialização.

Author: Sistema 1Crypten
Version: 1.0
"""

import logging
from pathlib import Path
import os

# Configuração de logging
def setup_logging():
    """Configura logging do backend"""
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format=log_format,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('backend.log', encoding='utf-8')
        ]
    )

# Inicialização
setup_logging()

# Exportar versão
__version__ = "1.0.0"
__author__ = "Sistema 1Crypten"
__email__ = "contato@1crypten.com"

# Exportar configurações principais
from .config import settings

# Exportar componentes principais
from .database.database_service_secure import get_db
from .auth.middleware import get_current_user, require_permission
from .services.okx_user_service import OKXUserService

# Exportar modelos de dados
from .database.models_auth import User, UserOKXTokens, AuditLog, UserSession

# Exportar serviços de segurança
from .security.encryption import TokenEncryption, get_encryption_instance
from .auth.security.password_handler import PasswordHandler, password_handler
from .auth.jwt_handler import JWTManager, jwt_manager

# Exportar rotas principais
from .routes import auth, tokens

__all__ = [
    # Configurações
    'settings',
    
    # Database
    'get_db',
    
    # Autenticação
    'get_current_user',
    'require_permission',
    'User',
    'UserOKXTokens', 
    'AuditLog',
    'UserSession',
    
    # Segurança
    'TokenEncryption',
    'get_encryption_instance',
    'PasswordHandler',
    'password_handler',
    'JWTManager',
    'jwt_manager',
    
    # Rotas
    'auth',
    'tokens',
    
    # Serviços
    'OKXUserService',
    
    # Versão
    '__version__',
    '__author__',
    '__email__'
]