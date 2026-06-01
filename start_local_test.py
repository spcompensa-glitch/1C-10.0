#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Iniciar Servidor de Teste Local
===============================

Script para iniciar o servidor de teste local e verificar o sistema de autenticação.
"""

import os
import sys
import time
import subprocess
import requests
import webbrowser
from pathlib import Path

def check_backend_services():
    """Verificar se os serviços do backend estão funcionando"""
    print("🔍 Verificando serviços do backend...")
    
    # Verificar se os diretórios existem
    backend_path = Path("backend")
    if not backend_path.exists():
        print("❌ Diretório backend não encontrado")
        return False
    
    # Verificar arquivos importantes
    important_files = [
        "backend/__init__.py",
        "backend/config.py",
        "backend/routes/auth.py",
        "backend/auth/middleware.py",
        "backend/auth/jwt_handler.py"
    ]
    
    for file_path in important_files:
        if Path(file_path).exists():
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path} - NÃO ENCONTRADO")
            return False
    
    return True

def check_frontend_files():
    """Verificar se os arquivos do frontend existem"""
    print("🔍 Verificando arquivos do frontend...")
    
    frontend_path = Path("frontend")
    if not frontend_path.exists():
        print("❌ Diretório frontend não encontrado")
        return False
    
    # Verificar arquivos importantes
    important_files = [
        "frontend/login.html",
        "frontend/auth.html", 
        "frontend/cockpit.html",
        "frontend/index.html"
    ]
    
    for file_path in important_files:
        if Path(file_path).exists():
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path} - NÃO ENCONTRADO")
            return False
    
    return True

def start_local_server():
    """Iniciar o servidor local"""
    print("🚀 Iniciando servidor de teste local...")
    
    # Criar processo do servidor
    process = subprocess.Popen([
        sys.executable, 
        "local_test_server.py"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    # Esperar o servidor iniciar
    time.sleep(3)
    
    return process

def test_server_endpoints():
    """Testar os endpoints do servidor"""
    print("🧪 Testando endpoints do servidor...")
    
    base_url = "http://127.0.0.1:8080"
    
    # Testar endpoint de saúde
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Endpoint /health OK")
        else:
            print(f"❌ Endpoint /health falhou: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Erro ao testar /health: {e}")
        return False
    
    # Testar endpoint de login
    try:
        response = requests.post(f"{base_url}/api/auth/login", 
                              json={"username": "admin", "password": "admin123"},
                              timeout=5)
        if response.status_code == 200:
            print("✅ Endpoint /api/auth/login OK")
            print(f"🎯 Token recebido: {response.json().get('access_token', 'N/A')}")
        else:
            print(f"❌ Endpoint /api/auth/login falhou: {response.status_code}")
            print(f"📝 Erro: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Erro ao testar /api/auth/login: {e}")
        return False
    
    return True

def open_browser():
    """Abrir navegador com as páginas de teste"""
    print("🌐 Abrindo navegador para teste...")
    
    base_url = "http://127.0.0.1:8080"
    
    # Abrir página de login
    try:
        webbrowser.open(f"{base_url}/login")
        print(f"🔐 Página de login: {base_url}/login")
    except:
        print(f"❌ Não foi possível abrir navegador. Acesse manualmente: {base_url}/login")
    
    # Abrir página de auth
    try:
        webbrowser.open(f"{base_url}/auth")
        print(f"🔐 Página de auth: {base_url}/auth")
    except:
        print(f"❌ Não foi possível abrir navegador. Acesse manualmente: {base_url}/auth")
    
    # Abrir cockpit
    try:
        webbrowser.open(f"{base_url}/cockpit")
        print(f"🚀 Página de cockpit: {base_url}/cockpit")
    except:
        print(f"❌ Não foi possível abrir navegador. Acesse manualmente: {base_url}/cockpit")

def main():
    """Função principal"""
    print("🎯 Servidor de Teste Local para Sistema de Autenticação")
    print("=" * 60)
    
    # Verificar backend
    if not check_backend_services():
        print("❌ Backend não está pronto para teste")
        return False
    
    # Verificar frontend
    if not check_frontend_files():
        print("❌ Frontend não está pronto para teste")
        return False
    
    print("\n✅ Sistema pronto para teste!")
    
    # Iniciar servidor
    server_process = start_local_server()
    
    # Esperar um pouco para o servidor iniciar
    time.sleep(2)
    
    # Testar endpoints
    if test_server_endpoints():
        print("\n🎉 Servidor de teste está funcionando!")
        print("\n📋 URLs para teste:")
        print("  🔐 Login: http://127.0.0.1:8080/login")
        print("  🔐 Auth: http://127.0.0.1:8080/auth")
        print("  🚀 Cockpit: http://127.0.0.1:8080/cockpit")
        print("  📊 Health: http://127.0.0.1:8080/health")
        
        # Abrir navegador
        open_browser()
        
        print("\n💡 Use as credenciais de teste:")
        print("  📝 Usuário: admin")
        print("  🔑 Senha: admin123")
        
        print("\n⏹️  Pressione Ctrl+C para parar o servidor")
        
        # Manter servidor rodando
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Parando servidor...")
            server_process.terminate()
            server_process.wait()
            print("✅ Servidor parado")
        
        return True
    else:
        print("\n❌ Servidor não passou nos testes")
        server_process.terminate()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)