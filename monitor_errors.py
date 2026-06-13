#!/usr/bin/env python3
"""
Script para monitorar erros no frontend
"""
import time
import webbrowser
import requests

def check_frontend_errors():
    """Verifica se o frontend está sem erros"""
    try:
        print("🔍 Verificando frontend...")
        
        # Acessar a página principal
        try:
            response = requests.get("http://localhost:8080/cockpit.html", timeout=5)
            if response.status_code == 200:
                print("✅ Frontend acessível")
            else:
                print(f"❌ Erro HTTP: {response.status_code}")
                return
        except requests.exceptions.RequestException as e:
            print(f"❌ Não foi possível acessar o frontend: {e}")
            return
        
        # Verificar scripts principais
        scripts_to_check = [
            "app.js",
            "components/TriumphModal.js",
            "components/SettingsPage.js",
            "components/AdminUsersPage.js",
            "components/TakeoffModal.js",
            "components/DeepAnalysisModal.js"
        ]
        
        print("📋 Verificando scripts...")
        for script in scripts_to_check:
            try:
                response = requests.get(f"http://localhost:8080/{script}", timeout=5)
                if response.status_code == 200:
                    print(f"✅ {script} - OK")
                else:
                    print(f"❌ {script} - Erro: {response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"❌ {script} - Não acessível: {e}")
        
        print("🎉 Verificação concluída!")
        print("📱 Por favor, verifique o console do navegador manualmente para erros.")
        
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    check_frontend_errors()