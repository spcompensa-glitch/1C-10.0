#!/usr/bin/env python3
"""
Script para testar o frontend no navegador
"""
import webbrowser
import time
import os

def test_frontend():
    """Testa o frontend no navegador"""
    try:
        # Verificar se os arquivos existem
        if not os.path.exists('frontend/cockpit.html'):
            print("❌ Arquivo frontend/cockpit.html não encontrado")
            return
        
        if not os.path.exists('frontend/app.js'):
            print("❌ Arquivo frontend/app.js não encontrado")
            return
        
        print("🔍 Testando frontend...")
        
        # Verificar se o servidor está rodando
        try:
            import http.server
            import socketserver
            import threading
            
            class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, directory="frontend", **kwargs)
            
            with socketserver.TCPServer(("", 8080), MyHTTPRequestHandler) as httpd:
                print("🚀 Servidor HTTP iniciado na porta 8080")
                print("📱 Abindo navegador...")
                
                # Iniciar servidor em background
                server_thread = threading.Thread(target=httpd.serve_forever)
                server_thread.daemon = True
                server_thread.start()
                
                # Abrir navegador
                time.sleep(1)  # Dar tempo para o servidor iniciar
                webbrowser.open("http://localhost:8080/cockpit.html")
                
                print("✅ Frontend aberto no navegador")
                print("📋 Verifique se os erros desapareceram")
                
                # Manter servidor rodando por 30 segundos
                time.sleep(30)
                
        except Exception as e:
            print(f"❌ Erro ao iniciar servidor: {e}")
            
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    test_frontend()