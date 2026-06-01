#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor HTTP Simples para Testar Frontend
==========================================

Servidor HTTP mínimo para testar as páginas de login e autenticação.
Usa apenas o servidor embutido do Python.

Author: DevOps Team
Version: 1.0
"""

import os
import sys
import http.server
import socketserver
import webbrowser
from pathlib import Path

class FrontendHandler(http.server.SimpleHTTPRequestHandler):
    """Handler personalizado para servir o frontend"""
    
    def __init__(self, *args, **kwargs):
        # Define o diretório como o frontend
        os.chdir(os.path.dirname(__file__) + '/frontend')
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET requests"""
        print(f"📡 GET request: {self.path}")
        
        # Mapear rotas específicas
        if self.path == '/' or self.path == '/index.html':
            self.path = '/index.html'
        elif self.path == '/login':
            self.path = '/login.html'
        elif self.path == '/auth':
            self.path = '/auth.html'
        elif self.path == '/cockpit':
            self.path = '/cockpit.html'
        elif self.path.startswith('/api/'):
            # API endpoints - retornar respostas simuladas
            self.handle_api_request()
            return
        
        # Chamar o método da classe pai para servir arquivos
        super().do_GET()
    
    def handle_api_request(self):
        """Handle API requests"""
        import json
        import time
        
        if self.path == '/api/auth/login':
            # Simular resposta de login
            response_data = {
                "access_token": "test_token_123",
                "refresh_token": "test_refresh_token_456",
                "token_type": "bearer",
                "user": {
                    "username": "admin",
                    "email": "admin@1crypten.space",
                    "permissions": ["admin"],
                    "created_at": "2026-06-01T00:00:00Z"
                }
            }
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode())
        
        elif self.path == '/api/auth/register':
            # Simular resposta de registro
            response_data = {
                "message": "Usuário criado com sucesso",
                "user": {
                    "username": "newuser",
                    "email": "newuser@1crypten.space",
                    "created_at": "2026-06-01T00:00:00Z"
                }
            }
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode())
        
        elif self.path == '/api/auth/me':
            # Simular resposta de perfil
            response_data = {
                "username": "admin",
                "email": "admin@1crypten.space", 
                "permissions": ["admin"],
                "created_at": "2026-06-01T00:00:00Z"
            }
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode())
        
        else:
            # API não encontrada
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        """Handle POST requests"""
        print(f"📡 POST request: {self.path}")
        
        if self.path.startswith('/api/'):
            # API endpoints - retornar respostas simuladas
            self.handle_api_request()
            return
        
        # Chamar o método da classe pai para servir arquivos
        self.send_response(405)
        self.end_headers()
    
    def log_message(self, format, *args):
        """Custom log message"""
        print(f"📡 {format % args}")

def test_frontend_files():
    """Testar se os arquivos do frontend existem"""
    print("🔍 Verificando arquivos do frontend...")
    
    required_files = [
        "login.html",
        "auth.html", 
        "cockpit.html",
        "index.html"
    ]
    
    missing_files = []
    for file in required_files:
        if Path(file).exists():
            print(f"✅ {file}")
        else:
            print(f"❌ {file} - NÃO ENCONTRADO")
            missing_files.append(file)
    
    if missing_files:
        print(f"\n❌ Arquivos faltando: {missing_files}")
        return False
    
    return True

def start_server():
    """Iniciar o servidor"""
    PORT = 8000
    
    print(f"🚀 Iniciando servidor frontend na porta {PORT}")
    print(f"📁 Diretório: {os.getcwd()}")
    
    # Criar o servidor
    with socketserver.TCPServer(("", PORT), FrontendHandler) as httpd:
        print(f"\n✅ Servidor iniciado com sucesso!")
        print(f"🌐 URL: http://localhost:{PORT}")
        print(f"🔐 Login: http://localhost:{PORT}/login")
        print(f"🔐 Auth: http://localhost:{PORT}/auth")
        print(f"🚀 Cockpit: http://localhost:{PORT}/cockpit")
        print("\n💡 Credenciais de teste:")
        print("   📝 Usuário: admin")
        print("   🔑 Senha: admin123")
        print("\n⏹️  Pressione Ctrl+C para parar o servidor")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Servidor parado pelo usuário")

def main():
    """Função principal"""
    print("🎯 Servidor Frontend de Teste")
    print("=" * 40)
    
    # Verificar arquivos
    if not test_frontend_files():
        print("\n❌ Arquivos do frontend não encontrados")
        return False
    
    print("\n✅ Arquivos do frontend prontos!")
    
    # Abrir navegador
    print("\n�abrindo navegador...")
    try:
        webbrowser.open("http://localhost:8000/login")
        print("✅ Navegador aberto com a página de login")
    except:
        print("❌ Não foi possível abrir navegador")
        print("   Acesse manualmente: http://localhost:8000/login")
    
    # Iniciar servidor
    start_server()

if __name__ == "__main__":
    main()