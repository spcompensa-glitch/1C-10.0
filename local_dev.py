#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor Local de Desenvolvimento - Auth + Backend Completo + Frontend
======================================================================

Sobe um único servidor FastAPI na porta 8085 servindo:
  - Frontend HTML (/login, /auth, /cockpit, etc.)
  - API de Autenticação em /api/auth/* (login, register, me, ...)
  - Todas as rotas do backend de trading (montadas a partir de main.py)
  - Inicialização automática do banco SQLite (auth.db)

Uso:
    python local_dev.py

Author: Sistema 1Crypten
"""
import os
import sys
import logging
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

# Garante que tanto a raiz quanto backend estao no sys.path
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
import uvicorn

# Importa o router de auth (de backend/routes/auth.py)
from routes.auth import router as auth_router
from database.database_service_secure import get_engine, Base
from database import models_auth  # noqa: F401  - registra modelos no metadata
from auth.security.password_handler import password_handler
from database.models_auth import User
from sqlalchemy import text
from datetime import datetime
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("local-dev")

# [HERMES DASHBOARD V2] Serviço do Hermes Web Dashboard
HERMES_DASHBOARD_ENABLED = os.getenv("HERMES_DASHBOARD_ENABLED", "true").lower() in ("true", "1", "t", "yes")
hermes_dashboard_service = None

PORT = int(os.getenv("PORT", 8085))
HOST = os.getenv("HOST", "0.0.0.0")
FULL_TRADING_LOOPS = os.getenv("LOCAL_DEV_FULL_TRADING", "0").lower() in {"1", "true", "yes", "on"}


def init_database():
    """Cria tabelas e garante usuário admin/admin123."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT id FROM users WHERE username = :u"),
            {"u": "admin"},
        ).scalar()

        if not existing:
            pwd_hash = password_handler.hash_password("admin123", rounds=12)
            now = datetime.utcnow()
            conn.execute(
                text("""
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
            logger.info("✅ Usuário admin/admin123 criado")
        else:
            logger.info("✅ Usuário admin já existe")


async def init_trading_database():
    """Inicializa o DB de trading (slots, radar_pulse, banca_status, etc.) e faz seed."""
    from services.database_service import database_service, Slot, BancaStatus
    from sqlalchemy import select

    try:
        await database_service.initialize()
        logger.info("✅ Trading DB tables inicializadas (slots/radar_pulse/banca_status/etc)")
    except Exception as e:
        logger.error(f"❌ Falha ao inicializar trading DB: {e}")
        return

    try:
        async with database_service.AsyncSessionLocal() as session:
            existing_slots = (await session.execute(select(Slot))).scalars().all()
            if not existing_slots:
                for i in range(1, 5):
                    session.add(Slot(id=i, status_risco="LIVRE", leverage=50.0))
                await session.commit()
                logger.info("✅ 4 slots vazios criados (id=1..4)")
            else:
                logger.info(f"✅ {len(existing_slots)} slots já existentes")

            banca = await session.get(BancaStatus, 1)
            if not banca:
                session.add(BancaStatus(
                    id=1,
                    saldo_total=100.0,
                    risco_real_percent=0.0,
                    slots_disponiveis=4,
                    status="IDLE",
                ))
                await session.commit()
                logger.info("✅ BancaStatus inicial criada ($100.00, 4 slots)")
            else:
                logger.info(f"✅ BancaStatus já existe (saldo=${banca.saldo_total})")

            # Seed dummy trade in history if empty to allow visual testing
            from services.database_service import TradeHistory
            existing_history = (await session.execute(select(TradeHistory))).scalars().all()
            if not existing_history:
                session.add(TradeHistory(
                    order_id="dummy_1780596241984",
                    genesis_id="PEPEUSDT_1780596241984",
                    symbol="PEPEUSDT",
                    side="SELL",
                    pnl=-0.08,
                    pnl_percent=-4.0,
                    entry_price=0.00001550,
                    exit_price=0.00001612,
                    strategy="SNIPER",
                    close_reason="STOP_LOSS",
                    timestamp=datetime.utcnow(),
                    data={
                        "symbol": "PEPEUSDT",
                        "side": "SELL",
                        "pnl": -0.08,
                        "pnl_percent": -4.0,
                        "entry_price": 0.00001550,
                        "exit_price": 0.00001612,
                        "strategy": "SNIPER",
                        "close_reason": "STOP_LOSS",
                        "leverage": 50,
                        "margin": 2.0
                    }
                ))
                await session.commit()
                logger.info("✅ Trade dummy de teste inserido no histórico local")
    except Exception as e:
        logger.error(f"❌ Falha ao fazer seed de slots/banca/histórico: {e}")


# Importa o app principal (cockpit data, websocket, hermes, etc.)
# Importamos DEPOIS de garantir sys.path e env carregados.
try:
    import main as main_module
    MAIN_APP = main_module.app
    logger.info("✅ main.py importado — rotas de cockpit/banca/slots OK")
except Exception as e:
    logger.warning(f"⚠️ Não foi possível importar main.py: {e}")
    MAIN_APP = None


# Agentes/loops de trading (captain + signal generator) — só inicializamos aqui
# porque o main.py da raiz não chama monitor_signals() no startup.
_captain_agent = None
_sig_gen = None
_harvester_agent = None
try:
    from services.agents.captain import captain_agent as _captain_agent  # type: ignore
    logger.info("✅ captain_agent importado")
except Exception as e:
    logger.warning(f"⚠️ captain_agent não importou: {e}")



def init_database():
    """Cria tabelas e garante usuário admin/admin123."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT id FROM users WHERE username = :u"),
            {"u": "admin"},
        ).scalar()

        if not existing:
            pwd_hash = password_handler.hash_password("admin123", rounds=12)
            now = datetime.utcnow()
            conn.execute(
                text("""
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
            logger.info("✅ Usuário admin/admin123 criado")
        else:
            logger.info("✅ Usuário admin já existe")


async def init_trading_database():
    """Inicializa o DB de trading (slots, radar_pulse, banca_status, etc.) e faz seed."""
    from services.database_service import database_service, Slot, BancaStatus
    from sqlalchemy import select

    try:
        await database_service.initialize()
        logger.info("✅ Trading DB tables inicializadas (slots/radar_pulse/banca_status/etc)")
    except Exception as e:
        logger.error(f"❌ Falha ao inicializar trading DB: {e}")
        return

    try:
        async with database_service.AsyncSessionLocal() as session:
            existing_slots = (await session.execute(select(Slot))).scalars().all()
            if not existing_slots:
                for i in range(1, 5):
                    session.add(Slot(id=i, status_risco="LIVRE", leverage=50.0))
                await session.commit()
                logger.info("✅ 4 slots vazios criados (id=1..4)")
            else:
                logger.info(f"✅ {len(existing_slots)} slots já existentes")

            banca = await session.get(BancaStatus, 1)
            if not banca:
                session.add(BancaStatus(
                    id=1,
                    saldo_total=100.0,
                    risco_real_percent=0.0,
                    slots_disponiveis=4,
                    status="IDLE",
                ))
                await session.commit()
                logger.info("✅ BancaStatus inicial criada ($100.00, 4 slots)")
            else:
                logger.info(f"✅ BancaStatus já existe (saldo=${banca.saldo_total})")

            # Seed dummy trade in history if empty to allow visual testing
            from services.database_service import TradeHistory
            existing_history = (await session.execute(select(TradeHistory))).scalars().all()
            if not existing_history:
                session.add(TradeHistory(
                    order_id="dummy_1780596241984",
                    genesis_id="PEPEUSDT_1780596241984",
                    symbol="PEPEUSDT",
                    side="SELL",
                    pnl=-0.08,
                    pnl_percent=-4.0,
                    entry_price=0.00001550,
                    exit_price=0.00001612,
                    strategy="SNIPER",
                    close_reason="STOP_LOSS",
                    timestamp=datetime.utcnow(),
                    data={
                        "symbol": "PEPEUSDT",
                        "side": "SELL",
                        "pnl": -0.08,
                        "pnl_percent": -4.0,
                        "entry_price": 0.00001550,
                        "exit_price": 0.00001612,
                        "strategy": "SNIPER",
                        "close_reason": "STOP_LOSS",
                        "leverage": 50,
                        "margin": 2.0
                    }
                ))
                await session.commit()
                logger.info("✅ Trade dummy de teste inserido no histórico local")
    except Exception as e:
        logger.error(f"❌ Falha ao fazer seed de slots/banca/histórico: {e}")


# Importa o app principal (cockpit data, websocket, hermes, etc.)
# Importamos DEPOIS de garantir sys.path e env carregados.
try:
    import main as main_module
    MAIN_APP = main_module.app
    logger.info("✅ main.py importado — rotas de cockpit/banca/slots OK")
except Exception as e:
    logger.warning(f"⚠️ Não foi possível importar main.py: {e}")
    MAIN_APP = None


# Agentes/loops de trading (captain + signal generator) — só inicializamos aqui
# porque o main.py da raiz não chama monitor_signals() no startup.
_captain_agent = None
_sig_gen = None
try:
    from services.agents.captain import captain_agent as _captain_agent  # type: ignore
    logger.info("✅ captain_agent importado")
except Exception as e:
    logger.warning(f"⚠️ captain_agent não importou: {e}")

try:
    from services.signal_generator import signal_generator as _sig_gen  # type: ignore
    logger.info("✅ signal_generator importado")
except Exception as e:
    logger.warning(f"⚠️ signal_generator não importou: {e}")

# harvester_agent consolidated into FlashAgent


# Cria app FastAPI próprio
app = FastAPI(
    title="1Crypten - Local Dev",
    version="1.0.0-local",
    description="Servidor local com auth + backend completo + frontend",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1) API de autenticação em /api/auth
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

# Mount antigo desativado; o app principal e montado depois das rotas locais.
if False:
    try:
        app.mount("/", MAIN_APP)
        logger.info("✅ Backend completo (main.py) montado em /")
    except Exception as e:
        logger.warning(f"⚠️ Falha ao montar main.py: {e}")


# 3) Frontend - páginas HTML
FRONTEND_PAGES = {
    "/login": "login.html",
    "/login.html": "login.html",
    "/auth": "auth.html",
    "/auth.html": "auth.html",
    "/cockpit": "cockpit.html",
    "/cockpit.html": "cockpit.html",
    "/user": "user.html",
    "/user.html": "user.html",
    "/neural-graph": "neural_graph.html",
    "/neural-graph.html": "neural_graph.html",
    "/observatory": "observatory.html",
    "/observatory.html": "observatory.html",
    "/intel-wiki": "intel_wiki.html",
    "/intel-wiki.html": "intel_wiki.html",
    "/offline": "offline.html",
    "/offline.html": "offline.html",
    "/index.html": "index.html",
}




for route, filename in FRONTEND_PAGES.items():
    if not route or route == "/":
        continue
    page_path = FRONTEND / filename

    def make_handler(p: Path):
        async def handler():
            if p.exists():
                return FileResponse(p)
            return {"error": f"{p.name} not found"}
        return handler

    app.get(route)(make_handler(page_path))


# Servir assets estáticos do frontend
if FRONTEND.exists():
    app.mount("/static-frontend", StaticFiles(directory=str(FRONTEND)), name="static-frontend")
    # [V110.186] Serve /vendor/* directly so cockpit.html can use <script src="vendor/...">
    vendor_dir = FRONTEND / "vendor"
    if vendor_dir.exists():
        app.mount("/vendor", StaticFiles(directory=str(vendor_dir)), name="vendor")


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "1Crypten Local Dev", "main_app_loaded": MAIN_APP is not None}

@app.get("/sandbox")
@app.get("/sandbox.html")
async def serve_sandbox_local():
    return FileResponse(str(FRONTEND / "sandbox.html"))


# [HERMES DASHBOARD V2] Proxy reverso para o Hermes Dashboard
@app.get("/neural-chat")
@app.get("/neural-chat.html")
async def neural_chat_redirect_local():
    """Redireciona Neural Chat para Hermes Dashboard."""
    return RedirectResponse(url="/hermes")

@app.get("/kanban")
@app.get("/kanban.html")
@app.get("/kanban-hermes")
@app.get("/kanban-hermes.html")
@app.get("/kanban-hermes-enhanced")
@app.get("/kanban-hermes-enhanced.html")
async def kanban_redirect_local():
    """Redireciona Kanban para Hermes Dashboard."""
    return RedirectResponse(url="/hermes")


@app.get("/hermes", response_class=HTMLResponse)
@app.get("/hermes/", response_class=HTMLResponse)
async def serve_hermes_dashboard_local():
    """[HERMES DASHBOARD v2] Proxy da página inicial do Hermes Dashboard."""
    if hermes_dashboard_service and hermes_dashboard_service.is_running:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{hermes_dashboard_service.base_url}/")
                html = resp.text
                if "<head>" in html:
                    html = html.replace("<head>", "<head><base href=\"/hermes/\">", 1)
                return HTMLResponse(content=html, status_code=resp.status_code)
        except Exception as e:
            logger.error(f"[HERMES PROXY] Erro ao buscar dashboard: {e}")

    # Placeholder enquanto o Hermes não estiver pronto
    html = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hermes Dashboard — 1CRYPTEN</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #050508;
            color: #ffffff;
            font-family: 'Inter', sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            gap: 24px;
        }
        .status {
            padding: 16px 32px;
            border-radius: 16px;
            background: rgba(34, 211, 238, 0.05);
            border: 1px solid rgba(34, 211, 238, 0.15);
            text-align: center;
        }
        .status .icon { font-size: 32px; margin-bottom: 12px; }
        .status h2 { font-size: 14px; font-weight: 700; text-transform: uppercase; letter-spacing: 2px; }
        .status p { font-size: 11px; color: #9ca3af; margin-top: 8px; }
        .status .dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #f59e0b;
            margin-right: 6px;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 0.5; transform: scale(1); }
            50% { opacity: 1; transform: scale(1.2); }
        }
        .back-link { color: #22d3ee; font-size: 11px; text-decoration: none; opacity: 0.6; transition: opacity 0.2s; }
        .back-link:hover { opacity: 1; }
    </style>
</head>
<body>
    <div class="status">
        <div class="icon">🪶</div>
        <span class="dot"></span>
        <h2>Hermes Dashboard</h2>
        <p>Inicializando serviço...<br>O Hermes será carregado automaticamente quando estiver pronto.</p>
    </div>
    <a href="/cockpit#/" class="back-link">← Voltar ao Cockpit</a>
    <script>setInterval(function() { window.location.reload(); }, 3000);</script>
</body>
</html>
"""
    return HTMLResponse(content=html)


@app.api_route("/hermes/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
@app.api_route("/hermes/api", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_hermes_api_local(path: str = "", request: Request = None):
    """Proxy reverso para API do Hermes Dashboard."""
    api_path = f"api/{path}" if path else "api"
    return await _proxy_to_hermes_local(api_path, request)


@app.api_route("/hermes/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_hermes_catch_all_local(path: str, request: Request = None):
    """Proxy catch-all: assets, JS, CSS, imagens do Hermes Dashboard."""
    if path.startswith("api/") or path == "api":
        return await proxy_hermes_api_local(path.replace("api/", "", 1) if path != "api" else "", request)
    return await _proxy_to_hermes_local(path, request)


async def _proxy_to_hermes_local(path: str, request: Request = None) -> Response:
    """Proxy genérico: encaminha requisição para o Hermes Dashboard interno."""
    from fastapi.responses import Response as FastAPIResponse
    if not hermes_dashboard_service or not hermes_dashboard_service.is_running:
        return HTMLResponse(
            content='{"error": "Hermes Dashboard não está rodando"}',
            status_code=503,
            media_type="application/json",
        )

    target_url = f"{hermes_dashboard_service.base_url}/{path}" if path else hermes_dashboard_service.base_url

    try:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            req_headers = {}
            if request:
                req_headers = {
                    k: v for k, v in request.headers.items()
                    if k.lower() not in ("host", "content-length", "x-forwarded-for", "x-forwarded-proto", "x-forwarded-host")
                }

            body = await request.body() if request and request.method in ("POST", "PUT", "PATCH") and request.headers.get("content-length") else None
            params = dict(request.query_params) if request else {}

            resp = await client.request(
                method=request.method if request else "GET",
                url=target_url,
                headers=req_headers,
                content=body,
                params=params,
            )

            content_type = resp.headers.get("content-type", "")
            if "text/html" in content_type:
                html = resp.text
                if "<head>" in html:
                    html = html.replace("<head>", "<head><base href=\"/hermes/\">", 1)
                return HTMLResponse(content=html, status_code=resp.status_code)

            return FastAPIResponse(
                content=resp.content,
                status_code=resp.status_code,
                media_type=content_type or "application/octet-stream",
            )
    except Exception as e:
        logger.error(f"[HERMES PROXY] Erro ao fazer proxy para {path}: {e}")
        return HTMLResponse(
            content=f'{{"error": "Erro de conexão com Hermes Dashboard: {str(e)}"}}',
            status_code=502,
            media_type="application/json",
        )


# 4) Mount do app principal por ultimo. O main.py tem catch-all; se vier antes,
# ele captura /health e paginas locais.
if MAIN_APP is not None:
    try:
        app.mount("/", MAIN_APP)
        logger.info("Backend completo (main.py) montado em /")
    except Exception as e:
        logger.warning(f"Falha ao montar main.py: {e}")


@app.on_event("startup")
async def startup():
    logger.info("🚀 Inicializando banco de dados...")
    try:
        init_database()
    except Exception as e:
        logger.error(f"❌ Erro ao inicializar DB: {e}")
        raise

    try:
        await init_trading_database()
    except Exception as e:
        logger.error(f"❌ Erro ao inicializar trading DB: {e}")

    # 🧪 Inicializar o Sandbox Service no local_dev
    try:
        from services.sandbox_service import sandbox_service
        sandbox_service.start()
        logger.info("🟢 Sandbox Service iniciado no ambiente local!")
    except Exception as e:
        logger.error(f"❌ Falha ao iniciar Sandbox Service local: {e}")

    # 🆕 [HERMES DASHBOARD v2] Inicia o Hermes Web Dashboard como serviço paralelo
    if HERMES_DASHBOARD_ENABLED:
        try:
            from backend.hermes_dashboard_service import hermes_dashboard as _hd
            global hermes_dashboard_service
            hermes_dashboard_service = _hd
            _started = await _hd.start()
            if _started:
                logger.info(f"🪶 [HERMES DASHBOARD v2] Hermes Dashboard ONLINE em {_hd.base_url}")
            else:
                logger.warning("⚠️ [HERMES DASHBOARD v2] Falha ao iniciar - continuando sem dashboard.")
        except Exception as hd_err:
            logger.warning(f"⚠️ [HERMES DASHBOARD v2] Erro ao iniciar: {hd_err}")
    else:
        logger.info("⏭️ [HERMES DASHBOARD v2] Desabilitado via HERMES_DASHBOARD_ENABLED=false")

    if not FULL_TRADING_LOOPS:
        logger.info("LOCAL_DEV_FULL_TRADING=0 - OKX/Radar/Captain loops disabled for responsive local frontend/API testing")
        logger.info(f"✅ Frontend: {FRONTEND}")
        logger.info(f"✅ Servidor pronto em http://localhost:{PORT}")
        return

    # Inicializa o OKX WebSocket Public (alimenta btc_price, btc_adx, etc.)
    # Sem isso, o BTC fica com preço 0 no cockpit mesmo com captain/slots ativos.
    try:
        from services.okx_ws_public import okx_ws_public_service
        symbols = [f"{s}.P" for s in (settings.ELITE_40_MATRIX + settings.MASTER_CONTEXT_ASSETS)]
        asyncio.create_task(okx_ws_public_service.start(symbols))
        logger.info(f"🟢 OKX WebSocket Public iniciado ({len(symbols)} símbolos) — BTC price feed ativo")
    except Exception as e:
        logger.error(f"❌ Falha ao iniciar OKX WebSocket Public: {e}")

    # Inicia loops de trading (captain + signal generator).
    # O main.py raiz não dispara isso — fazemos aqui para o cockpit ter dados.
    import asyncio as _asyncio
    if _sig_gen is not None:
        try:
            _asyncio.create_task(_sig_gen._sync_radar_rtdb())
            _asyncio.create_task(_sig_gen.monitor_and_generate())
            _asyncio.create_task(_sig_gen.track_outcomes())
            _asyncio.create_task(_sig_gen.radar_loop())
            logger.info("🟢 signal_generator loops iniciados (radar/track/sync)")
        except Exception as e:
            logger.warning(f"⚠️ Falha iniciando sig_gen loops: {e}")
    if _captain_agent is not None:
        try:
            _asyncio.create_task(_captain_agent.monitor_signals())
            logger.info("🟢 captain_agent.monitor_signals() iniciado — radar→slots ativo")
        except Exception as e:
            logger.warning(f"⚠️ Falha iniciando captain.monitor_signals: {e}")
    # harvester consolidated into FlashAgent
    pass

    logger.info(f"✅ Frontend: {FRONTEND}")
    logger.info(f"✅ Servidor pronto em http://localhost:{PORT}")


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )
