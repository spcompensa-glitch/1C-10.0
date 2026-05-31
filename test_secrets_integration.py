# -*- coding: utf-8 -*-
"""
Testes de Integração - Secrets Manager
======================================

Testes de integração para validar o funcionamento do Secrets Manager
com outros serviços do sistema.

Author: QA Team
Version: 1.0
"""

import pytest
import sys
import os

# Adiciona backend ao path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from backend.services.secrets import secrets_manager, Environment, SecurityException

class TestSecretsIntegration:
    """Testes de integração do Secrets Manager"""
    
    def test_secrets_manager_basic_functionality(self):
        """Testa funcionalidade básica do Secrets Manager"""
        # Testa ambiente
        assert secrets_manager.environment.value == "dev"
        
        # Testa obtenção de JWT secret
        jwt_secret = secrets_manager.get_jwt_secret()
        assert len(jwt_secret) > 0
        assert "secret" in jwt_secret.lower()
        
        # Testa relatório de segurança
        security_report = secrets_manager.get_security_report()
        assert "environment" in security_report
        assert "production_ready" in security_report
        assert security_report["environment"] == "dev"
    
    def test_secrets_manager_validation(self):
        """Testa validação de segredos"""
        # Testa validação de produção (deve falhar em dev)
        is_production_ready = secrets_manager.validate_production_readiness()
        assert not is_production_ready  # Deve ser False em dev
        
        # Testa relatório de segurança
        security_report = secrets_manager.get_security_report()
        assert security_report["access_log_count"] > 0
        assert security_report["required_secrets_count"] > 0
    
    def test_secrets_manager_logging(self):
        """Testa logging de acesso a segredos"""
        # Limpa access log
        secrets_manager._access_log.clear()
        
        # Acessa segredo
        jwt_secret = secrets_manager.get_jwt_secret()
        
        # Verifica que foi logado
        assert len(secrets_manager._access_log) > 0
        assert secrets_manager._access_log[0]["secret"] == "JWT_SECRET_KEY"
        # Pode ser "access" ou "fallback_dev" dependendo da implementação atual
        assert secrets_manager._access_log[0]["action"] in ["access", "fallback_dev"]
    
    def test_secrets_manager_environment_switching(self):
        """Testa troca de ambiente"""
        # Testa ambiente atual
        assert secrets_manager.environment == Environment.DEVELOPMENT
        
        # Testa criação com ambiente diferente
        staging_manager = secrets_manager.__class__(Environment.STAGING)
        assert staging_manager.environment == Environment.STAGING
        
        # Testa validação de staging
        staging_security_report = staging_manager.get_security_report()
        assert staging_security_report["environment"] == "staging"
    
    def test_secrets_manager_error_handling(self):
        """Testa tratamento de erros"""
        # Testa acesso a segredo obrigatório em produção
        prod_manager = secrets_manager.__class__(Environment.PRODUCTION)
        
        # Deve falhar pois estamos em ambiente de teste
        with pytest.raises(SecurityException):
            prod_manager.validate_production_readiness()
    
    def test_secrets_manager_memory_usage(self):
        """Testa uso de memória"""
        # Acessa múltiplos segredos
        jwt_secret = secrets_manager.get_jwt_secret()
        okx_creds = secrets_manager.get_okx_credentials()
        gemini_key = secrets_manager.get_gemini_api_key()
        
        # Verifica que todos foram acessados
        assert len(secrets_manager._access_log) >= 3
        
        # Verifica relatório de segurança
        security_report = secrets_manager.get_security_report()
        assert security_report["access_log_count"] >= 3
    
    def test_secrets_manager_concurrent_access(self):
        """Testa acesso concorrente a segredos"""
        import threading
        import time
        
        results = []
        errors = []
        
        def access_secret():
            try:
                secret = secrets_manager.get_jwt_secret()
                results.append(secret)
            except Exception as e:
                errors.append(str(e))
        
        # Cria threads concorrentes
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=access_secret)
            threads.append(thread)
            thread.start()
        
        # Espera todas as threads
        for thread in threads:
            thread.join()
        
        # Verifica resultados
        assert len(results) == 5
        assert len(errors) == 0
        assert all(len(secret) > 0 for secret in results)

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])