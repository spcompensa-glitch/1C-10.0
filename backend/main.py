# 1CRYPTEN_SPACE_V4.0 - V110.512 MACRO COMPASS (FORCE DEPLOY)
import sys
import codecs
if sys.platform == "win32":
    try:
        # V89.6: Force UTF-8 encoding for Windows console to prevent UnicodeEncodeError with emojis
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # Fallback for older python versions if reconfigure is missing
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import traceback
import os
import datetime
import asyncio
import logging
import time
from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

class ManualChatRequest(BaseModel):
    text: str

from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
import uvicorn
import ssl
import urllib3
from services.kernel.dispatcher import kernel
from config import settings
from concurrent.futures import ThreadPoolExecutor
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# V15.1 Fix: Custom Middleware to prevent index.html caching
class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            response = await call_next(request)
            path_lower = request.url.path.lower()
            # [V110.520] Anti-cache agressivo para arquivos estáticos HTML, rotas SPA e páginas principais
            if any(path in path_lower for path in ["/", "/index.html", "/observatory", "/cockpit"]) or not any(ext in path_lower for ext in [".js", ".css", ".png", ".jpg", ".svg", ".json", ".ico"]):
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, proxy-revalidate, post-check=0, pre-check=0"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "Fri, 01 Jan 1990 00:00:00 GMT"
                response.headers["Surrogate-Control"] = "no-store"
            return response
        except Exception as e:
            logger.error(f"❌ ASGI Middleware Exception during {request.url.path}: {str(e)}")
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Internal Server Shield: Route Failed", "path": request.url.path}
            )

# V5.2.4.6: Increase Thread Pool size for concurrent network calls
executor = ThreadPoolExecutor(max_workers=32)
asyncio.get_event_loop().set_default_executor(executor)

# V5.2.4.8 Cloud Run Startup Optimization - Infrastructure Protocol
# V90.3: PROTOCOLO COCKPIT - FIM DO CACHE
# V110.40.0: PROTOCOLO COMMAND CENTER PRO - ALMIRANTE ELITE
VERSION = "V110.510"
DEPLOYMENT_ID = "V110.510_STABILIZATION_ULTIMATE"

# Global Directory Configurations - Hardened for Docker/Cloud Run
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Standard: backend/main.py -> ../frontend (moved to root)
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
if not os.path.exists(FRONTEND_DIR):
    # Fallback to old path for backwards compatibility or local tests
    FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "frontend"))
    if not os.path.exists(FRONTEND_DIR):
        # Fallback to current dir if not found (mostly for cloud deployments)
        FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
print(f"[DEBUG] FRONTEND_DIR: {FRONTEND_DIR}")

# Global references
sovereign_service = None
database_service = None # V110.175
websocket_service = None # V110.175
okx_rest_service = None
okx_ws_public_service = None
bankroll_manager = None
redis_service = None
captain_agent = None  # V12.2: Standardized global
globals()['sig_gen'] = None        # V12.2: Standardized global
globals()['oracle_agent'] = None   # V110.32.1: Oracle Global

