#!/usr/bin/env python3
import os
from dotenv import load_dotenv

# Carrega o .env
load_dotenv(".env", override=True)

# Testa as variáveis
print("ADMIN_API_KEY:", os.getenv("ADMIN_API_KEY"))
print("RAILWAY_TOKEN:", os.getenv("RAILWAY_TOKEN"))
print("RAILWAY_URL:", os.getenv("RAILWAY_URL"))

# Testa importação do config
try:
    from backend.config import settings
    print("Config.ADMIN_API_KEY:", settings.ADMIN_API_KEY)
except Exception as e:
    print("Erro ao importar config:", e)