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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
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
    "/neural-chat": "neural-chat.html",
    "/neural-chat.html": "neural-chat.html",
    "/neural-graph": "neural_graph.html",
    "/neural-graph.html": "neural_graph.html",
    "/observatory": "observatory.html",
    "/observatory.html": "observatory.html",
    "/intel-wiki": "intel_wiki.html",
    "/intel-wiki.html": "intel_wiki.html",
    "/kanban": "kanban-hermes-enhanced.html",
    "/kanban.html": "kanban-hermes-enhanced.html",
    "/kanban-hermes": "kanban-hermes.html",
    "/kanban-hermes.html": "kanban-hermes.html",
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