import logging.handlers
# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(
            os.path.join(BASE_DIR, "backend_v110_173.log"),
            maxBytes=100 * 1024 * 1024,  # 100MB
            backupCount=5,
            encoding='utf-8'
        )
    ]
)
logger = logging.getLogger("1CRYPTEN-MAIN")
logger.info(f"BASE_DIR: {BASE_DIR}")
logger.info(f"FRONTEND_DIR: {FRONTEND_DIR}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # V5.2.0: Stability Staggering
    logger.info(f"Initializing 1CRYPTEN SPACE {VERSION}...")
    
    async def start_services():
        global sovereign_service, database_service, websocket_service, okx_rest_service, okx_ws_public_service, bankroll_manager, redis_service, captain_agent, sig_gen
        
        logger.info("Step 0: Loading services (slow-walk mode)...")
        try:
            import importlib
            # Load services with 1s delay each to keep event loop breathing
            logger.info("Step 0.1: Loading Database Service...")
            database_service = importlib.import_module("services.database_service").database_service
            await database_service.initialize()
            
            # [V110.208] AUTO-MIGRATION SHIELD: Ensures DB schema is always up to date
            try:
                from migrate_db import migrate
                await migrate()
                logger.info("✅ Database Schema check complete.")
            except Exception as migrate_err:
                logger.error(f"⚠️ Auto-migration failed, but continuing: {migrate_err}")

            # [V110.505] Initialize Local SQLite (Klines Cache)
            try:
                from services.backtest import data_extractor
                data_extractor.init_db()
                logger.info("✅ Local Klines DB initialized.")
            except Exception as e:
                logger.warning(f"⚠️ Failed to init Local DB: {e}")

            # [V110.701] Initialize Auth DB tables (users, user_okx_tokens, audit_logs, user_sessions)
            try:
                from database.database_service_secure import init_db as init_auth_db
                init_auth_db()
                logger.info("✅ Auth DB tables initialized.")
            except Exception as e:
                logger.error(f"⚠️ Failed to init Auth DB: {e}")

            logger.info("Step 0.2: Initializing WebSocket Service...")
            websocket_service = importlib.import_module("services.websocket_service").websocket_service
            
            logger.info("Step 0.3: Connecting Redis Service...")
            redis_service = importlib.import_module("services.redis_service").redis_service
            await redis_service.connect()
            await asyncio.sleep(1)

            logger.info("Step 1: Loading Sovereign Service...")
            sovereign_service = importlib.import_module("services.sovereign_service").sovereign_service
            
            logger.info("Step 1.1: Activating Sovereign Mode (Railway)...")
            await sovereign_service.initialize()
            
            logger.info("Step 0.2: Loading OKX REST Service...")
            okx_rest_service = importlib.import_module("services.okx_rest").okx_rest_service
            try:
                # V5.2.4.3: Added 60s timeout for OKX initialization
                await asyncio.wait_for(okx_rest_service.initialize(), timeout=60.0)
            except Exception as e:
                logger.error(f"⚠️ OKX REST Init Error (Continuing anyway): {e}")

            logger.info("Step 0.3: Loading OKX WS Public Service...")
            okx_ws_public_service = importlib.import_module("services.okx_ws_public").okx_ws_public_service
            await asyncio.sleep(0.5) 
            
            # Use bankroll_manager from services.bankroll
            logger.info("Step 0.4: Loading Bankroll Manager...")
            mod = importlib.import_module("services.bankroll")
            bankroll_manager = mod.bankroll_manager
            
            await asyncio.sleep(1)
            logger.info("Step 0: Service modules loaded \u2705")
            
            # [V110.518] DB SANITATION REMOVED TO PRESERVE ACTIVE ORDERS ON DEPLOYS/RESTARTS
            logger.info("🛡️ [V110.519] Startup Order Persistence active. Skipping DB Sanitation.")

            
            logger.info("Step 2: Syncing Bybit Instruments...")
            # [V110.400] ALIGNED BOOTSTRAP: Start with Elite 20 + Master Context
            symbols = [f"{s}.P" for s in (settings.ELITE_40_MATRIX + settings.MASTER_CONTEXT_ASSETS)]
            try:
                # Fetch symbols in background
                async def fetch_and_start_ws():
                    try:
                        # [V110.173] Usar get_elite_focus_pairs para concentrar nos Top 20 Elite
                        s = await asyncio.wait_for(
                            okx_rest_service.get_elite_focus_pairs(),
                            timeout=90
                        )
                        if s: await okx_ws_public_service.start(s)
                    except Exception as e: 
                        logger.error(f"Step 2: Symbol Scan or WS Start Error: {e}")
                        await okx_ws_public_service.start(symbols)
                asyncio.create_task(fetch_and_start_ws())
                # [V110.202] Force slot sync on startup - ensuring persistence during deploys
                logger.info("📡 [V110.202] Syncing slots from persistence layer...")
                await bankroll_manager.update_banca_status()
            except Exception as e:
                logger.warning(f"Step 2: Symbol fetch scheduled (Background): {e}")

            logger.info("Step 3: Activating Agents...")
            try:
                from services.agents.captain import captain_agent as captain_module
                from services.signal_generator import signal_generator as sig_gen_module
                
                # Assign to globals defined at module level
                globals()['captain_agent'] = captain_module
                globals()['sig_gen'] = sig_gen_module
                
                from services.agents.fleet_audit import fleet_audit
                
                from services.agents.macro_analyst import macro_analyst
                from services.agents.whale_tracker import whale_tracker
                from services.agents.onchain_whale_watcher import on_chain_whale_watcher
                from services.agents.sentiment_specialist import sentiment_specialist
                from services.agents.librarian import librarian_agent
                from services.agents.harvester import harvester_agent
                from services.agents.blitz_sniper import blitz_sniper_agent # [V110.137] Blitz Active

                # 🆕 [V4.0 DECENTRALIZATION] Slot Operator Agents (The New Core)
                from services.agents.slot_operator import SlotOperatorAgent
                for sid in range(1, 5):
                    agent = SlotOperatorAgent(sid)
                    await kernel.register_agent(agent)
                    await agent.start()
                    logger.info(f"🚀 [SLOT-{sid}] Agente de Operação ONLINE — Monitoramento isolado ativo.")

                # 🆕 [V110.32.1] Oracle Agent - Data Integrity Guard
                from services.agents.oracle_agent import oracle_agent
                await oracle_agent.initialize()
                await kernel.register_agent(oracle_agent)
                
                # 🆕 [V110.113] Threshold Calibrator - Auto-calibration
                from services.threshold_calibrator import threshold_calibrator
                await threshold_calibrator.initialize()
                if threshold_calibrator.enabled:
                    logger.info("📊 [V110.113] Threshold Calibrator ENABLED - Auto-calibration active")
                else:
                    logger.info("📊 [V110.113] Threshold Calibrator DISABLED - Using static thresholds")

                await kernel.register_agent(captain_agent)
                await kernel.register_agent(fleet_audit)
                await fleet_audit.start() # [V110.656] Inicia Auditoria e Proteção Panic
                
                await kernel.register_agent(macro_analyst)
                await kernel.register_agent(whale_tracker)
                await kernel.register_agent(sentiment_specialist)
                
                await kernel.register_agent(librarian_agent)
                
                await kernel.register_agent(harvester_agent)
                await harvester_agent.start() # [V110.656] Inicia Monitoramento de Moonbags
                
                # 🔥 [V5.4.0] HeatMonitor Agent - Ignition & Flow Intelligence
                try:
                    from services.agents.heat_monitor import heat_monitor_agent
                    await kernel.register_agent(heat_monitor_agent)
                    asyncio.create_task(heat_monitor_agent.run_monitoring_loop())
                    logger.info("🔥 [V5.4.0] HeatMonitor ONLINE — Monitoramento de Ignição ativo.")
                except ImportError as ie:
                    logger.warning(f"⚠️ [V5.4.0] HeatMonitor Agent not found, skipping: {ie}")

                # 🆕 [HERMES] Compliance & Telemetry Agent
                from services.agents.hermes_agent import hermes_agent
                await kernel.register_agent(hermes_agent)
                await hermes_agent.start()
                logger.info("🟢 [HERMES] Compliance & Telemetry Agent ONLINE — Monitorando docs vs código vs runtime.")

                # 🧬 [V5.5.0] Sniper Sieve - O Funil de 200 Ativos
                try:
                    from services.agents.sieve_agent import sieve_agent
                    asyncio.create_task(sieve_agent.run_sieve_loop())
                    logger.info("🧬 [V5.5.0] Sniper Sieve ONLINE — Varredura de 200 pares ativa (20x-50x).")
                except ImportError as ie:
                    logger.warning(f"⚠️ [V5.5.0] Sniper Sieve Agent not found, skipping: {ie}")

                logger.info("Step 3.0: [V110.240] AIOS Kernel — Fleet Active 🚀")

                # [HERMES TELEGRAM] Integração nativa de Telegram
                from services.telegram_service import telegram_service
                telegram_service.start_polling_task()

                # Start Core Loops
                asyncio.create_task(sig_gen._sync_radar_rtdb()) # [V15.7.6] Initial sync
                asyncio.create_task(sig_gen.monitor_and_generate())
                asyncio.create_task(sig_gen.track_outcomes())
                asyncio.create_task(sig_gen.radar_loop())
                asyncio.create_task(captain_agent.monitor_signals())
                # asyncio.create_task(captain_agent.monitor_active_positions_loop()) # [V4.0] Desativado em favor dos SlotOperatorAgents
                asyncio.create_task(librarian_agent.run_loop())
                

                
                # 🆕 [V110.113] Threshold Calibration Loop
                async def threshold_calibration_loop():
                    while True:
                        try:
                            await asyncio.sleep(3600)  # Checa a cada hora
                            if threshold_calibrator.should_calibrate():
                                logger.info("🔧 [V110.113] Running automatic threshold calibration...")
                                result = await threshold_calibrator.run_calibration()
                                if result.get("success"):
                                    logger.info(f"✅ [V110.113] Calibration complete: PF={result['profit_factor']:.2f}")
                                else:
                                    logger.warning(f"⚠️ [V110.113] Calibration skipped: {result.get('reason')}")
                        except Exception as e:
                            logger.error(f"❌ [THRESH-CAL] Error in calibration loop: {e}")
                
                asyncio.create_task(threshold_calibration_loop())
                
                # [V27.2] Trade Analyst - Performance Intelligence (KEPT)
                from services.agents.trade_analyst import trade_analyst
                await kernel.register_agent(trade_analyst)
                asyncio.create_task(trade_analyst.start_loop())
                
                # 3.1: V5.2.3: Initial Sync - Ensure Vault and Banca are aligned with history
                async def initial_sync():
                    try:
                        from services.vault_service import vault_service
                        logger.info("Step 3.1: Running initial Vault & Banca Synchronization...")
                        await vault_service.sync_vault_with_history()
                        await bankroll_manager.update_banca_status()
                        
                        # [V110.25.1] Legacy startup cleanup removed to preserve slot persistence.
                        # BankrollManager now handles safe ghost-busting with 10m grace period.
                        logger.info("Step 3.1: Initial Sync COMPLETE ✅")

                    except Exception as e:
                        logger.error(f"Step 3.1: Initial Sync ERROR: {e}")
                
                asyncio.create_task(initial_sync())
                
                # 4. [V4.0] DECENTRALIZED EXECUTION: Removed centralized loops.
                # Every SlotOperatorAgent handles its own execution and monitoring.
                logger.info(f"Step 4: [V4.0] Decentralized Execution Engine ACTIVE (Modo: {okx_rest_service.execution_mode})")

                # Sovereign Pulse Loop (WebSocket only)
                async def pulse_loop():
                    while True:
                        # [V110.175] Native Railway Heartbeat (Implemented in update_pulse_drag)
                        await asyncio.sleep(60)
                asyncio.create_task(pulse_loop())

                async def market_context_loop():
                    while True:
                        try:
                            if okx_ws_public_service:
                                # [V16.3.1] Read consolidated cached metrics from OKX WS Public to prevent duplicate REST calls.
                                pass
                                
                                # 🆕 [V110.175] FEED THE ORACLE: Alimenta o oráculo com dados reais do WebSocket
                                if oracle_agent:
                                    await oracle_agent.update_market_data("okx_ws_public", {
                                        "btc_price": okx_ws_public_service.btc_price,
                                        "btc_adx": okx_ws_public_service.btc_adx,
                                        "btc_variation_1h": okx_ws_public_service.btc_variation_1h,
                                        "btc_variation_24h": okx_ws_public_service.btc_variation_24h,
                                        "btc_variation_15m": okx_ws_public_service.btc_variation_15m
                                    })

                                # Sync to RTDB for immediate UI update
                                if sig_gen:
                                    # 🆕 [V110.32.1] Fetch Validated Context from Oracle
                                    oracle_ctx = {}
                                    if oracle_agent:
                                        oracle_ctx = oracle_agent.get_validated_context()
                                        # Use Oracle ADX if available to ensure "Amnesia Guard" consistency in UI
                                        current_adx = oracle_ctx.get("btc_adx", getattr(okx_ws_public_service, 'btc_adx', 20.0))
                                    else:
                                        current_adx = getattr(okx_ws_public_service, 'btc_adx', 20.0)
                                    
                                    # Fallback final para evitar "..."
                                    if not current_adx or current_adx < 0.1:
                                        current_adx = 20.0

                                    # 🆕 [V110.33] Fetch BTC Dominance from Macro Analyst
                                    current_dominance = 0.0
                                    try:
                                        from services.agents.macro_analyst import macro_analyst
                                        current_dominance = await macro_analyst._get_btc_dominance()
                                        # Sync dominance to Oracle for LKG persistence
                                        if oracle_agent and current_dominance > 0:
                                            await oracle_agent.update_market_data("macro_analyst", {"dominance": current_dominance})
                                    except Exception as dom_err:
                                        logger.error(f"Error fetching dominance: {dom_err}")

                                    btc_var_15m = getattr(okx_ws_public_service, 'btc_variation_15m', 0.0)
                                    btc_var_1h = okx_ws_public_service.btc_variation_1h
                                    captain_direction = getattr(captain_agent, 'last_decision', "LATERAL")

                                    # [V5.5.0] Calculate Global Heat Index (Average velocity of monitored symbols)
                                    try:
                                        velocities = list(okx_ws_public_service.velocity_cache.values())
                                        global_heat = sum(velocities) / len(velocities) if velocities else 0.0
                                    except:
                                        global_heat = 0.0

                                    await sovereign_service.update_pulse_drag(
                                        btc_drag_mode=getattr(sig_gen, 'btc_drag_mode', False),
                                        btc_cvd=okx_ws_public_service.get_cvd_score("BTCUSDT"),
                                        exhaustion=getattr(sig_gen, 'exhaustion_level', 0.0),
                                        btc_price=okx_ws_public_service.btc_price,
                                        btc_var_1h=btc_var_1h,
                                        btc_adx=current_adx,
                                        decorrelation_avg=getattr(okx_ws_public_service, 'decorrelation_avg', 0.0),
                                        btc_var_24h=okx_ws_public_service.btc_variation_24h,
                                        btc_dominance=current_dominance,
                                        btc_var_15m=btc_var_15m,
                                        btc_var_4h=getattr(okx_ws_public_service, 'btc_variation_4h', 0.0),
                                        btc_direction=None, # Centralized logic in SovereignService
                                        oracle_context={**oracle_ctx, "heat_index": global_heat}
                                    )

                                    # [V110.506] Harmonize Direction SSOT
                                    btc_direction_ssot = sovereign_service._pulse_cache.get("btc_direction", "LATERAL")
                                    
                                    payload = {
                                        "btc_price": okx_ws_public_service.btc_price,
                                        "btc_variation_1h": btc_var_1h,
                                        "btc_adx": current_adx,
                                        "btc_direction": btc_direction_ssot, # SSOT consistency
                                        "btc_dominance": current_dominance,
                                        "btc_var_15m": btc_var_15m,
                                        "timestamp": time.time()
                                    }
                                    # 🆕 [V110.181] BROADCAST SYSTEM STATE: Sincronização nativa WebSocket
                                    from services.websocket_service import websocket_service
                                    await websocket_service.emit_system_state(payload)

                        except Exception as e:
                            logger.error(f"Error in market_context_loop: {e}")
                        await asyncio.sleep(10) # 🆕 Optimized for V110.32.1 (from 300s)
                asyncio.create_task(market_context_loop())

                async def bankroll_loop():
                    while True:
                        try: await bankroll_manager.update_banca_status()
                        except: pass
                        await asyncio.sleep(60)
                asyncio.create_task(bankroll_loop())

                # [V110.999] LIVE SLOTS BROADCAST LOOP — Garante que Cockpit veja ordens do Postgres
                async def slots_broadcast_loop():
                    """Publica slots ativos via WS a cada 5s para garantir sincronismo do Cockpit."""
                    while True:
                        try:
                            from services.database_service import database_service as _ds
                            from services.websocket_service import websocket_service as _ws
                            
                            db_slots = await _ds.get_active_slots()
                            
                            # Convert SQLAlchemy Slot objects to dict lists for serialization
                            slots = []
                            for s in db_slots:
                                if not isinstance(s, dict):
                                    # Fallback caso seja um objeto ORM
                                    s = {c.name: getattr(s, c.name) for c in s.__table__.columns}
                                
                                slots.append({
                                    "id": s.get("id"),
                                    "symbol": s.get("symbol"),
                                    "side": s.get("side"),
                                    "qty": s.get("qty"),
                                    "entry_price": s.get("entry_price"),
                                    "entry_margin": s.get("entry_margin"),
                                    "current_stop": s.get("current_stop"),
                                    "initial_stop": s.get("initial_stop"),
                                    "order_id": s.get("order_id"),
                                    "target_price": s.get("target_price"),
                                    "leverage": s.get("leverage"),
                                    "slot_type": s.get("slot_type") or "BLITZ",
                                    "status_risco": s.get("status_risco"),
                                    "pnl_percent": s.get("pnl_percent"),
                                    "strategy": s.get("strategy"),
                                    "strategy_label": s.get("strategy_label"),
                                    "genesis_id": s.get("genesis_id"),
                                    "opened_at": s.get("opened_at").isoformat() if s.get("opened_at") and hasattr(s.get("opened_at"), "isoformat") else (s.get("opened_at") or 0),
                                    "updated_at": s.get("updated_at").isoformat() if s.get("updated_at") and hasattr(s.get("updated_at"), "isoformat") else (s.get("updated_at") or 0),
                                    "pensamento": s.get("pensamento"),
                                    "liq_price": s.get("liq_price"),
                                    "structural_target": s.get("structural_target"),
                                    "target_extended": s.get("target_extended"),
                                    "is_ranging_sniper": s.get("is_ranging_sniper"),
                                    "v42_tag": s.get("v42_tag"),
                                    "move_room_pct": s.get("move_room_pct"),
                                    "pattern": s.get("pattern"),
                                    "unified_confidence": s.get("unified_confidence"),
                                    "fleet_intel": s.get("fleet_intel"),
                                    "is_reverse_sniper": s.get("is_reverse_sniper"),
                                    "market_regime": s.get("market_regime"),
                                    "rescue_activated": s.get("rescue_activated"),
                                    "rescue_resolved": s.get("rescue_resolved")
                                })
                            
                            if _ws.active_connections:
                                await _ws.emit_slots(slots)
                        except Exception as e:
                            logger.warning(f"[SLOTS-BROADCAST] Erro: {e}")
                        await asyncio.sleep(5)
                asyncio.create_task(slots_broadcast_loop())
                logger.info("📡 [V110.999] Live Slots Broadcast Loop ATIVO.")

                # 5. [V110.510] MCP Bridge for AIOS / n8n Integration
                try:
                    from services.mcp_bridge import mcp
                    # Tenta extrair a aplicação ASGI do FastMCP para montar nativamente
                    asgi_app = None
                    if hasattr(mcp, "get_asgi_app"):
                        asgi_app = mcp.get_asgi_app()
                    elif hasattr(mcp, "_app"):
                        asgi_app = mcp._app
                    else:
                        asgi_app = mcp  # Assume que é chamável (ASGI)
                    
                    app.mount("/mcp", asgi_app)
                    logger.info("Step 5: MCP Bridge Integrado nativamente no FastAPI em /mcp ✅")
                except Exception as e:
                    logger.warning(f"Step 5: MCP Bridge Mount Error: {e}")

            except Exception as e:
                logger.error(f"Step 3: Agent sync error: {e}")
                
            # [SaaS V5.5.0] Inicialização de Serviços da OKX e Hermes Broker
            try:
                logger.info("🛰️ [SaaS] Inicializando novos serviços OKX e Hermes Broker...")
                from services.hermes_broker import hermes_broker_service
                from services.portfolio_guardian import portfolio_guardian
                from services.okx_ws import okx_ws_service
                
                # 1. Inicia gRPC e MQTT do Hermes
                await hermes_broker_service.start_mqtt()
                await hermes_broker_service.start_grpc()
                
                # 2. Ativa escuta do Portfolio Guardian
                portfolio_guardian.start()
                
                # 3. Conecta WebSocket privado da OKX Master
                await okx_ws_service.start()

                # 4. Inicializa o Sentinel Auditor (Caixa-Preta da 1CrypTen)
                from services.sentinel_auditor import sentinel_auditor
                await sentinel_auditor.start()
                logger.info("🛡️ [SaaS] Sentinel Auditor ONLINE e reconciliando!")

                logger.info("✅ [SaaS] OKX e Hermes Broker inicializados com SUCESSO!")
            except Exception as saas_init_err:
                logger.error(f"❌ [SaaS] Falha ao iniciar serviços OKX/Hermes: {saas_init_err}", exc_info=True)
                
            logger.info("✅ All background services started successfully!")
        except Exception as e:
            logger.error(f"FATAL Startup Error: {e}", exc_info=True)
            
    # Start worker
    asyncio.create_task(start_services())
    
    yield
    
    # 🛑 [V110.176] CLEAN SHUTDOWN PROTOCOL
    logger.info("🛑 [V110.176] 10D Sniper Intelligence Lab - SHUTTING DOWN...")
    try:
        if okx_ws_public_service:
            okx_ws_public_service.stop()
        if redis_service:
            # redis_service has an async client but connect() doesn't expose a clean close yet, 
            # let's try a best effort if it has aclose
            if hasattr(redis_service.client, "aclose"):
                await redis_service.client.aclose()
                
        # [SaaS V5.5.0] Desligamento seguro de novos serviços
        try:
            from services.okx_ws import okx_ws_service
            from services.hermes_broker import hermes_broker_service
            
            logger.info("🛑 [SaaS] Desligando serviços OKX WebSocket e Hermes Broker...")
            await okx_ws_service.stop()
            await hermes_broker_service.stop_mqtt()
            await hermes_broker_service.stop_grpc()
            logger.info("✅ [SaaS] Serviços desativados com sucesso.")
        except Exception as saas_err:
            logger.error(f"Erro ao desligar serviços SaaS: {saas_err}")
            
    except Exception as shutdown_err:
        logger.error(f"Error during shutdown: {shutdown_err}")
    
    logger.info("🔚 End of Lifespan. Goodbye.")

app = FastAPI(
    title=f"1CRYPTEN SPACE {VERSION} API",
    version=VERSION,
    lifespan=lifespan
)

# Configure CORS - V15.1.5 Security Hardening
# In production, restrict this. For local dev/file open, * is risky but often used.
# Let's target the exact port 8085 as default.
ALLOWED_ORIGINS = [
    "http://localhost:8085",
    "http://127.0.0.1:8085",
    "http://localhost:5173",
    "https://1crypten.space",
    "https://www.1crypten.space",
    "https://1crypten-hermes-agent-production.up.railway.app",
]

# Process and append custom backend CORS origins
if settings.BACKEND_CORS_ORIGINS:
    try:
        custom_origins = [orig.strip() for orig in settings.BACKEND_CORS_ORIGINS.split(",") if orig.strip()]
        for origin in custom_origins:
            if origin not in ALLOWED_ORIGINS:
                ALLOWED_ORIGINS.append(origin)
        logger.info(f"📡 Dynamic CORS Origins loaded: {custom_origins}")
    except Exception as e:
        logger.error(f"❌ Error parsing BACKEND_CORS_ORIGINS: {e}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if not settings.DEBUG else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(NoCacheMiddleware)

# [V1.0] Servir provas visuais do Agente Visão
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
VISION_PROOFS_DIR = os.path.join(ASSETS_DIR, "vision_proofs")

if not os.path.exists(VISION_PROOFS_DIR):
    os.makedirs(VISION_PROOFS_DIR, exist_ok=True)
    logger.info(f"📁 Created vision_proofs directory: {VISION_PROOFS_DIR}")
else:
    logger.info(f"✅ vision_proofs directory exists: {VISION_PROOFS_DIR}")

# [V110.506] Robust Static Mounting
app.mount("/assets", StaticFiles(directory=ASSETS_DIR, html=False), name="assets")

if settings.SERVE_STATIC_FRONTEND:
    # [V5.0] Intel Map (Graphify)
    GRAPHIFY_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "graphify-out"))
    OBSIDIAN_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".obsidian_intel"))

    if os.path.exists(GRAPHIFY_DIR):
        app.mount("/intel/map", StaticFiles(directory=GRAPHIFY_DIR, html=True), name="intel_map")

    if os.path.exists(OBSIDIAN_DIR):
        app.mount("/intel/wiki_raw", StaticFiles(directory=OBSIDIAN_DIR), name="wiki_raw")

    @app.get("/intel/wiki")
    async def intelligence_wiki():
        return FileResponse(os.path.join(FRONTEND_DIR, "intel_wiki.html"))

    @app.get("/intel/neural")
    async def intelligence_neural():
        """Serves the True Force-Directed Neural Map."""
        return FileResponse(os.path.join(FRONTEND_DIR, "neural_graph.html"))

    @app.get("/intel/map/graph.json")
    async def serve_graph_json():
        """Serves the knowledge graph JSON representing the system architecture."""
        graph_path = os.path.join(GRAPHIFY_DIR, "graph.json")
        if os.path.exists(graph_path):
            return FileResponse(graph_path, media_type="application/json")
        # Fallback: return empty graph
        from fastapi.responses import JSONResponse
        return JSONResponse({"nodes": [], "links": []})

    @app.get("/neural-chat")
    async def neural_chat():
        """Serves the Neural Chat Fusion — 60% Neural Graph + 40% Chat Hermes."""
        return FileResponse(os.path.join(FRONTEND_DIR, "neural-chat.html"))

    @app.get("/user")
    async def serve_user_dashboard():
        """Serves the premium UBI dashboard for retail subscribers."""
        return FileResponse(os.path.join(FRONTEND_DIR, "user.html"))






