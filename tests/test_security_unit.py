# -*- coding: utf-8 -*-
"""
Testes de Segurança Unitária - Suite Completa
=============================================

Suite de testes unitários para validar:
1. JWT Security
2. Authentication Service
3. Secrets Manager
4. Proteção contra SQL Injection
5. Cache Security

Author: Security Testing Team
Version: 1.0

Coverage:
- JWT token generation/validation
- Authentication flows
- Secrets management
- SQL injection protection
- Cache security
"""

import pytest
import asyncio
import jwt
import time
import hashlib
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta
from typing import Dict, Any

# Importa módulos de segurança
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.secrets import secrets_manager, SecretsManager, Environment
from backend.services.auth_service import auth_service, get_current_user
from backend.services.safe_cache import SafeCache, get_cache, cached
from backend.services.database_service_secure import SQLInjectionValidator, SecureQueryBuilder

class TestJWTSecurity:
    """Testes de segurança JWT"""
    
    def test_jwt_secret_validation(self):
        """Testa validação de JWT Secret"""
        # Testa com ambiente de desenvolvimento
        dev_secrets = SecretsManager(Environment.DEVELOPMENT)
        jwt_secret = dev_secrets.get_jwt_secret()
        assert len(jwt_secret) >= 32, "JWT Secret deve ter no mínimo 32 caracteres"
        
        # Testa com ambiente de produção
        with patch.dict(os.environ, {'JWT_SECRET_KEY': 'test_secret_key_32_chars_long_enough'}):
            prod_secrets = SecretsManager(Environment.PRODUCTION)
            jwt_secret = prod_secrets.get_jwt_secret()
            assert jwt_secret == 'test_secret_key_32_chars_long_enough'
    
    def test_jwt_token_generation(self):
        """Testa geração de JWT tokens"""
        token_data = {
            "sub": "test_user",
            "role": "admin",
            "exp": datetime.utcnow() + timedelta(minutes=60)
        }
        
        # Gera token
        token = auth_service.create_access_token(data=token_data)
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Valida token
        payload = jwt.decode(token, auth_service.SECRET_KEY, algorithms=[auth_service.ALGORITHM])
        assert payload["sub"] == "test_user"
        assert payload["role"] == "admin"
    
    def test_jwt_token_expiration(self):
        """Testa expiração de JWT tokens"""
        # Gera token com expiração rápida
        token_data = {
            "sub": "test_user",
            "exp": datetime.utcnow() - timedelta(minutes=1)
        }
        
        token = auth_service.create_access_token(data=token_data, expires_delta=timedelta(minutes=-1))
        
        # Deve falhar na validação
        with pytest.raises(jwt.ExpiredSignatureError):
            jwt.decode(token, auth_service.SECRET_KEY, algorithms=[auth_service.ALGORITHM])
    
    def test_jwt_token_forgery(self):
        """Testa proteção contra falsificação de JWT tokens"""
        # Gera token válido
        token_data = {"sub": "test_user"}
        token = auth_service.create_access_token(data=token_data)
        
        # Modifica token
        forged_token = token[:-5] + "abcde"
        
        # Deve falhar na validação
        with pytest.raises(jwt.InvalidTokenError):
            jwt.decode(forged_token, auth_service.SECRET_KEY, algorithms=[auth_service.ALGORITHM])

class TestAuthenticationSecurity:
    """Testes de segurança de autenticação"""
    
    @pytest.mark.asyncio
    async def test_fortress_bypass_production(self):
        """Testa que Fortress Bypass não funciona em produção"""
        with patch.dict(os.environ, {'ENVIRONMENT': 'prod'}):
            from backend.services.secrets import secrets_manager
            
            # Simula token inválido em produção
            invalid_token = "invalid_token_123"
            
            # Deve falhar em produção
            with pytest.raises(Exception):
                await get_current_user(invalid_token)
    
    @pytest.mark.asyncio
    async def test_fortress_bypass_development(self):
        """Testa que Fortress Bypass funciona em desenvolvimento"""
        with patch.dict(os.environ, {'ENVIRONMENT': 'dev', 'DEBUG': 'true'}):
            from backend.services.secrets import secrets_manager
            
            # Simula token inválido em desenvolvimento
            invalid_token = "invalid_token_123"
            
            # Deve funcionar em desenvolvimento
            user = await get_current_user(invalid_token)
            assert user is not None
    
    @pytest.mark.asyncio
    async def test_user_authentication_flow(self):
        """Testa fluxo completo de autenticação de usuário"""
        # Registra usuário de teste
        user_data = {
            "username": "test_user",
            "password": "test_password",
            "email": "test@example.com",
            "role": "user"
        }
        
        success = await auth_service.register_user(user_data)
        assert success is True
        
        # Login válido
        token = auth_service.create_access_token(data={"sub": "test_user"})
        
        # Valida token
        payload = jwt.decode(token, auth_service.SECRET_KEY, algorithms=[auth_service.ALGORITHM])
        assert payload["sub"] == "test_user"
        
        # Obtém usuário
        user = await auth_service.get_user("test_user")
        assert user is not None
        assert user.username == "test_user"

