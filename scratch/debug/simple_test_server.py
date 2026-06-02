#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor Simples de Teste para Frontend
======================================

Servidor local mínimo para testar apenas o frontend e autenticação.
Sem dependências complexas.

Author: DevOps Team
Version: 1.0
"""

import os
import sys
import logging
import time
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SimpleTestServer")

# Criar app FastAPI
app = FastAPI(
    title="1Crypten Simple Test Server",
    description="Servidor simples para testar frontend",
    version="1.0.0"
)

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
if os.path.exists(frontend_path):
    logger.info(f"📁 Frontend encontrado em: {frontend_path}")
else:
    logger.warning("⚠️ Diretório frontend não encontrado")

# Variáveis de ambiente
LOCAL_PORT = int(os.getenv("LOCAL_PORT", 8080))
LOCAL_HOST = os.getenv("LOCAL_HOST", "127.0.0.1")

# ===== ROTAS DE LOGIN E AUTENTICAÇÃO =====

@app.get("/", response_class=RedirectResponse)
async def redirect_root():
    """Redirecionar root para a página de login"""
    return "/login"

@app.get("/login", response_class=FileResponse)
async def serve_login():
    """Servir página de Login"""
    login_path = os.path.join(frontend_path, "login.html")
    if os.path.exists(login_path):
        logger.info(f"✅ Servindo login.html de: {login_path}")
        return login_path
    else:
        logger.error(f"❌ Arquivo não encontrado: {login_path}")
        raise HTTPException(status_code=404, detail="Login page not found")

@app.get("/auth", response_class=FileResponse)
async def serve_auth():
    """Servir página de Autenticação"""
    auth_path = os.path.join(frontend_path, "auth.html")
    if os.path.exists(auth_path):
        logger.info(f"✅ Servindo auth.html de: {auth_path}")
        return auth_path
    else:
        logger.error(f"❌ Arquivo não encontrado: {auth_path}")
        raise HTTPException(status_code=404, detail="Authentication page not found")

@app.get("/cockpit", response_class=FileResponse)
async def serve_cockpit():
    """Servir página Cockpit"""
    cockpit_path = os.path.join(frontend_path, "cockpit.html")
    if os.path.exists(cockpit_path):
        logger.info(f"✅ Servindo cockpit.html de: {cockpit_path}")
        return cockpit_path
    else:
        logger.error(f"❌ Arquivo não encontrado: {cockpit_path}")
        raise HTTPException(status_code=404, detail="Cockpit page not found")

@app.get("/index.html", response_class=FileResponse)
async def serve_index():
    """Servir página principal"""
    index_path = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_path):
        return index_path
    else:
        raise HTTPException(status_code=404, detail="Index page not found")

# ===== ROTAS DE API DE AUTENTICAÇÃO =====

@app.post("/api/auth/login")
async def login_user(credentials: dict):
    """Endpoint de login para teste local"""
    logger.info(f"🔐 Tentativa de login: {credentials}")
    
    # Credenciais de teste
    if credentials.get("username") == "admin" and credentials.get("password") == "admin123":
        logger.info("✅ Login bem-sucedido")
        return {
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
    else:
        logger.warning(f"❌ Login falhou: credenciais inválidas")
        raise HTTPException(
            status_code=401, 
            detail="Credenciais inválidas"
        )

@app.post("/api/auth/register")
async def register_user(userData: dict):
    """Endpoint de registro para teste local"""
    logger.info(f"📝 Tentativa de registro: {userData}")
    
    username = userData.get("username", "")
    password = userData.get("password", "")
    
    # Validação simples
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Usuário deve ter pelo menos 3 caracteres")
    
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Senha deve ter pelo menos 8 caracteres")
    
    if password != userData.get("confirm_password", ""):
        raise HTTPException(status_code=400, detail="As senhas não coincidem")
    
    logger.info("✅ Registro bem-sucedido")
    return {
        "message": "Usuário criado com sucesso",
        "user": {
            "username": username,
            "email": userData.get("email", ""),
            "created_at": "2026-06-01T00:00:00Z"
        }
    }

@app.get("/api/auth/me")
async def get_current_user(token: str = None):
    """Endpoint para obter usuário atual"""
    if token and token == "test_token_123":
        return {
            "username": "admin",
            "email": "admin@1crypten.space", 
            "permissions": ["admin"],
            "created_at": "2026-06-01T00:00:00Z"
        }
    else:
        raise HTTPException(status_code=401, detail="Token inválido")

# ===== ROTAS DE STATUS =====

@app.get("/health")
async def health_check():
    """Endpoint de saúde do sistema"""
    return {
        "timestamp": time.time(),
        "status": "healthy",
        "message": "Servidor de teste local está operacional",
        "frontend_path": frontend_path,
        "frontend_exists": os.path.exists(frontend_path),
        "local_mode": True
    }

@app.get("/")
async def root():
    """Endpoint raiz"""
    return {
        "message": "1Crypten Simple Test Server",
        "version": "1.0.0",
        "mode": "simple_test",
        "login_url": f"http://{LOCAL_HOST}:{LOCAL_PORT}/login",
        "auth_url": f"http://{LOCAL_HOST}:{LOCAL_PORT}/auth",
        "cockpit_url": f"http://{LOCAL_HOST}:{LOCAL_PORT}/cockpit",
        "status": "running"
    }

if __name__ == "__main__":
    # Configurar servidor local
    logger.info(f"🚀 Iniciando servidor de teste local na porta {LOCAL_PORT}")
    logger.info(f"🌍 Host: {LOCAL_HOST}")
    logger.info(f"📁 Frontend: {frontend_path}")
    logger.info(f"🔐 URL de login: http://{LOCAL_HOST}:{LOCAL_PORT}/login")
    logger.info(f"🔐 URL de auth: http://{LOCAL_HOST}:{LOCAL_PORT}/auth")
    logger.info(f"🚀 URL de cockpit: http://{LOCAL_HOST}:{LOCAL_PORT}/cockpit")
    
    uvicorn.run(
        "simple_test_server:app",
        host=LOCAL_HOST,
        port=LOCAL_PORT,
        reload=True,
        log_level="info"
    )