# =================================================================
# ROUTES & MODULARIZATION (V110.25.0)
# =================================================================
from routes import trading, system, dashboard, market, aios, chat, vault, backtest_routes, auth, sentinel

# Include Modulated Routers
app.include_router(auth.router, prefix="/api/auth")
app.include_router(trading.router)
app.include_router(system.router)
app.include_router(dashboard.router)
app.include_router(market.router)
app.include_router(aios.router)
app.include_router(chat.router)
app.include_router(vault.router)
app.include_router(backtest_routes.router)
app.include_router(sentinel.router)

# =================================================================
# WEBSOCKET ENDPOINT (V110.175)
# =================================================================
from services.websocket_service import websocket_service
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws/cockpit")
async def cockpit_websocket_endpoint(websocket: WebSocket):
    await websocket_service.connect(websocket)
    try:
        while True:
            # Mantém a conexão viva e aguarda mensagens
            data = await websocket.receive_text()
            
            # Se receber um ping do front, respondemos pong
            if data == "ping":
                await websocket.send_text("pong")
                continue
                
            # Processar mensagem estruturada se for JSON
            try:
                import json
                import time
                message_data = json.loads(data)
                message_type = message_data.get("type")
                message_content = message_data.get("message", "")
                
                if message_type == "chat":
                    try:
                        from services.agents.hermes_agent import hermes_agent
                        result = await hermes_agent.handle_chat_query(message_content)
                        reply = result.get("response", "🌐 Sinal neural instável... Tente novamente, Almirante.")
                    except Exception as e:
                        logger.error(f"Erro no hermes_agent do backend WebSocket: {e}")
                        try:
                            from services.agents.ai_service import ai_service
                            from routes.chat import HERMES_FALLBACK_PROMPT
                            reply = await ai_service.generate_content(
                                prompt=message_content,
                                system_instruction=HERMES_FALLBACK_PROMPT
                            )
                            reply = reply or "🌐 Sinal neural instável."
                        except Exception as e2:
                            logger.error(f"Erro no fallback do AIService no backend WebSocket: {e2}")
                            reply = "🪶 Hermes: Erro de sinal neural interno."
                    
                    response = {
                        "type": "hermes_response",
                        "message": reply,
                        "timestamp": time.time()
                    }
                    await websocket.send_text(json.dumps(response))
            except json.JSONDecodeError:
                pass
            except Exception as e:
                logger.error(f"Erro ao processar mensagem do WebSocket: {e}")
                
    except WebSocketDisconnect:
        websocket_service.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket Error: {e}")
        websocket_service.disconnect(websocket)

