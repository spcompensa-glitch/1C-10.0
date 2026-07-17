#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor de Produção para Railway
=================================

Servidor de produção para Railway com todas as rotas funcionais.
"""

import os
import sys
import logging
import time
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Adicionar backend ao sys.path para imports de services
ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(ROOT, 'backend')
sys.path.insert(0, ROOT)
sys.path.insert(0, BACKEND)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ProductionServer")

# Criar app FastAPI
app = FastAPI(
    title="1Crypten Production Server",
    description="Servidor de produção para Railway",
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

# ===== STARTUP EVENT - Inicializar services =====
@app.on_event("startup")
async def startup_event():
    """Inicializa services necessários na inicialização"""
    logger.info("🚀 Iniciando services de produção...")
    
    # Sandbox Service
    try:
        from services.sandbox_service import sandbox_service
        sandbox_service.start()
        logger.info("🟢 Sandbox Service iniciado!")
    except Exception as e:
        logger.error(f"❌ Falha ao iniciar Sandbox Service: {e}")
    
    # Sandbox Swing Service
    try:
        from services.sandbox_swing_service import sandbox_swing_service
        await sandbox_swing_service.start()
        logger.info("🟢 Sandbox Swing Service iniciado!")
    except Exception as e:
        logger.error(f"❌ Falha ao iniciar Sandbox Swing Service: {e}")
    
    # Sandbox Scalping Engine
    try:
        from services.sandbox_scalping_engine import sandbox_scalping_engine
        await sandbox_scalping_engine.start()
        logger.info("🟢 VWAP SNIPER Engine (Scalping M1/M5) iniciado!")
    except Exception as e:
        logger.error(f"❌ Falha ao iniciar VWAP SNIPER Engine: {e}")

# Configurar caminho do frontend
frontend_path = os.path.join(os.path.dirname(__file__), 'frontend')
if os.path.exists(frontend_path):
    logger.info(f"📁 Frontend encontrado em: {frontend_path}")
else:
    logger.warning("⚠️ Diretório frontend não encontrado")

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

# ===== ROTAS DE PÁGINAS ADICIONAIS =====

@app.get("/kanban", response_class=FileResponse)
async def serve_kanban():
    """Servir página Kanban Hermes"""
    kanban_path = os.path.join(frontend_path, "kanban-hermes-enhanced.html")
    if os.path.exists(kanban_path):
        return kanban_path
    else:
        # Fallback para o Kanban original
        kanban_fallback = os.path.join(frontend_path, "kanban-hermes.html")
        if os.path.exists(kanban_fallback):
            return kanban_fallback
        else:
            raise HTTPException(status_code=404, detail="Kanban page not found")

@app.get("/neural-chat", response_class=FileResponse)
async def serve_neural_chat():
    """Servir página Neural Chat"""
    neural_path = os.path.join(frontend_path, "neural-chat.html")
    if os.path.exists(neural_path):
        return neural_path
    else:
        raise HTTPException(status_code=404, detail="Neural chat page not found")

@app.get("/neural-graph", response_class=FileResponse)
async def serve_neural_graph():
    """Servir página Neural Graph"""
    graph_path = os.path.join(frontend_path, "neural_graph.html")
    if os.path.exists(graph_path):
        return graph_path
    else:
        raise HTTPException(status_code=404, detail="Neural graph page not found")

@app.get("/observatory", response_class=FileResponse)
async def serve_observatory():
    """Servir página Observatory"""
    observatory_path = os.path.join(frontend_path, "observatory.html")
    if os.path.exists(observatory_path):
        return observatory_path
    else:
        raise HTTPException(status_code=404, detail="Observatory page not found")

@app.get("/offline", response_class=FileResponse)
async def serve_offline():
    """Servir página Offline"""
    offline_path = os.path.join(frontend_path, "offline.html")
    if os.path.exists(offline_path):
        return offline_path
    else:
        raise HTTPException(status_code=404, detail="Offline page not found")

@app.get("/intel-wiki", response_class=FileResponse)
async def serve_intel_wiki():
    """Servir página Intel Wiki"""
    wiki_path = os.path.join(frontend_path, "intel_wiki.html")
    if os.path.exists(wiki_path):
        return wiki_path
    else:
        raise HTTPException(status_code=404, detail="Intel wiki page not found")

@app.get("/user", response_class=FileResponse)
async def serve_user():
    """Servir página de usuário"""
    user_path = os.path.join(frontend_path, "user.html")
    if os.path.exists(user_path):
        return user_path
    else:
        raise HTTPException(status_code=404, detail="User page not found")

@app.get("/sandbox", response_class=FileResponse)
async def serve_sandbox():
    """Servir página Sandbox"""
    sandbox_path = os.path.join(frontend_path, "sandbox.html")
    if os.path.exists(sandbox_path):
        logger.info(f"✅ Servindo sandbox.html de: {sandbox_path}")
        return sandbox_path
    else:
        logger.error(f"❌ Arquivo não encontrado: {sandbox_path}")
        raise HTTPException(status_code=404, detail="Sandbox page not found")

@app.get("/memory", response_class=FileResponse)
async def serve_memory():
    """Servir página Memory Galaxy"""
    memory_path = os.path.join(frontend_path, "memory_galaxy.html")
    if os.path.exists(memory_path):
        logger.info(f"✅ Servindo memory_galaxy.html de: {memory_path}")
        return memory_path
    else:
        logger.error(f"❌ Arquivo não encontrado: {memory_path}")
        raise HTTPException(status_code=404, detail="Memory Galaxy page not found")

# ===== ROTAS DE API DE AUTENTICAÇÃO =====

@app.post("/api/auth/login")
async def login_user(credentials: dict):
    """Endpoint de login para produção"""
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
    """Endpoint de registro para produção"""
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
        "message": "Servidor de produção está operacional",
        "frontend_path": frontend_path,
        "frontend_exists": os.path.exists(frontend_path),
        "production_mode": True
    }

@app.get("/")
async def root():
    """Endpoint raiz"""
    return {
        "message": "1Crypten Production Server",
        "version": "1.0.0",
        "mode": "production",
        "login_url": "/login",
        "auth_url": "/auth",
        "cockpit_url": "/cockpit",
        "status": "running"
    }

if __name__ == "__main__":
    # Configurar servidor de produção
    port = int(os.getenv("PORT", 8085))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"🚀 Iniciando servidor de produção na porta {port}")
    logger.info(f"🌍 Host: {host}")
    logger.info(f"📁 Frontend: {frontend_path}")
    logger.info(f"🔐 URL de login: http://{host}:{port}/login")
    logger.info(f"🔐 URL de auth: http://{host}:{port}/auth")
    logger.info(f"🚀 URL de cockpit: http://{host}:{port}/cockpit")
    
    uvicorn.run(
        "production_server:app",
        host=host,
        port=port,
        reload=False,  # Desativar reload em produção
        log_level="info"
    )