class TestSecretsManager:
    """Testes de gerenciamento de segredos"""
    
    def test_secrets_manager_environment_validation(self):
        """Testa validação de ambiente"""
        # Testa ambiente de desenvolvimento
        dev_secrets = SecretsManager(Environment.DEVELOPMENT)
        assert dev_secrets.environment == Environment.DEVELOPMENT
        
        # Testa ambiente de produção
        prod_secrets = SecretsManager(Environment.PRODUCTION)
        assert prod_secrets.environment == Environment.PRODUCTION
    
    def test_secrets_validation_production(self):
        """Testa validação de segredos em produção"""
        # Configura variáveis de ambiente obrigatórias
        required_secrets = {
            "JWT_SECRET_KEY": "test_secret_32_chars_long_enough",
            "OKX_API_KEY_MASTER": "test_api_key",
            "OKX_API_SECRET_MASTER": "test_api_secret",
            "OKX_PASSPHRASE_MASTER": "test_passphrase",
            "DATABASE_URL": "postgresql://localhost/test",
            "ADMIN_API_KEY": "test_admin_key"
        }
        
        with patch.dict(os.environ, required_secrets):
            prod_secrets = SecretsManager(Environment.PRODUCTION)
            assert prod_secrets.validate_production_readiness() is True
    
    def test_secrets_validation_missing_required(self):
        """Testa validação quando segredos obrigatórios estão faltando"""
        # Remove segredos obrigatórios
        with patch.dict(os.environ, {}, clear=True):
            prod_secrets = SecretsManager(Environment.PRODUCTION)
            assert prod_secrets.validate_production_readiness() is False
    
    def test_secrets_access_logging(self):
        """Testa logging de acesso a segredos"""
        # Configura segredo
        with patch.dict(os.environ, {"JWT_SECRET_KEY": "test_secret"}):
            secrets = SecretsManager(Environment.DEVELOPMENT)
            
            # Acessa segredo
            jwt_secret = secrets.get_jwt_secret()
            
            # Verifica que acesso foi logado
            assert len(secrets._access_log) > 0
            assert secrets._access_log[0]["secret"] == "JWT_SECRET_KEY"

class TestSQLInjectionProtection:
    """Testes de proteção contra SQL Injection"""
    
    def test_sql_injection_validator_safe_input(self):
        """Testa validação de inputs seguros"""
        validator = SQLInjectionValidator()
        
        # Inputs seguros
        safe_inputs = [
            "normal_text",
            "user123",
            "email@example.com",
            "12345",
            "some_value"
        ]
        
        for input_text in safe_inputs:
            assert validator.is_safe_input(input_text) is True
    
    def test_sql_injection_validator_malicious_input(self):
        """Testa detecção de inputs maliciosos"""
        validator = SQLInjectionValidator()
        
        # Inputs maliciosos
        malicious_inputs = [
            "SELECT * FROM users",
            "DROP TABLE users",
            "1 OR 1=1",
            "UNION SELECT",
            "'; DROP TABLE users; --",
            "<script>alert('xss')</script>"
        ]
        
        for input_text in malicious_inputs:
            assert validator.is_safe_input(input_text) is False
    
    def test_sql_injection_validator_column_names(self):
        """Testa validação de nomes de colunas"""
        validator = SQLInjectionValidator()
        
        # Nomes de colunas válidos
        valid_columns = ["username", "email", "created_at", "user_id"]
        for col in valid_columns:
            assert validator.is_safe_input(col, "column") is True
        
        # Nomes de colunas inválidos
        invalid_columns = ["username; DROP TABLE users", "email OR 1=1", "created_at--"]
        for col in invalid_columns:
            assert validator.is_safe_input(col, "column") is False
    
    def test_secure_query_builder(self):
        """Testa construtor de queries seguro"""
        builder = SecureQueryBuilder()
        
        # Testa query SELECT segura
        query, params = builder.build_select(
            table="users",
            columns=["id", "username", "email"],
            conditions={"username": "test_user"}
        )
        
        assert "SELECT id, username, email FROM users WHERE username = :username" in query
        assert params["username"] == "test_user"
        
        # Testa query UPDATE segura
        query, params = builder.build_update(
            table="users",
            data={"email": "new@example.com"},
            conditions={"id": 1}
        )
        
        assert "UPDATE users SET email = :set_email WHERE id = :where_id" in query
        assert params["set_email"] == "new@example.com"
        assert params["where_id"] == 1
    
    def test_secure_query_builder_malicious_input(self):
        """Testa rejeição de queries com input malicioso"""
        builder = SecureQueryBuilder()
        
        # Tentativa de SQL Injection em tabela
        with pytest.raises(ValueError):
            builder.build_select(
                table="users; DROP TABLE users",
                columns=["id"],
                conditions={}
            )
        
        # Tentativa de SQL Injection em coluna
        with pytest.raises(ValueError):
            builder.build_select(
                table="users",
                columns=["id; DROP TABLE users"],
                conditions={}
            )

