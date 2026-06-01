#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste Rápido das Rotas
======================

Teste rápido das rotas do servidor frontend.
"""

import requests

def test_route(url, name):
    try:
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            print(f"✅ {name}: {url}")
            return True
        else:
            print(f"❌ {name}: {url} - {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ {name}: {url} - {e}")
        return False

def main():
    print("🧪 Teste Rápido das Rotas")
    print("=" * 30)
    
    base_url = "http://localhost:9000"
    
    routes = [
        (f"{base_url}/", "Página principal"),
        (f"{base_url}/login", "Página de login"),
        (f"{base_url}/auth", "Página de autenticação"),
        (f"{base_url}/cockpit", "Página do cockpit"),
        (f"{base_url}/index.html", "Página index"),
        (f"{base_url}/kanban-hermes-enhanced.html", "Kanban enhanced"),
        (f"{base_url}/neural-chat.html", "Neural chat"),
        (f"{base_url}/observatory.html", "Observatory"),
    ]
    
    success = 0
    total = len(routes)
    
    for url, name in routes:
        if test_route(url, name):
            success += 1
    
    print(f"\n📊 Resultado: {success}/{total} rotas funcionando")
    
    if success == total:
        print("🎉 Todas as rotas estão funcionando!")
        print(f"\n🔗 Acesse no navegador:")
        print(f"   http://localhost:9000/login")
        print(f"   http://localhost:9000/auth")
        print(f"   http://localhost:9000/cockpit")
    else:
        print("❌ Algumas rotas não estão funcionando")

if __name__ == "__main__":
    main()