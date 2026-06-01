#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configurações do Sistema de Autenticação 1Crypten
=================================================

Gerencia todas as configurações do sistema de autenticação.

Author: Sistema 1Crypten
Version: 1.0
"""

import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class AuthSettings(BaseSettings):
    """
    Configurações do sistema de autenticação
    """
    
    # Configurações básicas
    app_name: str = Field(default="1Crypten", env="APP_NAME")
    app_version: str = Field(default="1.0.0", env="APP_VERSION")
    debug: bool = Field(default=False, env="DEBUG")
    secret_key: str = Field(default="your-secret-key-here", env="SECRET_KEY")
    
    # Configurações de banco de dados
    database_url: str = Field(
        default="postgresql://postgres:password@localhost:5432/1crypten",
        env="DATABASE_URL"
    )
    
    # Configurações JWT
    jwt_secret_key: str = Field(default="your-jwt-secret-key", env="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(default=30, env="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    jwt_refresh_token_expire_days: int = Field(default=7, env="JWT_REFRESH_TOKEN_EXPIRE_DAYS")
    
    # Configurações de criptografia
    encryption_password: str = Field(default="your-encryption-password", env="ENCRYPTION_PASSWORD")
    encryption_salt: str = Field(default="your-encryption-salt", env="ENCRYPTION_SALT")
    
    # Configurações de segurança
    password_min_length: int = Field(default=8, env="PASSWORD_MIN_LENGTH")
    password_max_length: int = Field(default=64, env="PASSWORD_MAX_LENGTH")
    bcrypt_rounds: int = Field(default=12, env="BCRYPT_ROUNDS")
    session_timeout_minutes: int = Field(default=120, env="SESSION_TIMEOUT_MINUTES")
    
    # Configurações de logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "allow"
    
    def get_cors_origins(self) -> list:
        """Obtém origens CORS configuradas"""
        if isinstance(self.cors_origins, str):
            return [origin.strip() for origin in self.cors_origins.split(",")]
        return self.cors_origins
    
    def validate_environment(self) -> bool:
        """Valida configurações críticas do ambiente"""
        required_vars = [
            'DATABASE_URL',
            'JWT_SECRET_KEY',
            'ENCRYPTION_PASSWORD',
            'ENCRYPTION_SALT'
        ]
        
        missing_vars = []
        for var in required_vars:
            if not getattr(self, var.lower().replace('_', ''), None):
                missing_vars.append(var)
        
        if missing_vars:
            raise ValueError(f"Variáveis de ambiente obrigatórias ausentes: {', '.join(missing_vars)}")
        
        return True

# Instância global de configurações
@lru_cache()
def get_auth_settings() -> AuthSettings:
    """
    Obtém instância de configurações (cached)
    
    Returns:
        Instância de AuthSettings
    """
    return AuthSettings()

# Exportar instância
auth_settings = get_auth_settings()