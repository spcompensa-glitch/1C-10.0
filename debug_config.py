#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Debug de Configurações
======================

Script para debugar as configurações do sistema.
"""

import os
from pathlib import Path

# Carregar variáveis de ambiente
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    print(f"📁 Arquivo .env encontrado: {env_path}")
    with open(env_path, 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                print(f"   {line.strip()}")
else:
    print("❌ Arquivo .env não encontrado")

print("\n🔍 Variáveis de ambiente atuais:")
for key, value in os.environ.items():
    if 'ENCRYPTION' in key or 'JWT' in key or 'DATABASE' in key or 'APP' in key:
        print(f"   {key}: {value}")

# Testar import do config
try:
    import sys
    sys.path.append('backend')
    from config import settings
    
    print(f"\n✅ Configurações carregadas:")
    print(f"   APP_NAME: {getattr(settings, 'app_name', 'N/A')}")
    print(f"   DEBUG: {getattr(settings, 'debug', 'N/A')}")
    print(f"   DATABASE_URL: {getattr(settings, 'database_url', 'N/A')}")
    print(f"   ENCRYPTION_PASSWORD: {'*' * 10 if getattr(settings, 'encryption_password', '') else 'N/A'}")
    print(f"   JWT_SECRET_KEY: {'*' * 10 if getattr(settings, 'jwt_secret_key', '') else 'N/A'}")
    
except Exception as e:
    print(f"\n❌ Erro ao importar configurações: {e}")