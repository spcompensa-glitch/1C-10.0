#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor Web Mínimo para Teste
==============================

Servidor web extremamente simples para testar as páginas de login.
"""

import http.server
import socketserver
import webbrowser
import os
from pathlib import Path

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    
    def do_GET(self):
        # Mapear rotas específicas
        if self.path == '/' or self.path == '/login':
            self.path = '/login.html'
        elif self.path == '/auth':
            self.path = '/auth.html'
        elif self.path == '/cockpit':
            self.path = '/cockpit.html'
        elif self.path == '/index':
            self.path = '/index.html'
        elif self.path.startswith('/api/'):
            self.send_api_response()
            return
        
        # Servir o arquivo
        super().do_GET()
    
    def do_POST(self):
        if self.path.startswith('/api/'):
            self.send_api_response()
            return
        
        self.send_response(405)
        self.end_headers()
    
    def send_api_response(self):
        """Enviar resposta de API simulada"""
        import json
        import time
        
        if self.path == '/api/auth/login':
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
        elif self.path == '/api/auth/register':
            response_data = {
                "message": "Usuário criado com sucesso",
                "user": {
                    "username": "newuser",
                    "email": "newuser@1crypten.space",
                    "created_at": "2026-06-01T00:00:00Z"
                }
            }
        elif self.path == '/api/auth/me':
            response_data = {
                "username": "admin",
                "email": "admin@1crypten.space", 
                "permissions": ["admin"],
                "created_at": "2026-06-01T00:00:00Z"
            }
        else:
            response_data = {"error": "API não encontrada"}
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
        self.wfile.write(json.dumps(response_data).encode())
    
    def log_message(self, format, *args):
        print(f"[{self.address_string()}] {format % args}")

def main():
    PORT = 9000
    
    # Mudar para o diretório frontend
    frontend_dir = os.path.dirname(__file__) + '/frontend'
    os.chdir(frontend_dir)
    
    print(f"🚀 Servidor web mínimo iniciado na porta {PORT}")
    print(f"📁 Diretório: {os.getcwd()}")
    print(f"🌐 URL: http://localhost:{PORT}")
    print(f"🔐 Login: http://localhost:{PORT}/login")
    print(f"🔐 Auth: http://localhost:{PORT}/auth")
    print(f"🚀 Cockpit: http://localhost:{PORT}/cockpit")
    
    # Abrir navegador
    try:
        webbrowser.open(f"http://localhost:{PORT}/login")
        print("✅ Navegador aberto com a página de login")
    except:
        print("❌ Não foi possível abrir navegador")
    
    with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
        print("\n⏹️  Pressione Ctrl+C para parar o servidor")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Servidor parado")

if __name__ == "__main__":
    main()