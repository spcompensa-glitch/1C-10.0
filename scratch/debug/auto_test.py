#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste Automático do Servidor Frontend
======================================

Inicia o servidor e testa todas as rotas automaticamente.
"""

import os
import sys
import subprocess
import time
import requests
import json
import signal
import atexit
from pathlib import Path

# Variáveis globais
server_process = None
SERVER_PORT = 8000

def cleanup():
    """Limpeza quando o script terminar"""
    global server_process
    if server_process:
        print("\n🛑 Parando servidor...")
        server_process.terminate()
        server_process.wait()

def start_server():
    """Iniciar o servidor frontend"""
    global server_process
    
    print("🚀 Iniciando servidor frontend...")
    
    # Mudar para o diretório frontend
    os.chdir(os.path.dirname(__file__) + '/frontend')
    
    # Iniciar servidor
    server_process = subprocess.Popen(
        [sys.executable, '../frontend_test_server.py'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Aguardar o servidor iniciar
    time.sleep(3)
    
    print("✅ Servidor iniciado")

def test_routes():
    """Testar todas as rotas"""
    base_url = f"http://localhost:{SERVER_PORT}"
    
    print(f"\n🧪 Testando rotas em {base_url}")
    
    # Testar rotas principais
    test_cases = [
        (f"{base_url}/", "Página principal", "GET"),
        (f"{base_url}/login", "Página de login", "GET"),
        (f"{base_url}/auth", "Página de autenticação", "GET"),
        (f"{base_url}/cockpit", "Página do cockpit", "GET"),
        (f"{base_url}/index.html", "Página index", "GET"),
        (f"{base_url}/kanban-hermes-enhanced.html", "Página kanban enhanced", "GET"),
        (f"{base_url}/neural-chat.html", "Página neural chat", "GET"),
        (f"{base_url}/observatory.html", "Página observatory", "GET"),
        (f"{base_url}/api/auth/login", "API Login", "POST", {"username": "admin", "password": "admin123"}),
        (f"{base_url}/api/auth/register", "API Register", "POST", {"username": "testuser", "password": "test123", "confirm_password": "test123"}),
        (f"{base_url}/api/auth/me", "API Get Profile", "GET"),
    ]
    
    success_count = 0
    total_count = len(test_cases)
    
    for i, test_case in enumerate(test_cases):
        url = test_case[0]
        description = test_case[1]
        method = test_case[2]
        data = test_case[3] if len(test_case) > 3 else None
        
        try:
            print(f"\n[{i+1}/{total_count}] 📍 {description}: {url}")
            
            if method == "GET":
                response = requests.get(url, timeout=5)
            elif method == "POST":
                response = requests.post(url, json=data, timeout=5)
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                print(f"   ✅ SUCESSO")
                success_count += 1
            else:
                print(f"   ❌ FALHOU")
                if response.text:
                    print(f"   Erro: {response.text[:200]}...")
                
        except Exception as e:
            print(f"   ❌ ERRO: {e}")
    
    return success_count, total_count

def main():
    """Função principal"""
    print("🎯 Teste Automático do Servidor Frontend")
    print("=" * 50)
    
    # Registrar função de limpeza
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, lambda s, f: (cleanup(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda s, f: (cleanup(), sys.exit(0)))
    
    # Verificar arquivos
    required_files = ["login.html", "auth.html", "cockpit.html", "index.html"]
    frontend_dir = os.path.dirname(__file__) + '/frontend'
    
    print("🔍 Verificando arquivos do frontend...")
    for file in required_files:
        if Path(f"{frontend_dir}/{file}").exists():
            print(f"   ✅ {file}")
        else:
            print(f"   ❌ {file} - NÃO ENCONTRADO")
            return False
    
    # Iniciar servidor
    start_server()
    
    # Testar rotas
    success_count, total_count = test_routes()
    
    # Resultado
    print(f"\n📊 Resultado Final:")
    print(f"   ✅ {success_count}/{total_count} rotas funcionando")
    print(f"   📈 Sucesso: {(success_count/total_count)*100:.1f}%")
    
    if success_count == total_count:
        print("🎉 TODAS AS ROTAS ESTÃO FUNCIONANDO!")
        print(f"\n🔗 URLs para acessar:")
        print(f"   🔐 Login: http://localhost:{SERVER_PORT}/login")
        print(f"   🔐 Auth: http://localhost:{SERVER_PORT}/auth")
        print(f"   🚀 Cockpit: http://localhost:{SERVER_PORT}/cockpit")
        print(f"   📊 Health: http://localhost:{SERVER_PORT}/api/health")
        
        print(f"\n💡 Credenciais de teste:")
        print(f"   📝 Usuário: admin")
        print(f"   🔑 Senha: admin123")
        
        return True
    else:
        print("❌ Algumas rotas não estão funcionando")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)