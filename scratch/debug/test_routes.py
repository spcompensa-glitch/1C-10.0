#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testar Rotas do Servidor Frontend
=================================

Script para testar todas as rotas do servidor frontend local.
"""

import requests
import time
import json

def test_route(url, description):
    """Testar uma rota específica"""
    try:
        response = requests.get(url, timeout=5)
        print(f"✅ {description}: {url} - Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   📝 Tamanho: {len(response.content)} bytes")
            return True
        else:
            print(f"   ❌ Erro: {response.text}")
            return False
    except Exception as e:
        print(f"❌ {description}: {url} - Erro: {e}")
        return False

def test_api_route(url, data, description):
    """Testar uma rota de API"""
    try:
        response = requests.post(url, json=data, timeout=5)
        print(f"✅ {description}: {url} - Status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"   📝 Resposta: {json.dumps(result, indent=2)}")
            return True
        else:
            print(f"   ❌ Erro: {response.text}")
            return False
    except Exception as e:
        print(f"❌ {description}: {url} - Erro: {e}")
        return False

def main():
    """Função principal"""
    print("🧪 Testando Rotas do Servidor Frontend")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    
    # Testar rotas principais
    routes = [
        (f"{base_url}/", "Página principal (redireciona)"),
        (f"{base_url}/login", "Página de login"),
        (f"{base_url}/auth", "Página de autenticação"),
        (f"{base_url}/cockpit", "Página do cockpit"),
        (f"{base_url}/index.html", "Página index"),
        (f"{base_url}/kanban-hermes-enhanced.html", "Página kanban enhanced"),
        (f"{base_url}/neural-chat.html", "Página neural chat"),
        (f"{base_url}/observatory.html", "Página observatory"),
    ]
    
    print("\n📋 Testando rotas de páginas...")
    success_count = 0
    for url, desc in routes:
        if test_route(url, desc):
            success_count += 1
    
    # Testar rotas de API
    print("\n📋 Testando rotas de API...")
    api_routes = [
        (f"{base_url}/api/auth/login", {"username": "admin", "password": "admin123"}, "Login admin"),
        (f"{base_url}/api/auth/register", {"username": "testuser", "password": "test123", "confirm_password": "test123"}, "Registro usuário"),
        (f"{base_url}/api/auth/me", None, "Obter perfil"),
    ]
    
    for url, data, desc in api_routes:
        if data:
            if test_api_route(url, data, desc):
                success_count += 1
        else:
            if test_route(url, desc):
                success_count += 1
    
    # Resultado final
    total_routes = len(routes) + len(api_routes)
    print(f"\n📊 Resultado: {success_count}/{total_routes} rotas funcionando")
    
    if success_count == total_routes:
        print("🎉 Todas as rotas estão funcionando!")
        print("\n🔗 URLs para acessar:")
        print("   🔐 Login: http://localhost:8000/login")
        print("   🔐 Auth: http://localhost:8000/auth")
        print("   🚀 Cockpit: http://localhost:8000/cockpit")
        return True
    else:
        print("❌ Algumas rotas não estão funcionando")
        return False

if __name__ == "__main__":
    # Aguardar um pouco para o servidor iniciar
    time.sleep(2)
    
    success = main()
    exit(0 if success else 1)