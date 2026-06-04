#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para testar o Railway
"""

import requests
import time

def test_railway():
    """Testar endpoints do Railway"""
    base_url = "https://1crypten-hermes-agent-production.up.railway.app"
    
    print(f"🔍 Testando Railway: {base_url}")
    
    # Testar endpoint /health
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        print(f"📊 /health: {response.status_code}")
        if response.status_code == 200:
            print(f"✅ Health check: {response.json()}")
        else:
            print(f"❌ Health error: {response.text}")
    except Exception as e:
        print(f"❌ Health failed: {e}")
    
    # Testar endpoint /auth.html
    try:
        response = requests.get(f"{base_url}/auth.html", timeout=10)
        print(f"📋 /auth.html: {response.status_code}")
        if response.status_code == 200:
            print("✅ Auth page OK")
        else:
            print(f"❌ Auth error: {response.text}")
    except Exception as e:
        print(f"❌ Auth failed: {e}")
    
    # Testar endpoint /api/auth/me
    try:
        response = requests.get(f"{base_url}/api/auth/me", timeout=10)
        print(f"👤 /api/auth/me: {response.status_code}")
        if response.status_code == 401:  # Não autenticado é esperado
            print("✅ API auth endpoint OK (não autenticado)")
        else:
            print(f"❌ API auth error: {response.text}")
    except Exception as e:
        print(f"❌ API auth failed: {e}")

if __name__ == "__main__":
    time.sleep(2)  # Dar tempo para o Railway atualizar
    test_railway()