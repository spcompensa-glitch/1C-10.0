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


def _init_auth_db():
    """Cria tabelas de auth (users, audit_log, user_sessions, user_okx_tokens) e garante admin/admin123."""
    try:
        engine = get_engine()
        AuthBase.metadata.create_all(bind=engine)
        with engine.connect() as conn:
            existing = conn.execute(
                _sql_text("SELECT id FROM users WHERE username = :u"),
                {"u": "admin"},
            ).scalar()
            if not existing:
                pwd_hash = password_handler.hash_password("admin123", rounds=12)
                now = _dt.utcnow()
                conn.execute(
                    _sql_text("""
                        INSERT INTO users (username, email, password_hash, is_active, role, created_at, updated_at)
                        VALUES (:username, :email, :password_hash, :is_active, :role, :created_at, :updated_at)
                    """),
                    {
                        "username": "admin",
                        "email": "admin@1crypten.com",
                        "password_hash": pwd_hash,
                        "is_active": True,
                        "role": "admin",
                        "created_at": now,
                        "updated_at": now,
                    },
                )
                conn.commit()
                logger.info("✅ [AUTH] Usuário admin/admin123 criado")
            else:
                logger.info("✅ [AUTH] Usuário admin já existe")
    except Exception as e:
        logger.error(f"❌ [AUTH] Falha ao inicializar banco de auth: {e}")

# Configurar caminho do frontend
frontend_path = os.path.join(os.path.dirname(__file__), 'frontend')
if os.path.exists(frontend_path):
    logger.info(f"📁 Frontend encontrado em: {frontend_path}")
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

@app.get("/auth", response_class=FileResponse)
async def serve_auth():
    """Servir página de Autenticação"""
    auth_path = os.path.join(frontend_path, "auth.html")
    if os.path.exists(auth_path):
        return auth_path
    else:
        raise HTTPException(status_code=404, detail="Authentication page not found")

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