# Special Root Routes (Must stay in main for precedence or special handling)
if settings.SERVE_STATIC_FRONTEND:
    @app.get("/observatory", response_class=HTMLResponse)
    @app.get("/observatory/{symbol}", response_class=HTMLResponse)
    async def observatory_page(symbol: str = "AVAXUSDT"):
        # Check local path then app path
        path = os.path.join(FRONTEND_DIR, "observatory.html")
        if not os.path.exists(path):
            path = "/app/frontend/observatory.html"
        
        with open(path, "r", encoding="utf-8") as f:
            html_content = f.read()
            # Injeta Cache-Bust dinâmico na chamada dos scripts se necessário
            # Adiciona um header de timestamp de deploy para invalidar em proxies CDN
            from fastapi.responses import HTMLResponse
            return HTMLResponse(
                content=html_content,
                headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0, proxy-revalidate",
                    "ETag": f"1c-obs-{time.time()}"
                }
            )

    @app.get("/kanban", response_class=HTMLResponse)
    async def serve_kanban_page():
        path = os.path.join(FRONTEND_DIR, "kanban-hermes-enhanced.html")
        if not os.path.exists(path):
            path = os.path.join(FRONTEND_DIR, "kanban-hermes.html")
        
        with open(path, "r", encoding="utf-8") as f:
            html_content = f.read()
            return HTMLResponse(
                content=html_content,
                headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0, proxy-revalidate",
                    "ETag": f"1c-kanban-{time.time()}"
                }
            )

    @app.get("/")
    async def serve_index():
        path = os.path.join(FRONTEND_DIR, "cockpit.html")
        with open(path, "r", encoding="utf-8") as f:
            html_content = f.read()
            return HTMLResponse(
                content=html_content,
                headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0, proxy-revalidate",
                    "ETag": f"1c-cockpit-{time.time()}"
                }
            )

    @app.get("/n8n")
    @app.get("/n8n/")
    async def n8n_redirect():
        return RedirectResponse(url="https://n8n-production-8e2d4.up.railway.app")

    @app.get("/cockpit")
    @app.get("/cockpit.html")
    async def cockpit_redirect():
        return RedirectResponse(url="/")

    @app.get("/observatory.html")
    async def serve_observatory_legacy():
        """[V5.0] Sala de Observação Visual — 40 Elite Pairs"""
        path = os.path.join(FRONTEND_DIR, "observatory.html")
        with open(path, "r", encoding="utf-8") as f:
            html_content = f.read()
            return HTMLResponse(
                content=html_content,
                headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0, proxy-revalidate",
                    "ETag": f"1c-obs-leg-{time.time()}"
                }
            )

    @app.get("/{full_path:path}")
    async def catch_all(full_path: str):
        # Search for physical file first (crucial for manifest.json, sw.js, etc.)
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
            
        # SECURITY: Never catch-all API routes that DON'T correspond to files
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        
        # SPA Fallback
        return FileResponse(os.path.join(FRONTEND_DIR, "cockpit.html"))
else:
    @app.get("/")
    async def serve_headless_root():
        return {
            "status": "online",
            "mode": "headless",
            "version": VERSION,
            "deployment_id": DEPLOYMENT_ID,
            "message": "1Crypten Space V4.0 (10D Sniper Factory) API is running in Headless Mode."
        }

    @app.get("/{full_path:path}")
    async def catch_all(full_path: str):
        # SECURITY: Never catch-all API routes that DON'T correspond to files
        raise HTTPException(status_code=404, detail="Not found (API Headless Mode)")

if __name__ == "__main__":
    target_port = settings.PORT
    target_host = settings.HOST
    logger.info(f"Server starting on http://{target_host}:{target_port}")
    uvicorn.run(app, host=target_host, port=target_port, reload=False)

logger.info("🔚 End of main.py file reached")