class TestCacheSecurity:
    """Testes de segurança do cache"""
    
    def test_cache_initialization(self):
        """Testa inicialização do cache"""
        cache = SafeCache(max_size_mb=10, default_ttl=60)
        assert cache.max_size_bytes == 10 * 1024 * 1024
        assert cache.default_ttl == 60
        assert len(cache._cache) == 0
    
    def test_cache_set_and_get(self):
        """Testa operações básicas de cache"""
        cache = SafeCache(max_size_mb=10, default_ttl=60)
        
        # Armazena valor
        success = cache.set("test_key", "test_value")
        assert success is True
        
        # Recupera valor
        value = cache.get("test_key")
        assert value == "test_value"
    
    def test_cache_expiration(self):
        """Testa expiração de cache"""
        cache = SafeCache(max_size_mb=10, default_ttl=1)  # 1 segundo TTL
        
        # Armazena valor
        cache.set("test_key", "test_value")
        
        # Deve estar disponível imediatamente
        value = cache.get("test_key")
        assert value == "test_value"
        
        # Espera expiração
        time.sleep(2)
        
        # Deve estar expirado
        value = cache.get("test_key")
        assert value is None
    
    def test_cache_memory_management(self):
        """Testa gerenciamento de memória do cache"""
        cache = SafeCache(max_size_mb=1)  # 1MB
        
        # Armazena dados até atingir limite
        large_data = "x" * 1024 * 1024  # 1MB
        success = cache.set("large_key", large_data)
        
        # Verifica se foi armazenado
        if success:
            # Deve ter sido armazenado
            value = cache.get("large_key")
            assert value == large_data
    
    @pytest.mark.asyncio
    async def test_cache_decorator(self):
        """Testa decorator de cache"""
        
        @cached(ttl=60)
        async def test_function(x, y):
            return x + y
        
        # Primeira chamada - deve calcular
        result1 = await test_function(1, 2)
        assert result1 == 3
        
        # Segunda chamada - deve usar cache
        result2 = await test_function(1, 2)
        assert result2 == 3
    
    def test_cache_security_events(self):
        """Testa logging de eventos de segurança do cache"""
        cache = SafeCache(max_size_mb=10, default_ttl=60)
        
        # Armazena valor
        cache.set("security_test", "sensitive_data")
        
        # Recupera valor
        value = cache.get("security_test")
        assert value == "sensitive_data"
        
        # Verifica que acesso foi logado
        stats = cache.get_stats()
        assert stats['hits'] > 0

class TestIntegrationSecurity:
    """Testes de segurança integrada"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_security_flow(self):
        """Testa fluxo completo de segurança"""
        # 1. Registra usuário
        user_data = {
            "username": "security_test_user",
            "password": "secure_password_123",
            "email": "security@example.com",
            "role": "user"
        }
        
        success = await auth_service.register_user(user_data)
        assert success is True
        
        # 2. Gera token JWT
        token = auth_service.create_access_token(data={"sub": "security_test_user"})
        assert len(token) > 0
        
        # 3. Valida token
        payload = jwt.decode(token, auth_service.SECRET_KEY, algorithms=[auth_service.ALGORITHM])
        assert payload["sub"] == "security_test_user"
        
        # 4. Testa cache
        cache = get_cache()
        cache.set("security_test", "integration_test_data")
        cached_data = cache.get("security_test")
        assert cached_data == "integration_test_data"
        
        # 5. Testa proteção contra SQL Injection
        validator = SQLInjectionValidator()
        assert validator.is_safe_input("security_test_user") is True
        assert validator.is_safe_input("SELECT * FROM users") is False

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])