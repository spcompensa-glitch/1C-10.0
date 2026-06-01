#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path

# Adicionar backend ao path
sys.path.append(str(Path(__file__).parent / "backend"))

print("🔍 Testando backend...")

try:
    # Testar config
    from auth_config import auth_settings as settings
    print(f"✅ Config: {settings.app_name}")
    
    # Testar criptografia
    from auth.security.encryption import TokenEncryption
    encryption = TokenEncryption()
    print("✅ Criptografia: OK")
    
    # Testar senhas
    from auth.security.password_handler import PasswordHandler
    password_handler = PasswordHandler()
    print("✅ Senhas: OK")
    
    print("🎉 Todos os testes passaram!")
    
except Exception as e:
    print(f"❌ Erro: {e}")
    import traceback
    traceback.print_exc()