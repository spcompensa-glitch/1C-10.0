#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Debug de ambiente
"""

import os
from dotenv import load_dotenv

# Carregar .env
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
print(f"Carregando .env de: {env_path}")
print(f"Arquivo .env existe: {os.path.exists(env_path)}")

if os.path.exists(env_path):
    load_dotenv(env_path, override=True)
    print("✅ .env carregado com sucesso")
else:
    print("❌ .env não encontrado")

print("\nVariáveis de ambiente:")
print(f"DATABASE_URL: {os.getenv('DATABASE_URL')}")
print(f"JWT_SECRET_KEY: {os.getenv('JWT_SECRET_KEY')}")
print(f"ENCRYPTION_PASSWORD: {os.getenv('ENCRYPTION_PASSWORD')}")

# Testar leitura direta do arquivo
print("\nConteúdo do arquivo .env:")
try:
    with open(env_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if 'DATABASE_URL' in line:
                print(f"Linha {i+1}: {line.strip()}")
except Exception as e:
    print(f"Erro ao ler arquivo: {e}")