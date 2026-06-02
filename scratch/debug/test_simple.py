#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path

# Adicionar backend ao path
sys.path.append(str(Path(__file__).parent / "backend"))

print("🔍 Testando módulos básicos...")

try:
    # Testar config
    from auth_config import auth_settings as settings
    print(f"✅ Config: {settings.app_name}")
    
    # Testar criptografia
    from auth.security.encryption import TokenEncryption
    encryption = TokenEncryption()
    
    # Testar criptografia/descriptografia
    test_data = "test_data_123"
    encrypted = encryption.encrypt_token(test_data)
    decrypted = encryption.decrypt_token(encrypted)
    
    if decrypted == test_data:
        print("✅ Criptografia: OK")
    else:
        print("❌ Criptografia: FALHA")
    
    # Testar mascaramento
    from auth.security.encryption import get_data_masker
    masker = get_data_masker()
    masked_api = masker.mask_api_key("test_api_key_1234567890123456")
    print(f"✅ Mascaramento API: {masked_api}")
    
    # Testar senhas
    from auth.security.password_handler import PasswordHandler
    password_handler = PasswordHandler()
    
    # Testar hash de senha
    password = "test_password_123"
    hashed = password_handler.hash_password(password)
    verified = password_handler.verify_password(password, hashed)
    
    if verified:
        print("✅ Senhas: OK")
    else:
        print("❌ Senhas: FALHA")
    
    # Testar validação de força
    strength = password_handler.validate_password_strength("StrongPass123!")
    print(f"✅ Validação força: {strength['strength']} ({strength['score']}/{strength['max_score']})")
    
    print("🎉 Todos os testes básicos passaram!")
    
except Exception as e:
    print(f"❌ Erro: {e}")
    import traceback
    traceback.print_exc()