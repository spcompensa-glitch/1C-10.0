# -*- coding: utf-8 -*-
"""
Testes de Integração - Autenticação
====================================

Testes de integração para validar o funcionamento do sistema de
autenticação com outros serviços do sistema.

Author: QA Team
Version: 1.0
"""

import pytest
import sys
import os
import time
import jwt

# Adiciona backend ao path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from backend.services.secrets import secrets_manager

class TestAuthIntegration:
    """Testes de integração de autenticação"""
    
    def test_jwt_generation_and_validation(self):
        """Testa geração e validação de JWT"""
        # Obtém chave JWT
        jwt_secret = secrets_manager.get_jwt_secret()
        
        # Gera token JWT
        payload = {
            "user_id": "test_user",
            "username": "test_username",
            "exp": int(time.time()) + 3600,  # 1 hora de expiração
            "iat": int(time.time())
        }
        
        token = jwt.encode(payload, jwt_secret, algorithm="HS256")
        
        # Valida token
        decoded = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        
        # Verifica payload
        assert decoded["user_id"] == "test_user"
        assert decoded["username"] == "test_username"
        assert "exp" in decoded
        assert "iat" in decoded
    
    def test_jwt_expiration(self):
        """Testa expiração de JWT"""
        jwt_secret = secrets_manager.get_jwt_secret()
        
        # Gera token expirado
        payload = {
            "user_id": "test_user",
            "exp": int(time.time()) - 3600,  # 1 hora atrás
            "iat": int(time.time())
        }
        
        token = jwt.encode(payload, jwt_secret, algorithm="HS256")
        
        # Deve falhar ao validar token expirado
        with pytest.raises(jwt.ExpiredSignatureError):
            jwt.decode(token, jwt_secret, algorithms=["HS256"])
    
    def test_jwt_invalid_signature(self):
        """Testa assinatura JWT inválida"""
        jwt_secret = secrets_manager.get_jwt_secret()
        
        # Gera token com chave diferente
        payload = {
            "user_id": "test_user",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time())
        }
        
        token = jwt.encode(payload, "wrong_secret", algorithm="HS256")
        
        # Deve falhar ao validar com chave incorreta
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(token, jwt_secret, algorithms=["HS256"])
    
    def test_jwt_claims_validation(self):
        """Testa validação de claims JWT"""
        jwt_secret = secrets_manager.get_jwt_secret()
        
        # Gera token sem claims obrigatórias
        payload = {
            "user_id": "test_user",
            # sem 'exp' ou 'iat'
        }
        
        token = jwt.encode(payload, jwt_secret, algorithm="HS256")
        
        # Deve falhar ao validar sem claims obrigatórias
        with pytest.raises(jwt.InvalidTokenError):
            jwt.decode(token, jwt_secret, algorithms=["HS256"], options={"require": ["exp", "iat"]})
    
    def test_secrets_manager_with_jwt(self):
        """Testa integração entre Secrets Manager e JWT"""
        # Obtém chave JWT
        jwt_secret = secrets_manager.get_jwt_secret()
        
        # Verifica que a chave não está vazia
        assert len(jwt_secret) >= 32
        
        # Loga acesso
        assert len(secrets_manager._access_log) > 0
        
        # Verifica que foi logado corretamente
        last_log = secrets_manager._access_log[-1]
        assert last_log["secret"] == "JWT_SECRET_KEY"
        assert last_log["action"] in ["access", "fallback_dev"]
    
    def test_multiple_jwt_tokens(self):
        """Testa geração múltipla de JWT tokens"""
        jwt_secret = secrets_manager.get_jwt_secret()
        
        # Gera múltiplos tokens
        tokens = []
        for i in range(5):
            payload = {
                "user_id": f"user_{i}",
                "username": f"username_{i}",
                "exp": int(time.time()) + 3600,
                "iat": int(time.time())
            }
            
            token = jwt.encode(payload, jwt_secret, algorithm="HS256")
            tokens.append(token)
            
            # Valida token
            decoded = jwt.decode(token, jwt_secret, algorithms=["HS256"])
            assert decoded["user_id"] == f"user_{i}"
        
        # Verifica que todos são diferentes
        assert len(set(tokens)) == 5
        
        # Verifica que todos são válidos
        for token in tokens:
            decoded = jwt.decode(token, jwt_secret, algorithms=["HS256"])
            assert "user_id" in decoded
            assert "username" in decoded
    
    def test_jwt_with_custom_claims(self):
        """Testa JWT com claims customizadas"""
        jwt_secret = secrets_manager.get_jwt_secret()
        
        # Gera token com claims customizadas
        payload = {
            "user_id": "test_user",
            "username": "test_username",
            "role": "admin",
            "permissions": ["read", "write", "delete"],
            "metadata": {
                "device": "web",
                "location": "BR"
            },
            "exp": int(time.time()) + 3600,
            "iat": int(time.time())
        }
        
        token = jwt.encode(payload, jwt_secret, algorithm="HS256")
        
        # Valida token
        decoded = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        
        # Verifica claims customizadas
        assert decoded["role"] == "admin"
        assert decoded["permissions"] == ["read", "write", "delete"]
        assert decoded["metadata"]["device"] == "web"
        assert decoded["metadata"]["location"] == "BR"
    
    def test_jwt_refresh_mechanism(self):
        """Testa mecanismo de refresh de JWT"""
        jwt_secret = secrets_manager.get_jwt_secret()
        
        # Gera token curto
        payload = {
            "user_id": "test_user",
            "username": "test_username",
            "exp": int(time.time()) + 60,  # 1 minuto
            "iat": int(time.time()),
            "type": "access"
        }
        
        access_token = jwt.encode(payload, jwt_secret, algorithm="HS256")
        
        # Gera refresh token
        refresh_payload = {
            "user_id": "test_user",
            "exp": int(time.time()) + 86400,  # 24 horas
            "iat": int(time.time()),
            "type": "refresh"
        }
        
        refresh_token = jwt.encode(refresh_payload, jwt_secret, algorithm="HS256")
        
        # Valida access token
        decoded_access = jwt.decode(access_token, jwt_secret, algorithms=["HS256"])
        assert decoded_access["type"] == "access"
        
        # Valida refresh token
        decoded_refresh = jwt.decode(refresh_token, jwt_secret, algorithms=["HS256"])
        assert decoded_refresh["type"] == "refresh"
        assert decoded_refresh["exp"] > decoded_access["exp"]

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])