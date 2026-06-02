#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path
import requests
import time

# Adicionar backend ao path
sys.path.append(str(Path(__file__).parent / "backend"))

print("🔍 Testando API de Autenticação...")

# URL da API
BASE_URL = "http://localhost:8085"

def test_health_check():
    """Testar endpoint de saúde"""
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print("✅ Health Check: OK")
            return True
        else:
            print(f"❌ Health Check: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health Check Error: {e}")
        return False

def test_login():
    """Testar endpoint de login"""
    try:
        login_data = {
            "username": "admin",
            "password": "admin123"
        }
        
        response = requests.post(f"{BASE_URL}/api/auth/login", json=login_data)
        
        if response.status_code == 200:
            print("✅ Login: OK")
            return response.json()
        else:
            print(f"❌ Login: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ Login Error: {e}")
        return None

def test_protected_endpoint():
    """Testar endpoint protegido"""
    try:
        # Primeiro fazer login
        login_response = test_login()
        if not login_response:
            return False
        
        # Usar token para acessar endpoint protegido
        headers = {
            "Authorization": f"Bearer {login_response['access_token']}"
        }
        
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
        
        if response.status_code == 200:
            print("✅ Protected Endpoint: OK")
            return True
        else:
            print(f"❌ Protected Endpoint: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Protected Endpoint Error: {e}")
        return False

def main():
    """Função principal"""
    print("Iniciando testes da API...")
    
    # Aguardar o servidor iniciar
    print("Aguardando servidor iniciar...")
    time.sleep(2)
    
    # Executar testes
    health_ok = test_health_check()
    login_ok = test_login() is not None
    protected_ok = test_protected_endpoint()
    
    # Resultados
    print("\n📊 Resultados dos Testes:")
    print(f"Health Check: {'✅' if health_ok else '❌'}")
    print(f"Login: {'✅' if login_ok else '❌'}")
    print(f"Protected Endpoint: {'✅' if protected_ok else '❌'}")
    
    if health_ok and login_ok and protected_ok:
        print("\n🎉 Todos os testes passaram!")
        return True
    else:
        print("\n❌ Alguns testes falharam.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)