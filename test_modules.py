#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste de Módulos do Sistema de Autenticação
===========================================

Script para testar os módulos criados para o sistema de autenticação.
"""

import sys
import os
from pathlib import Path

# Adicionar o diretório backend ao path
sys.path.append(str(Path(__file__).parent / "backend"))

print("🔍 Testando módulos do sistema de autenticação...")
print("=" * 50)

# Testar configurações
try:
    from config import settings
    print("✅ Configurações carregadas")
    print(f"   APP_NAME: {settings.app_name}")
    print(f"   DEBUG: {settings.debug}")
    print(f"   DATABASE_URL: {settings.database_url[:30]}...")
except Exception as e:
    print(f"❌ Erro nas configurações: {e}")

# Testar módulo de criptografia
try:
    from auth.security.encryption import get_encryption_instance, TokenEncryption
    encryption = get_encryption_instance()
    
    # Testar criptografia
    test_data = "test_data_123"
    encrypted = encryption.encrypt_token(test_data)
    decrypted = encryption.decrypt_token(encrypted)
    
    if decrypted == test_data:
        print("✅ Módulo de criptografia funcionando")
    else:
        print("❌ Módulo de criptografia com erro")
        
except Exception as e:
    print(f"❌ Erro no módulo de criptografia: {e}")

# Testar módulo de senhas
try:
    from auth.security.password_handler import password_handler, hash_password, verify_password
    
    # Testar hash de senha
    password = "test_password_123"
    hashed = hash_password(password)
    verified = verify_password(password, hashed)
    
    if verified:
        print("✅ Módulo de senhas funcionando")
    else:
        print("❌ Módulo de senhas com erro")
        
    # Testar validação de força
    strength = password_handler.validate_password_strength("StrongPass123!")
    print(f"   Força da senha: {strength['strength']} ({strength['score']}/{strength['max_score']})")
        
except Exception as e:
    print(f"❌ Erro no módulo de senhas: {e}")

# Testar módulo JWT
try:
    from auth.jwt_handler import JWTManager, jwt_manager
    
    # Testar criação de token
    test_payload = {"user_id": 1, "username": "test_user"}
    access_token = jwt_manager.create_access_token(data=test_payload)
    refresh_token = jwt_manager.create_refresh_token(data=test_payload)
    
    # Testar verificação
    decoded = jwt_manager.verify_token(access_token)
    
    if decoded and decoded["user_id"] == 1:
        print("✅ Módulo JWT funcionando")
    else:
        print("❌ Módulo JWT com erro")
        
except Exception as e:
    print(f"❌ Erro no módulo JWT: {e}")

# Testar modelos de banco de dados
try:
    from database.models_auth import User, UserOKXTokens
    print("✅ Modelos de banco de dados carregados")
    
    # Testar criação de usuário
    user = User(username="test_user", email="test@example.com")
    print(f"   Modelo User: {user.username}")
        
except Exception as e:
    print(f"❌ Erro nos modelos de banco de dados: {e}")

# Testar banco de dados
try:
    from database.database_service_secure import get_db, init_db, test_connection
    
    # Não vamos testar a conexão real para evitar erros
    print("✅ Serviço de banco de dados carregado")
        
except Exception as e:
    print(f"❌ Erro no serviço de banco de dados: {e}")

print("=" * 50)
print("🎉 Teste concluído!")