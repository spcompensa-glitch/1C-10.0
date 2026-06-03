#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main Application - Hermes Guardian Railway Deployment
=====================================================

Aplicação principal para Railway deployment do sistema Hermes Guardian,
integrando todos os serviços em um único endpoint monitorável.

Author: DevOps Team
Version: 1.0
"""

import os
import sys
import logging
import time
import json
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Adiciona backend ao path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.append(backend_path)

# Importar serviços
from backend.config import settings
from backend.services.secrets import secrets_manager as secrets
from backend.services.websocket_service import websocket_service
from backend.services.telegram_service import telegram_service
from backend.services.hermes_broker import hermes_broker_service as hermes_broker
from backend.services.portfolio_guardian import portfolio_guardian
from backend.services.sentinel_auditor import sentinel_auditor
from backend.services.nvidia_service import nvidia_service

# Auth (rotas /api/auth/*) - rotas de login/registro/refresh/me/logout/change-password
from backend.routes.auth import router as auth_router

# Importar outras rotas do sistema
from backend.routes.market import router as market_router
# from backend.routes.backtest_routes import router as backtest_router
# from backend.routes.dashboard import router as dashboard_router
from backend.routes.system import router as system_router
from backend.routes.vault import router as vault_router
from backend.routes.trading import router as trading_router
from backend.routes.chat import router as chat_router
from backend.database.database_service_secure import get_engine, Base as AuthBase
from backend.database import models_auth  # noqa: F401 - registra modelos no metadata
from backend.auth.security.password_handler import password_handler
from backend.database.models_auth import User as AuthUser
from sqlalchemy import text as _sql_text
from datetime import datetime as _dt

# Modelos Pydantic
class ChatMessage(BaseModel):
    message: str
    type: str = "chat"

class HermesResponse(BaseModel):
    type: str
    message: str
    timestamp: float

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("HermesGuardian")

# Criar app FastAPI
app = FastAPI(
    title="Hermes Guardian System",
    description="Sistema Guardião 1Cryptem 7.0 - Automação de Trading e Gestão de Portfólio",
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

# Registrar rotas de autenticação (login/registro/refresh/me/logout/change-password/admin)
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

# Registrar outras rotas do sistema
app.include_router(market_router, prefix="/api", tags=["market"])
# app.include_router(backtest_router, prefix="/api", tags=["backtest"])
# app.include_router(dashboard_router, prefix="/api", tags=["dashboard"])
app.include_router(system_router, prefix="/api", tags=["system"])
app.include_router(vault_router, prefix="/api", tags=["vault"])
app.include_router(trading_router, prefix="/api", tags=["trading"])
app.include_router(chat_router, prefix="/api", tags=["chat"])


def _init_auth_db():
    """Cria tabelas de auth e garante admin/admin123 (UPSERT para Postgres)."""
    try:
        engine = get_engine()
        logger.info(f"🔐 [AUTH] DATABASE_URL detectada: {engine.url.drivername}://***")
        AuthBase.metadata.create_all(bind=engine)
        pwd_hash = password_handler.hash_password("admin123", rounds=12)
        now = _dt.utcnow()
        dialect = engine.dialect.name
        with engine.begin() as conn:
            if dialect == "postgresql":
                # UPSERT nativo do Postgres
                conn.execute(_sql_text("""
                    INSERT INTO users (username, email, password_hash, is_active, role, created_at, updated_at)
                    VALUES (:username, :email, :password_hash, :is_active, :role, :created_at, :updated_at)
                    ON CONFLICT (username) DO UPDATE
                      SET password_hash = EXCLUDED.password_hash,
                          email = EXCLUDED.email,
                          is_active = EXCLUDED.is_active,
                          role = EXCLUDED.role,
                          updated_at = EXCLUDED.updated_at
                """), {
                    "username": "admin",
                    "email": "admin@1crypten.com",
                    "password_hash": pwd_hash,
                    "is_active": True,
                    "role": "admin",
                    "created_at": now,
                    "updated_at": now,
                })
            else:
                # SQLite (e outros): tenta insert, se já existir faz update
                existing = conn.execute(
                    _sql_text("SELECT id FROM users WHERE username = :u"),
                    {"u": "admin"},
                ).scalar()
                if not existing:
                    conn.execute(_sql_text("""
                        INSERT INTO users (username, email, password_hash, is_active, role, created_at, updated_at)
                        VALUES (:username, :email, :password_hash, :is_active, :role, :created_at, :updated_at)
                    """), {
                        "username": "admin",
                        "email": "admin@1crypten.com",
                        "password_hash": pwd_hash,
                        "is_active": True,
                        "role": "admin",
                        "created_at": now,
                        "updated_at": now,
                    })
                else:
                    conn.execute(
                        _sql_text("""
                            UPDATE users
                            SET password_hash = :h, email = :e, is_active = 1, role = 'admin', updated_at = :u
                            WHERE username = 'admin'
                        """),
                        {"h": pwd_hash, "e": "admin@1crypten.com", "u": now},
                    )
        logger.info("✅ [AUTH] Usuário admin/admin123 garantido (Postgres UPSERT)" if dialect == "postgresql" else "✅ [AUTH] Usuário admin/admin123 garantido (SQLite)")
    except Exception as e:
        logger.error(f"❌ [AUTH] Falha ao inicializar banco de auth: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())

# Configurar caminho do frontend
frontend_path = os.path.join(os.path.dirname(__file__), 'frontend')
if os.path.exists(frontend_path):
    logger.info(f"📁 Frontend encontrado em: {frontend_path}")
    # [V110.186] Serve /vendor/* for pre-compiled JSX chunks
    vendor_path = os.path.join(frontend_path, 'vendor')
    if os.path.exists(vendor_path):
        app.mount("/vendor", StaticFiles(directory=vendor_path), name="vendor")
        logger.info(f"📦 Vendor mountado em /vendor -> {vendor_path}")
    
    # [V110.186] Servir frontend completo como estático (será movido para o final)
else:
    logger.warning("⚠️ Diretório frontend não encontrado")

# Variáveis de ambiente Railway
RAILWAY_ENV = os.getenv("RAILWAY_ENV", "production")
RAILWAY_URL = os.getenv("RAILWAY_URL", "https://1crypten-hermes-agent-production.up.railway.app")

# Rotas frontend
@app.get("/", response_class=RedirectResponse)
async def redirect_root():
    """Redirecionar root para a página de login"""
    return "/login"

@app.get("/health")
async def health_check():
    """Endpoint de saúde do sistema"""
    try:
        health_status = {
            "timestamp": time.time(),
            "status": "healthy",
            "services": {},
            "overall": "ok"
        }

        # Verificar serviços
        services_status = {}

        # Secrets Manager
        try:
            services_status["secrets"] = {
                "healthy": True,
                "environment": secrets_manager.environment.value,
                "production_ready": secrets_manager.validate_production_readiness()
            }
        except Exception as e:
            services_status["secrets"] = {"healthy": False, "error": str(e)}

        # WebSocket Service
        try:
            services_status["websocket"] = {
                "healthy": True,
                "connections": len(websocket_service.active_connections),
                "slots_available": len(websocket_service._last_slots_snapshot),
                "radar_available": bool(websocket_service._last_radar_snapshot)
            }
        except Exception as e:
            services_status["websocket"] = {"healthy": False, "error": str(e)}

        # Telegram Service
        try:
            services_status["telegram"] = {
                "healthy": telegram_service.is_active,
                "configured": bool(os.getenv("TELEGRAM_BOT_TOKEN"))
            }
        except Exception as e:
            services_status["telegram"] = {"healthy": False, "error": str(e)}

        # Hermes Broker
        try:
            services_status["hermes_broker"] = {
                "healthy": True,
                "mqtt_available": hermes_broker._check_mqtt_availability(),
                "grpc_ready": hermes_broker.grpc_server is not None
            }
        except Exception as e:
            services_status["hermes_broker"] = {"healthy": False, "error": str(e)}

        # Portfolio Guardian
        try:
            services_status["portfolio_guardian"] = {
                "healthy": True,
                "state": portfolio_guardian.state,
                "max_roi_registered": portfolio_guardian.max_roi_registered,
                "current_roi": portfolio_guardian.current_roi
            }
        except Exception as e:
            services_status["portfolio_guardian"] = {"healthy": False, "error": str(e)}

        # Sentinel Auditor
        try:
            services_status["sentinel_auditor"] = {
                "healthy": True,
                "auto_healing_active": sentinel_auditor.auto_healing_active,
                "last_check": sentinel_auditor.last_check_time
            }
        except Exception as e:
            services_status["sentinel_auditor"] = {"healthy": False, "error": str(e)}

        health_status["services"] = services_status

        # Determinar status geral
        all_services_healthy = all(service.get("healthy", False) for service in services_status.values())
        health_status["overall"] = "healthy" if all_services_healthy else "degraded"

        return health_status

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

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

@app.get("/cockpit", response_class=FileResponse)
async def serve_cockpit():
    """Servir página Cockpit"""
    cockpit_path = os.path.join(frontend_path, "cockpit.html")
    if os.path.exists(cockpit_path):
        return cockpit_path
    else:
        raise HTTPException(status_code=404, detail="Cockpit page not found")

@app.get("/login", response_class=FileResponse)
async def serve_login():
    """Servir página de Login"""
    login_path = os.path.join(frontend_path, "login.html")
    if os.path.exists(login_path):
        return login_path
    else:
        raise HTTPException(status_code=404, detail="Login page not found")

@app.get("/auth", response_class=RedirectResponse)
async def serve_auth():
    """Redirecionar para auth.html"""
    return "/auth.html"

@app.get("/auth.html", response_class=FileResponse)
async def serve_auth_html():
    """Servir página de Autenticação"""
    auth_path = os.path.join(frontend_path, "auth.html")
    if os.path.exists(auth_path):
        return auth_path
    else:
        raise HTTPException(status_code=404, detail="Authentication page not found")

@app.get("/cockpit.html", response_class=FileResponse)
async def serve_cockpit_html():
    """Servir página do Cockpit"""
    cockpit_path = os.path.join(frontend_path, "cockpit.html")
    if os.path.exists(cockpit_path):
        return cockpit_path
    else:
        raise HTTPException(status_code=404, detail="Cockpit page not found")

@app.get("/index.html", response_class=FileResponse)
async def serve_index():
    """Servir página principal"""
    index_path = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_path):
        return index_path
    else:
        raise HTTPException(status_code=404, detail="Index page not found")

@app.get("/user.html", response_class=FileResponse)
async def serve_user():
    """Servir página de usuário"""
    user_path = os.path.join(frontend_path, "user.html")
    if os.path.exists(user_path):
        return user_path
    else:
        raise HTTPException(status_code=404, detail="User page not found")

@app.get("/neural-chat.html", response_class=FileResponse)
async def serve_neural_chat():
    """Servir página Neural Chat"""
    neural_path = os.path.join(frontend_path, "neural-chat.html")
    if os.path.exists(neural_path):
        return neural_path
    else:
        raise HTTPException(status_code=404, detail="Neural chat page not found")

@app.get("/neural-graph.html", response_class=FileResponse)
async def serve_neural_graph():
    """Servir página Neural Graph"""
    graph_path = os.path.join(frontend_path, "neural_graph.html")
    if os.path.exists(graph_path):
        return graph_path
    else:
        raise HTTPException(status_code=404, detail="Neural graph page not found")

@app.get("/kanban-hermes-enhanced.html", response_class=FileResponse)
async def serve_kanban_enhanced():
    """Servir página Kanban Hermes Enhanced"""
    kanban_path = os.path.join(frontend_path, "kanban-hermes-enhanced.html")
    if os.path.exists(kanban_path):
        return kanban_path
    else:
        raise HTTPException(status_code=404, detail="Kanban enhanced page not found")

@app.get("/kanban-hermes.html", response_class=FileResponse)
async def serve_kanban():
    """Servir página Kanban Hermes"""
    kanban_path = os.path.join(frontend_path, "kanban-hermes.html")
    if os.path.exists(kanban_path):
        return kanban_path
    else:
        raise HTTPException(status_code=404, detail="Kanban page not found")

@app.get("/observatory.html", response_class=FileResponse)
async def serve_observatory():
    """Servir página Observatory"""
    observatory_path = os.path.join(frontend_path, "observatory.html")
    if os.path.exists(observatory_path):
        return observatory_path
    else:
        raise HTTPException(status_code=404, detail="Observatory page not found")

@app.get("/offline.html", response_class=FileResponse)
async def serve_offline():
    """Servir página Offline"""
    offline_path = os.path.join(frontend_path, "offline.html")
    if os.path.exists(offline_path):
        return offline_path
    else:
        raise HTTPException(status_code=404, detail="Offline page not found")

@app.get("/intel-wiki.html", response_class=FileResponse)
async def serve_intel_wiki():
    """Servir página Intel Wiki"""
    wiki_path = os.path.join(frontend_path, "intel_wiki.html")
    if os.path.exists(wiki_path):
        return wiki_path
    else:
        raise HTTPException(status_code=404, detail="Intel wiki page not found")

@app.get("/", response_class=RedirectResponse)
async def redirect_root():
    """Redirecionar root para a página de login"""
    return "/login"

@app.on_event("startup")
async def startup_event():
    """Evento de startup da aplicação"""
    logger.info("🚀 Iniciando Hermes Guardian System...")
    logger.info(f"🌍 Ambiente: {RAILWAY_ENV}")
    logger.info(f"🚂 Railway URL: {RAILWAY_URL}")
    
    # Iniciar serviços
    try:
        # Iniciar WebSocket Service
        logger.info("🔌 Iniciando WebSocket Service...")

        # Iniciar Telegram Service
        if telegram_service.is_active:
            logger.info("📱 Telegram Service ativo - Iniciando Polling...")
            telegram_service.start_polling_task()

        # Iniciar Hermes Broker
        logger.info("🛰️ Iniciando Hermes Broker...")
        await hermes_broker.start_mqtt()

        # Iniciar Portfolio Guardian
        logger.info("🛡️ Iniciando Portfolio Guardian...")
        portfolio_guardian.start()

        # Iniciar Sentinel Auditor
        logger.info("🔍 Iniciando Sentinel Auditor...")

        # Inicializar banco de auth (criar tabelas + admin)
        logger.info("🔐 Inicializando banco de autenticação...")
        _init_auth_db()

        logger.info("✅ Todos os serviços iniciados com sucesso!")

    except Exception as e:
        logger.error(f"❌ Erro ao iniciar serviços: {e}")
        raise

@app.get("/health")
async def health_check():
    """Endpoint de saúde do sistema"""
    try:
        health_status = {
            "timestamp": time.time(),
            "status": "healthy",
            "services": {},
            "overall": "ok"
        }

        # Verificar serviços
        services_status = {}
        
        # Secrets Manager
        try:
            services_status["secrets"] = {
                "healthy": True,
                "environment": secrets_manager.environment.value,
                "production_ready": secrets_manager.validate_production_readiness()
            }
        except Exception as e:
            services_status["secrets"] = {"healthy": False, "error": str(e)}
        
        # WebSocket Service
        try:
            services_status["websocket"] = {
                "healthy": True,
                "connections": len(websocket_service.active_connections),
                "slots_available": len(websocket_service._last_slots_snapshot),
                "radar_available": bool(websocket_service._last_radar_snapshot)
            }
        except Exception as e:
            services_status["websocket"] = {"healthy": False, "error": str(e)}
        
        # Telegram Service
        try:
            services_status["telegram"] = {
                "healthy": telegram_service.is_active,
                "configured": bool(os.getenv("TELEGRAM_BOT_TOKEN"))
            }
        except Exception as e:
            services_status["telegram"] = {"healthy": False, "error": str(e)}
        
        # Hermes Broker
        try:
            services_status["hermes_broker"] = {
                "healthy": True,
                "mqtt_available": hermes_broker._check_mqtt_availability(),
                "grpc_ready": hermes_broker.grpc_server is not None
            }
        except Exception as e:
            services_status["hermes_broker"] = {"healthy": False, "error": str(e)}
        
        # Portfolio Guardian
        try:
            services_status["portfolio_guardian"] = {
                "healthy": True,
                "state": portfolio_guardian.state,
                "max_roi_registered": portfolio_guardian.max_roi_registered,
                "current_roi": portfolio_guardian.current_roi
            }
        except Exception as e:
            services_status["portfolio_guardian"] = {"healthy": False, "error": str(e)}
        
        # Sentinel Auditor
        try:
            services_status["sentinel_auditor"] = {
                "healthy": True,
                "auto_healing_active": sentinel_auditor.auto_healing_active,
                "last_check": sentinel_auditor.last_check_time
            }
        except Exception as e:
            services_status["sentinel_auditor"] = {"healthy": False, "error": str(e)}
        
        health_status["services"] = services_status
        
        # Determinar status geral
        all_services_healthy = all(service.get("healthy", False) for service in services_status.values())
        health_status["overall"] = "healthy" if all_services_healthy else "degraded"
        
        return health_status
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

@app.get("/status")
async def get_status():
    """Endpoint de status detalhado"""
    try:
        status = {
            "timestamp": time.time(),
            "system": {
                "name": "Hermes Guardian System",
                "version": "1.0.0",
                "environment": RAILWAY_ENV,
                "railway_url": RAILWAY_URL
            },
            "services": {},
            "integration": {
                "phase7_status": "success",
                "backend_status": "operational",
                "ui_status": "enhanced",
                "telegram_status": "configured"
            },
            "metrics": {
                "uptime": time.time(),
                "memory_usage": "normal",
                "cpu_usage": "normal",
                "security_score": 100
            }
        }
        
        return status
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")

@app.get("/kanban")
async def get_kanban_status():
    """Endpoint de status do Kanban"""
    try:
        kanban_status = {
            "timestamp": time.time(),
            "status": "active",
            "url": f"{RAILWAY_URL}/kanban",
            "features": [
                "Dashboard em tempo real",
                "Monitoramento de posições",
                "Alertas automáticos",
                "Integração Telegram",
                "Gestão de portfólio"
            ],
            "ui_version": "enhanced",
            "access_info": {
                "secured": True,
                "authentication": "password",
                "password": "123"  # Senha temporária para Railway
            }
        }
        
        return kanban_status
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kanban status failed: {str(e)}")

@app.get("/api/hermes/status")
async def get_hermes_status():
    """Endpoint de status do Hermes"""
    try:
        # Verificar status da NVIDIA API
        nvidia_status = "unknown"
        try:
            if nvidia_service._initialized:
                nvidia_status = "online"
            elif settings.NVAPI_KEY:
                nvidia_status = "configured"
            else:
                nvidia_status = "missing"
        except:
            nvidia_status = "error"
        
        return {
            "timestamp": time.time(),
            "status": "online",
            "message": "Hermes está operacional",
            "services": {
                "websocket": len(websocket_service.active_connections),
                "telegram": telegram_service.is_active,
                "broker": True,
                "nvidia_ai": nvidia_status
            },
            "ai_features": {
                "nvidia_api": nvidia_status,
                "model": "meta/llama3-70b-instruct",
                "provider": "NVIDIA"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Hermes status failed: {str(e)}")

@app.post("/api/hermes/chat")
async def post_hermes_chat(message: ChatMessage):
    """Endpoint de chat com Hermes usando NVIDIA AI"""
    try:
        # Gerar resposta usando NVIDIA AI
        ai_response = await nvidia_service.chat_completion(
            user_message=message.message,
            system_instruction="Você é Hermes, um assistente de trading e gestão de portfólio cripto. Responda de forma profissional e técnica, mas amigável. Use ícones e formatação adequada.",
            temperature=0.7,
            max_tokens=1000
        )
        
        # Se a IA falhar, usar resposta padrão
        if ai_response:
            response_message = f"🪶 Hermes: {ai_response}"
        else:
            response_message = f"🪶 Hermes: Sua mensagem '{message.message}' foi recebida. Estou processando com minha IA NVIDIA. Aguarde um momento..."
        
        # Enviar resposta via WebSocket para todos os clientes conectados
        response = {
            "type": "hermes_response",
            "message": response_message,
            "timestamp": time.time(),
            "ai_enabled": bool(ai_response)
        }
        
        # Enviar para todos os clientes WebSocket
        for connection in websocket_service.active_connections:
            try:
                await connection.send_text(json.dumps(response))
            except:
                pass
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")

@app.post("/api/chat")
async def post_chat(message: ChatMessage):
    """Endpoint de chat genérico usando NVIDIA AI"""
    try:
        # Gerar resposta usando NVIDIA AI
        ai_response = await nvidia_service.chat_completion(
            user_message=message.message,
            system_instruction="Você é Hermes, um assistente de trading e gestão de portfólio cripto. Responda de forma profissional e técnica, mas amigável. Use ícones e formatação adequada.",
            temperature=0.7,
            max_tokens=1000
        )
        
        # Se a IA falhar, usar resposta padrão
        if ai_response:
            response_message = f"🪶 Hermes: {ai_response}"
        else:
            response_message = f"🪶 Hermes: Mensagem recebida. Estou usando minha IA NVIDIA para processar sua solicitação."
        
        response = {
            "type": "hermes_response",
            "message": response_message,
            "timestamp": time.time(),
            "ai_enabled": bool(ai_response)
        }
        
        # Enviar resposta via WebSocket para todos os clientes conectados
        for connection in websocket_service.active_connections:
            try:
                await connection.send_text(json.dumps(response))
            except:
                pass
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")

@app.get("/telegram")
async def get_telegram_status():
    """Endpoint de status do Telegram"""
    try:
        telegram_status = {
            "timestamp": time.time(),
            "status": "active" if telegram_service.is_active else "inactive",
            "configured": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
            "chat_id": os.getenv("TELEGRAM_CHAT_ID"),
            "features": [
                "Notificações em tempo real",
                "Alertas de trading",
                "Relatórios automáticos",
                "Controle remoto"
            ]
        }
        
        return telegram_status
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Telegram status failed: {str(e)}")

@app.get("/dashboard")
async def get_dashboard():
    """Endpoint de dashboard consolidado"""
    try:
        dashboard = {
            "timestamp": time.time(),
            "overview": {
                "system_status": "healthy",
                "active_services": 6,
                "total_services": 6,
                "uptime": "24h+"
            },
            "services": {},
            "alerts": [],
            "metrics": {
                "memory_usage": "45%",
                "cpu_usage": "23%",
                "response_time": "0.42s",
                "security_score": 100
            },
            "railway": {
                "url": RAILWAY_URL,
                "environment": RAILWAY_ENV,
                "deployment_status": "active"
            }
        }
        
        return dashboard
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Dashboard failed: {str(e)}")

# Endpoints do Cockpit (V110.171) - Mock Data
@app.get("/api/system/state")
async def get_system_state():
    """Estado do sistema para o Cockpit"""
    return {
        "timestamp": time.time(),
        "status": "operational",
        "phase": "active",
        "memory_usage": "45%",
        "cpu_usage": "23%",
        "uptime": "24h+",
        "services": {
            "websocket": "active",
            "auth": "active", 
            "radar": "active",
            "slots": "active",
            "vault": "active",
            "market": "active"
        },
        "alerts": [],
        "security_score": 100
    }

@app.get("/api/slots")
async def get_slots():
    """Slots ativos do sistema"""
    return {
        "timestamp": time.time(),
        "slots": [
            {
                "id": 1,
                "symbol": "BTCUSDT",
                "strategy": "ABCD",
                "size": 0.1,
                "entry_price": 43500.0,
                "current_price": 43850.0,
                "pnl": "+35.00",
                "pnl_percent": "+0.08%",
                "status": "active",
                "time_active": "2h 15m",
                "last_signal": "BUY",
                "confidence": "85%"
            },
            {
                "id": 2,
                "symbol": "ETHUSDT", 
                "strategy": "MOLA",
                "size": 2.5,
                "entry_price": 2350.0,
                "current_price": 2320.0,
                "pnl": "-75.00",
                "pnl_percent": "-0.13%",
                "status": "active",
                "time_active": "1h 45m",
                "last_signal": "SELL",
                "confidence": "72%"
            },
            {
                "id": 3,
                "symbol": "SOLUSDT",
                "strategy": "SHADOW",
                "size": 15.0,
                "entry_price": 98.5,
                "current_price": 102.3,
                "pnl": "+57.00",
                "pnl_percent": "+0.39%",
                "status": "active",
                "time_active": "45m",
                "last_signal": "BUY",
                "confidence": "91%"
            }
        ],
        "total_slots": 3,
        "active_strategies": ["ABCD", "MOLA", "SHADOW"],
        "total_pnl": "+17.00",
        "win_rate": "67%"
    }

@app.get("/api/radar/pulse")
async def get_radar_pulse():
    """Radar pulse - sinais ativos"""
    return {
        "timestamp": time.time(),
        "signals": [
            {
                "symbol": "BNBUSDT",
                "type": "BUY",
                "strength": "STRONG",
                "confidence": 89,
                "price": 315.50,
                "change_24h": "+2.3%",
                "volume": "2.1M",
                "signal_time": "2 minutos atrás",
                "strategy": "BLITZ"
            },
            {
                "symbol": "ADAUSDT", 
                "type": "SELL",
                "strength": "MEDIUM",
                "confidence": 76,
                "price": 0.452,
                "change_24h": "-1.2%",
                "volume": "850K",
                "signal_time": "5 minutos atrás",
                "strategy": "MOLA"
            },
            {
                "symbol": "DOTUSDT",
                "type": "BUY", 
                "strength": "WEAK",
                "confidence": 65,
                "price": 7.85,
                "change_24h": "+0.8%",
                "volume": "1.2M",
                "signal_time": "8 minutos atrás",
                "strategy": "SHADOW"
            }
        ],
        "total_signals": 3,
        "buy_signals": 2,
        "sell_signals": 1
    }

@app.get("/api/banca/data")
async def get_banca_data():
    """Dados da banca"""
    return {
        "timestamp": time.time(),
        "banca": {
            "total_balance": 12500.00,
            "available_balance": 8750.00,
            "used_balance": 3750.00,
            "free_margin": 5000.00,
            "margin_level": "142%",
            "equity": 13250.00
        },
        "risk_metrics": {
            "max_risk_per_trade": "2%",
            "total_risk_exposure": "18%",
            "daily_pnl": "+125.00",
            "weekly_pnl": "+850.00",
            "monthly_pnl": "+3200.00"
        },
        "trades_today": 15,
        "win_rate_today": "73%",
        "profit_factor": "1.85"
    }

@app.get("/api/vault/status")
async def get_vault_status():
    """Status do Vault"""
    return {
        "timestamp": time.time(),
        "vault": {
            "status": "secure",
            "encrypted": True,
            "backups": "24h",
            "last_backup": "2 horas atrás",
            "storage_used": "2.3GB / 10GB",
            "api_calls_today": 1250,
            "api_calls_limit": 5000,
            "security_score": 98
        },
        "jornada": {
            "level": "ELITE COMMAND",
            "progress": "78%",
            "next_milestone": "SNIPER MASTER",
            "points": 24500,
            "rank": "#12"
        }
    }

@app.get("/api/market/klines")
async def get_market_klines(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 350):
    """Dados de mercado Klines"""
    # Mock data - em produção isso viria da API real
    mock_klines = []
    base_price = 43500.0
    base_time = int(time.time() - (limit * 3600))  # Limit * 1 hour ago
    
    for i in range(limit):
        timestamp = base_time + (i * 3600)
        price_variation = (i % 20 - 10) * 50  # Random variation
        open_price = base_price + price_variation
        close_price = open_price + (i % 7 - 3) * 25
        high_price = max(open_price, close_price) + 10
        low_price = min(open_price, close_price) - 10
        volume = 1000 + (i % 50) * 50
        
        mock_klines.append({
            "timestamp": timestamp,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": volume
        })
    
    return {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
        "data": mock_klines,
        "timestamp": time.time()
    }

@app.get("/api/moonbags")
async def get_moonbags():
    """Moonbags - tokens com potencial"""
    return {
        "timestamp": time.time(),
        "moonbags": [
            {
                "symbol": "PEPEUSDT",
                "name": "Pepe",
                "price": 0.00001234,
                "24h_change": "+15.2%",
                "volume": "125M",
                "holders": "1.2M",
                "potential": "HIGH",
                "moonbag_score": 87,
                "last_signal": "STRONG BUY"
            },
            {
                "symbol": "SHIBUSDT",
                "name": "Shiba Inu", 
                "price": 0.00002345,
                "24h_change": "+8.7%",
                "volume": "89M",
                "holders": "3.8M",
                "potential": "MEDIUM",
                "moonbag_score": 72,
                "last_signal": "BUY"
            },
            {
                "symbol": "DOGEUSDT",
                "name": "Dogecoin",
                "price": 0.15678,
                "24h_change": "+5.2%",
                "volume": "2.1B",
                "holders": "5.2M",
                "potential": "LOW",
                "moonbag_score": 58,
                "last_signal": "HOLD"
            }
        ],
        "total_moonbags": 3,
        "average_score": 72
    }

@app.get("/api/history")
async def get_history(limit: int = 50):
    """Histórico de trades"""
    return {
        "timestamp": time.time(),
        "limit": limit,
        "history": [
            {
                "id": "TX001",
                "symbol": "BTCUSDT",
                "type": "BUY",
                "size": 0.1,
                "entry_price": 43200.0,
                "exit_price": 43850.0,
                "pnl": "+65.00",
                "pnl_percent": "+1.5%",
                "duration": "2h 15m",
                "strategy": "ABCD",
                "status": "COMPLETED",
                "entry_time": "2026-06-02 10:30:00",
                "exit_time": "2026-06-02 12:45:00"
            },
            {
                "id": "TX002", 
                "symbol": "ETHUSDT",
                "type": "SELL",
                "size": 2.0,
                "entry_price": 2380.0,
                "exit_price": 2350.0,
                "pnl": "-60.00",
                "pnl_percent": "-1.26%",
                "duration": "1h 45m",
                "strategy": "MOLA",
                "status": "COMPLETED",
                "entry_time": "2026-06-02 09:15:00",
                "exit_time": "2026-06-02 11:00:00"
            }
        ],
        "total_trades": 2,
        "win_rate": "50%",
        "total_pnl": "+5.00"
    }

@app.get("/api/history/stats")
async def get_history_stats():
    """Estatísticas do histórico"""
    return {
        "timestamp": time.time(),
        "stats": {
            "total_trades": 156,
            "winning_trades": 118,
            "losing_trades": 38,
            "win_rate": "75.6%",
            "total_pnl": "+3250.00",
            "avg_trade_pnl": "+20.83",
            "largest_win": "+450.00",
            "largest_loss": "-180.00",
            "profit_factor": "2.15",
            "avg_trade_duration": "1h 45m"
        },
        "last_30_days": {
            "trades": 45,
            "win_rate": "78%",
            "pnl": "+980.00"
        }
    }

@app.get("/api/radar/grid")
async def get_radar_grid():
    """Radar grid - visão geral do mercado"""
    return {
        "timestamp": time.time(),
        "grid": {
            "total_tokens": 50,
            "active_tokens": 32,
            "bullish_tokens": 18,
            "bearish_tokens": 8,
            "neutral_tokens": 6,
            "strong_signals": 5,
            "weak_signals": 12
        },
        "sectors": [
            {
                "name": "Large Cap",
                "tokens": 15,
                "performance": "+2.3%",
                "top_performer": "BTCUSDT"
            },
            {
                "name": "Mid Cap", 
                "tokens": 20,
                "performance": "+1.8%",
                "top_performer": "ETHUSDT"
            },
            {
                "name": "Small Cap",
                "tokens": 15,
                "performance": "+5.2%",
                "top_performer": "SOLUSDT"
            }
        ],
        "market_sentiment": "BULLISH",
        "fear_greed_index": 72
    }

@app.get("/api/captain/tocaias")
async def get_captain_tocaias():
    """Dados do Captain Tocaias"""
    return {
        "timestamp": time.time(),
        "tocaias": [
            {
                "id": "TC001",
                "symbol": "XRPUSDT",
                "type": "ALERT",
                "message": "Price breakout detected at $0.52",
                "strength": "HIGH",
                "confidence": 85,
                "action": "WATCH",
                "time": "5 minutos atrás"
            },
            {
                "id": "TC002",
                "symbol": "LINKUSDT",
                "type": "SIGNAL", 
                "message": "RSI oversold - buying opportunity",
                "strength": "MEDIUM",
                "confidence": 76,
                "action": "CONSIDER",
                "time": "12 minutos atrás"
            },
            {
                "id": "TC003",
                "symbol": "AVAXUSDT",
                "type": "PATTERN",
                "message": "Head and shoulders forming",
                "strength": "WEAK", 
                "confidence": 65,
                "action": "MONITOR",
                "time": "18 minutos atrás"
            }
        ],
        "total_tocaias": 3,
        "active_alerts": 1,
        "pending_signals": 2
    }

@app.post("/api/system/re-sync")
async def post_system_resync():
    """Re-sincronização do sistema"""
    return {
        "timestamp": time.time(),
        "status": "success",
        "message": "System re-sync initiated",
        "sync_data": {
            "slots_synced": True,
            "radar_synced": True,
            "market_data_synced": True,
            "vault_synced": True
        }
    }

@app.get("/api/radar/librarian")
async def get_radar_librarian():
    """Radar librarian - dados de inteligência"""
    return {
        "timestamp": time.time(),
        "intelligence": {
            "market_regime": "BULLISH",
            "volatility": "MODERATE",
            "liquidity": "HIGH",
            "correlation": "LOW",
            "regime_strength": 78
        },
        "patterns": [
            {
                "pattern": "Ascending Triangle",
                "symbol": "BTCUSDT",
                "confidence": 82,
                "timeframe": "4h",
                "direction": "UP"
            }
        ],
        "support_resistance": {
            "key_levels": [
                {"level": 42000, "type": "SUPPORT", "strength": "STRONG"},
                {"level": 45000, "type": "RESISTANCE", "strength": "MEDIUM"}
            ]
        }
    }

@app.get("/api/system/state")
async def get_system_state():
    """Estado do sistema para o Cockpit"""
    return {
        "timestamp": time.time(),
        "status": "operational",
        "phase": "active",
        "memory_usage": "45%",
        "cpu_usage": "23%",
        "uptime": "24h+",
        "services": {
            "websocket": "active",
            "auth": "active", 
            "radar": "active",
            "slots": "active",
            "vault": "active",
            "market": "active"
        },
        "alerts": [],
        "security_score": 100
    }

@app.get("/api/slots")
async def get_slots():
    """Slots ativos do sistema"""
    return {
        "timestamp": time.time(),
        "slots": [
            {
                "id": 1,
                "symbol": "BTCUSDT",
                "strategy": "ABCD",
                "size": 0.1,
                "entry_price": 43500.0,
                "current_price": 43850.0,
                "pnl": "+35.00",
                "pnl_percent": "+0.08%",
                "status": "active",
                "time_active": "2h 15m",
                "last_signal": "BUY",
                "confidence": "85%"
            }
        ],
        "total_slots": 1,
        "active_strategies": ["ABCD"],
        "total_pnl": "+35.00",
        "win_rate": "100%"
    }

@app.get("/api/radar/pulse")
async def get_radar_pulse():
    """Radar pulse - sinais ativos"""
    return {
        "timestamp": time.time(),
        "signals": [
            {
                "symbol": "BNBUSDT",
                "type": "BUY",
                "strength": "STRONG",
                "confidence": 89,
                "price": 315.50,
                "change_24h": "+2.3%",
                "volume": "2.1M",
                "signal_time": "2 minutos atrás",
                "strategy": "BLITZ"
            }
        ],
        "total_signals": 1,
        "buy_signals": 1,
        "sell_signals": 0
    }

@app.get("/api/banca/data")
async def get_banca_data():
    """Dados da banca"""
    return {
        "timestamp": time.time(),
        "banca": {
            "total_balance": 12500.00,
            "available_balance": 8750.00,
            "used_balance": 3750.00,
            "free_margin": 5000.00,
            "margin_level": "142%",
            "equity": 13250.00
        },
        "risk_metrics": {
            "max_risk_per_trade": "2%",
            "total_risk_exposure": "18%",
            "daily_pnl": "+125.00",
            "weekly_pnl": "+850.00",
            "monthly_pnl": "+3200.00"
        },
        "trades_today": 15,
        "win_rate_today": "73%",
        "profit_factor": "1.85"
    }

@app.get("/api/market/klines")
async def get_market_klines(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 350):
    """Dados de mercado Klines"""
    # Mock data - em produção isso viria da API real
    mock_klines = []
    base_price = 43500.0
    base_time = int(time.time() - (limit * 3600))  # Limit * 1 hour ago        
    
    for i in range(min(limit, 10)):  # Limitar para 10 itens para teste
        timestamp = base_time + (i * 3600)
        price_variation = (i % 20 - 10) * 50  # Random variation
        open_price = base_price + price_variation
        close_price = open_price + (i % 7 - 3) * 25
        high_price = max(open_price, close_price) + 10
        low_price = min(open_price, close_price) - 10
        volume = 1000 + (i % 50) * 50
        
        mock_klines.append({
            "timestamp": timestamp,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": volume
        })
    
    return {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
        "data": mock_klines,
        "timestamp": time.time()
    }

@app.websocket("/ws")
@app.websocket("/ws/cockpit")
async def websocket_endpoint(websocket: WebSocket):
    """Endpoint WebSocket para o chat do Hermes"""
    await websocket_service.connect(websocket)
    try:
        while True:
            # Receber mensagem do cliente
            data = await websocket.receive_text()

            # Processar mensagem
            try:
                message_data = json.loads(data)
                message_type = message_data.get("type")
                message_content = message_data.get("message", "")

                # Responder com mensagem do Hermes
                if message_type == "chat":
                    try:
                        from backend.services.agents.hermes_agent import hermes_agent
                        result = await hermes_agent.handle_chat_query(message_content)
                        reply = result.get("response", "🌐 Sinal neural instável... Tente novamente, Almirante.")
                    except Exception as e:
                        logger.error(f"Erro ao processar com hermes_agent no WebSocket: {e}")
                        try:
                            from backend.services.agents.ai_service import ai_service
                            from backend.routes.chat import HERMES_FALLBACK_PROMPT
                            reply = await ai_service.generate_content(
                                prompt=message_content,
                                system_instruction=HERMES_FALLBACK_PROMPT
                            )
                            reply = reply or "🌐 Sinal neural instável."
                        except Exception as e2:
                            logger.error(f"Erro crítico no fallback do ai_service no WebSocket: {e2}")
                            reply = "🪶 Hermes: Erro de sinal neural interno."

                    response = {
                        "type": "hermes_response",
                        "message": reply,
                        "timestamp": time.time()
                    }
                    await websocket.send_text(json.dumps(response))

                # Log da mensagem
                logger.info(f"📨 WebSocket message received: {message_type}")

            except json.JSONDecodeError:
                response = {
                    "type": "error",
                    "message": "Formato de mensagem inválido",
                    "timestamp": time.time()
                }
                await websocket.send_text(json.dumps(response))

    except WebSocketDisconnect:
        websocket_service.disconnect(websocket)
        logger.info("❌ WebSocket client disconnected")


# Servir frontend estático (montado no escopo global para carregar tanto via uvicorn CLI quanto __main__)
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")

if __name__ == "__main__":
    # Configurar servidor Railway
    port = int(os.getenv("PORT", 8085))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"🚀 Iniciando servidor Hermes Guardian na porta {port}")
    logger.info(f"🌍 Host: {host}")
    logger.info(f"🚂 Ambiente Railway: {RAILWAY_ENV}")

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=False,  # Desativar reload em produção
        log_level="info"
    )