#!/usr/bin/env python3
"""
Script final para testar o frontend
"""
import webbrowser
import time
import os
import threading
import http.server
import socketserver

def test_frontend():
    """Testar o frontend final"""
    try:
        print("🔧 TESTE FINAL DO FRONTEND")
        print("=" * 50)
        
        # Verificar se os arquivos existem
        if not os.path.exists('frontend/cockpit.html'):
            print("❌ Arquivo frontend/cockpit.html não encontrado")
            return
        
        print("✅ Arquivos frontend encontrados")
        
        # Iniciar servidor HTTP
        class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory="frontend", **kwargs)
        
        with socketserver.TCPServer(("", 8080), MyHTTPRequestHandler) as httpd:
            print("🚀 Servidor HTTP iniciado na porta 8080")
            
            # Iniciar servidor em background
            server_thread = threading.Thread(target=httpd.serve_forever)
            server_thread.daemon = True
            server_thread.start()
            
            # Dar tempo para o servidor iniciar
            time.sleep(2)
            
            # Abrir navegador
            print("📱 Abrindo navegador...")
            webbrowser.open("http://localhost:8080/cockpit.html")
            
            print("\n📋 INSTRUÇÕES:")
            print("1. Verifique o console do navegador por erros")
            print("2. Os erros principais devem ter sido corrigidos:")
            print("   - ✅ useState is not a function")
            print("   - ✅ Erro de sintaxe no Babel (linha 4034)")
            print("   - ✅ HYPER (1200%) array structure")
            print("3. Se ainda houver erros, verifique o console")
            
            # Manter servidor rodando
            print("\n🎮 Servidor rodando. Pressione Ctrl+C para parar...")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n🛑 Servidor parado")
                
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    test_frontend()