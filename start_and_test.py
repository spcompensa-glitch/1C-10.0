#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para iniciar o servidor e testar endpoints
"""

import os
import sys
import subprocess
import time
import requests
import signal
import threading

# Configuração
SERVER_PORT = 8080
SERVER_URL = f"http://localhost:{SERVER_PORT}"

def start_server():
    """Iniciar o servidor"""
    print("🚀 Iniciando servidor Hermes Guardian...")
    
    # Mudar para o diretório correto
    os.chdir("c:\\Users\\spcom\\Desktop\\1C-7.0")
    
    # Iniciar servidor
    process = subprocess.Popen([
        sys.executable, "main.py"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    return process

def test_server():
    """Testar servidor"""
    print(f"🔍 Testando servidor em {SERVER_URL}")
    
    # Esperar servidor iniciar
    for i in range(30):  # 30 segundos de timeout
        try:
            response = requests.get(SERVER_URL, timeout=5)
            print(f"✅ Server status: {response.status_code}")
            return True
        except requests.exceptions.ConnectionError:
            print(f"⏳ Waiting for server... ({i+1}/30)")
            time.sleep(1)
    
    print("❌ Server failed to start")
    return False

def test_endpoints():
    """Testar endpoints específicos"""
    endpoints = [
        ("/", "Root"),
        ("/kanban", "Kanban"),
        ("/neural-chat", "Neural Chat"),
        ("/health", "Health"),
        ("/api/hermes/status", "API Status"),
    ]
    
    print("\n🧪 Testing endpoints:")
    
    for endpoint, name in endpoints:
        try:
            response = requests.get(f"{SERVER_URL}{endpoint}", timeout=10)
            print(f"✅ {name}: {response.status_code}")
            
            # Mostrar conteúdo para alguns endpoints
            if endpoint in ["/", "/kanban", "/neural-chat"]:
                content_len = len(response.content)
                print(f"   📄 Content length: {content_len} bytes")
                
        except Exception as e:
            print(f"❌ {name}: Error - {e}")

def test_api():
    """Testar API endpoints"""
    print("\n🔧 Testing API endpoints:")
    
    # Testar status
    try:
        response = requests.get(f"{SERVER_URL}/api/hermes/status", timeout=10)
        print(f"✅ API Status: {response.status_code}")
        if response.status_code == 200:
            print(f"   📊 Response: {response.text}")
    except Exception as e:
        print(f"❌ API Status: Error - {e}")
    
    # Testar chat
    try:
        response = requests.post(f"{SERVER_URL}/api/chat", 
                               json={"message": "Hello Hermes", "type": "chat"}, 
                               timeout=10)
        print(f"✅ API Chat: {response.status_code}")
        if response.status_code == 200:
            print(f"   💬 Response: {response.text}")
    except Exception as e:
        print(f"❌ API Chat: Error - {e}")

def main():
    """Função principal"""
    print("🚀 Hermes Guardian System - Local Test")
    print("=" * 50)
    
    # Iniciar servidor
    server_process = start_server()
    
    try:
        # Aguardar servidor iniciar
        time.sleep(5)
        
        # Testar servidor
        if test_server():
            # Testar endpoints
            test_endpoints()
            test_api()
            print("\n🎉 All tests completed!")
        else:
            print("\n❌ Server tests failed!")
            
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
        
    finally:
        # Parar servidor
        print("\n🛑 Stopping server...")
        server_process.terminate()
        server_process.wait()
        print("✅ Server stopped")

if __name__ == "__main__":
    main()