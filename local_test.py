#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste local do servidor principal
"""

import os
import sys
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

# Adicionar backend ao path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.append(backend_path)

# Criar app FastAPI
app = FastAPI(title="Local Test Server")

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurar caminho do frontend
frontend_path = os.path.join(os.path.dirname(__file__), 'frontend')
print(f"📁 Frontend path: {frontend_path}")

# Verificar arquivos
print("\n🔍 Verificando arquivos:")
for file in ['login.html', 'auth.html', 'cockpit.html', 'index.html']:
    file_path = os.path.join(frontend_path, file)
    exists = os.path.exists(file_path)
    size = os.path.getsize(file_path) if exists else 0
    print(f"   {file}: {'✅' if exists else '❌'} ({size} bytes)")

# Rotas principais
@app.get("/", response_class=RedirectResponse)
async def redirect_root():
    """Redirecionar root para a página de login"""
    print("🔄 Redirecionando / para /login")
    return "/login"

@app.get("/login", response_class=FileResponse)
async def serve_login():
    """Servir página de login"""
    login_path = os.path.join(frontend_path, "login.html")
    if os.path.exists(login_path):
        print(f"✅ Servindo login.html de: {login_path}")
        return login_path
    else:
        print(f"❌ Arquivo não encontrado: {login_path}")
        raise HTTPException(status_code=404, detail="Login page not found")

@app.get("/auth", response_class=FileResponse)
async def serve_auth():
    """Servir página de autenticação"""
    auth_path = os.path.join(frontend_path, "auth.html")
    if os.path.exists(auth_path):
        print(f"✅ Servindo auth.html de: {auth_path}")
        return auth_path
    else:
        print(f"❌ Arquivo não encontrado: {auth_path}")
        raise HTTPException(status_code=404, detail="Auth page not found")

@app.get("/cockpit", response_class=FileResponse)
async def serve_cockpit():
    """Servir cockpit"""
    cockpit_path = os.path.join(frontend_path, "cockpit.html")
    if os.path.exists(cockpit_path):
        print(f"✅ Servindo cockpit.html de: {cockpit_path}")
        return cockpit_path
    else:
        print(f"❌ Arquivo não encontrado: {cockpit_path}")
        raise HTTPException(status_code=404, detail="Cockpit page not found")

@app.get("/test-content")
async def test_content():
    """Teste de conteúdo"""
    try:
        login_path = os.path.join(frontend_path, "login.html")
        if os.path.exists(login_path):
            with open(login_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Verificar se é realmente o login.html
                if "login-container" in content:
                    return {"status": "ok", "file": "login.html", "size": len(content)}
                else:
                    return {"status": "error", "message": "login.html não tem o conteúdo esperado"}
        else:
            return {"status": "error", "message": "login.html não encontrado"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    print("🚀 Iniciando servidor de teste local...")
    print("🌐 URLs disponíveis:")
    print("   - / → redireciona para /login")
    print("   - /login → página de login")
    print("   - /auth → página auth")
    print("   - /cockpit → página cockpit")
    print("   - /test-content → teste de conteúdo")
    print("\n🔗 Acesse: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)