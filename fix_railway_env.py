#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix Railway Environment Variables
=================================

Script para garantir que as variáveis de ambiente estejam corretamente
configuradas para o Railway deployment.

Author: DevOps Team
Version: 1.0
"""

import os
import subprocess
import sys

def fix_railway_environment():
    """Fixar variáveis de ambiente no Railway"""
    print("🔧 Fixando variáveis de ambiente para Railway...")
    
    # Variáveis obrigatórias
    required_vars = {
        "RAILWAY_TOKEN": "baab061ec-2bcf-436b-bbb2-1c6b8616046b",
        "ADMIN_API_KEY": "1crypten-admin-key-2026-production",
        "TELEGRAM_BOT_TOKEN": "8656832302:AAHARDZZe-bltJte6QR-e-KcBiNkNDrvx7I",
        "TELEGRAM_CHAT_ID": "1249100206",
        "JWT_SECRET_KEY": "1crypten-jwt-secret-2026-production",
        "ENVIRONMENT": "production",
        "PORT": "8080"
    }
    
    # Verificar Railway CLI
    try:
        result = subprocess.run(["railway", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Railway CLI disponível")
            
            # Configurar variáveis
            for var_name, var_value in required_vars.items():
                print(f"🔧 Configurando {var_name}...")
                subprocess.run([
                    "railway", "variables", "set", f"{var_name}={var_value}"
                ], check=True)
                print(f"   ✅ {var_name} = {var_value}")
            
            print("✅ Variáveis de ambiente configuradas com sucesso!")
            
        else:
            print("❌ Railway CLI não encontrado")
            print("   Instale com: npm install -g @railway/cli")
            
    except FileNotFoundError:
        print("❌ Railway CLI não encontrado")
        print("   Instale com: npm install -g @railway/cli")
    except subprocess.CalledProcessError as e:
        print(f"❌ Erro ao configurar variáveis: {e}")

if __name__ == "__main__":
    fix_railway_environment()