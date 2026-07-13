from fastapi import APIRouter, Depends, Header, HTTPException, Request
import logging
import datetime
import os
from config import settings

from services.auth_service import get_current_user, User

router = APIRouter(prefix="/api", tags=["System"])
logger = logging.getLogger("1CRYPTEN-SYSTEM")

def get_services():
    from services.firebase_service import firebase_service
    from services.okx_rest import okx_rest_service
    from services.vault_service import vault_service
    from services.bankroll import bankroll_manager
    from services.execution_protocol import execution_protocol
    return firebase_service, okx_rest_service, vault_service, bankroll_manager, execution_protocol

async def verify_api_key(x_api_key: str = Header(None)):
    if settings.DEBUG:
        return True
    if x_api_key != settings.ADMIN_API_KEY:
        logger.warning(f"🔒 Security Alert: Unauthorized access attempt in System Route")
        raise HTTPException(status_code=403, detail="Acesso Proibido: Chave de API Inválida")
    return True

@router.get("/test")
async def test_connectivity():
    return {"status": "ok", "timestamp": datetime.datetime.now().isoformat()}

@router.get("/debug/test")
async def debug_test():
    from main import VERSION
    return {"status": "ok", "message": f"{VERSION} Almirante Verified"}

@router.get("/health")
async def health_check():
    firebase_service, okx_rest_service, _, _, _ = get_services()
    from main import VERSION, DEPLOYMENT_ID, FRONTEND_DIR
    frontend_files = []
    if os.path.exists(FRONTEND_DIR):
        try: frontend_files = os.listdir(FRONTEND_DIR)
        except: frontend_files = ["Permission Error"]
    okx_conn = False
    balance = 0.0
    if okx_rest_service:
        try:
            okx_conn = True
            balance = okx_rest_service.last_balance
        except: pass
    return {
        "status": "online", "version": VERSION, "deployment_id": DEPLOYMENT_ID,
        "okx_connected": okx_conn, "balance": balance,
        "frontend_path": FRONTEND_DIR, "frontend_found": os.path.exists(FRONTEND_DIR),
        "frontend_files": frontend_files,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

@router.get("/banca/data")
async def get_banca_data(request: Request):
    firebase_service, okx_rest_service, _, _, _ = get_services()
    username = "admin"
    try:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            from services.auth_service import jwt_manager
            payload = jwt_manager.verify_token(token, "access")
            if payload and payload.get("sub"):
                username = payload.get("sub")
    except Exception:
        pass

    try:
        status = await firebase_service.get_banca_status(username=username)
        if not status or status.get("saldo_total", 0) == 0:
            status = {"saldo_total": 100.0, "risco_real_percent": 0.0, "slots_disponiveis": 4, "status": "DEFAULT_PAPER"}
        
        # Consulta direta em tempo real do saldo real OKX
        from config import settings
        api_key = settings.OKX_API_KEY_MASTER or settings.OKX_API_KEY
        secret_key = settings.OKX_API_SECRET_MASTER or settings.OKX_API_SECRET
        passphrase = settings.OKX_PASSPHRASE_MASTER or getattr(settings, "OKX_PASSPHRASE", None)
        
        if api_key and secret_key and passphrase:
            try:
                import httpx
                from services.okx_service import okx_service
                request_path = "/api/v5/account/balance"
                url = "https://www.okx.com" + request_path
                headers = okx_service._get_headers(
                    "GET", request_path,
                    custom_key=api_key,
                    custom_secret=secret_key,
                    custom_passphrase=passphrase
                )
                async with httpx.AsyncClient(timeout=4.0) as client:
                    response = await client.get(url, headers=headers)
                    if response.status_code == 200:
                        res_data = response.json()
                        if res_data.get("code") == "0" and res_data.get("data"):
                            real_val = float(res_data["data"][0].get("totalEq", 0.0))
                            if real_val > 0:
                                status["saldo_real_okx"] = real_val
            except Exception as e:
                logger.error(f"Erro ao obter saldo real em tempo real para a API: {e}")
        
        # [V127] Se estiver em modo PAPER, espelha a Banca Simulada Consolidada do Sandbox no Cockpit
        if settings.OKX_EXECUTION_MODE == "PAPER":
            try:
                from services.database_service import database_service
                sim_balance = await database_service.get_sandbox_unified_balance()
            except Exception:
                sim_balance = float(getattr(settings, "OKX_SIMULATED_BALANCE", 10000.0))
            status["saldo_total"] = sim_balance
            status["configured_balance"] = sim_balance
            # Removemos saldo_real_okx para que a UI flutue a banca base com o PnL aberto local
            status.pop("saldo_real_okx", None)
                
        return status
    except Exception as e:
        logger.error(f"Error fetching banca: {e}")
    return {"saldo_total": 0.0, "risco_real_percent": 0.0, "slots_disponiveis": 4, "status": "ERROR"}

@router.post("/banca/update", dependencies=[Depends(verify_api_key)])
async def update_banca(payload: dict):
    return {"status": "blocked", "message": "Banca fixa em $100 (modo PAPER). Atualização automática via PnL."}

@router.get("/banca-history")
async def get_banca_history(limit: int = 50):
    firebase_service, _, _, _, _ = get_services()
    try: return await firebase_service.get_banca_history(limit=limit)
    except Exception as e:
        logger.error(f"Error in banca history endpoint: {e}")
        return []

@router.get("/bankroll/guardian-report")
async def get_bankroll_guardian_report():
    """Relatorio em PT-BR do Guardiao da Banca."""
    try:
        from services.agents.bankroll_guardian import bankroll_guardian
        return await bankroll_guardian.evaluate_bank_health()
    except Exception as e:
        logger.error(f"Error in bankroll guardian report: {e}")
        return {
            "agent": "Guardiao da Banca",
            "status": "ERRO",
            "mode": "INDISPONIVEL",
            "health_score": 0,
            "message_ptbr": f"Guardiao da Banca indisponivel: {e}",
            "reasons": [str(e)]
        }

@router.get("/stats")
async def get_stats(current_user: User = Depends(get_current_user)):
    firebase_service, _, _, _, _ = get_services()
    try: 
        return await firebase_service.get_banca_status(username=current_user.username)
    except Exception as e:
        logger.error(f"Error in stats endpoint for {current_user.username}: {e}")
        return {"saldo_total": 0.0, "risco_real_percent": 0.0, "win_rate": 0.0}

@router.post("/system/re-sync", dependencies=[Depends(verify_api_key)])
async def trigger_re_sync():
    _, _, vault_service, bankroll_manager, _ = get_services()
    try:
        logger.info("Manual Re-Sync Triggered via API")
        await vault_service.sync_vault_with_history()
        await bankroll_manager.update_banca_status()
        return {"status": "success", "message": "Manual synchronization complete. RTDB updated."}
    except Exception as e:
        logger.error(f"Re-sync error: {e}")
        return {"status": "error", "message": str(e)}

@router.post("/system/nuclear-reset", dependencies=[Depends(verify_api_key)])
async def nuclear_reset():
    """
    [V111.RESET] Limpa IMEDIATAMENTE o estado Paper em memória (paper_positions, paper_moonbags)
    e persiste o estado zerado no Firestore, Postgres e Redis.
    Resolve posições fantasma (ZECUSDT, OPNUSDT etc.) que bloqueiam novos slots.
    """
    firebase_service, okx_rest_service, _, bankroll_manager, _ = get_services()
    from services.database_service import database_service
    from services.redis_service import redis_service
    
    report = []
    try:
        # 1. Limpar memória RAM do OKX REST Service
        old_pos_count = len(okx_rest_service.paper_positions)
        old_moon_count = len(okx_rest_service.paper_moonbags)
        okx_rest_service.paper_positions = []
        okx_rest_service.paper_moonbags = []
        okx_rest_service.paper_balance = settings.OKX_SIMULATED_BALANCE
        report.append(f"✅ RAM Limpa: {old_pos_count} posições e {old_moon_count} moonbags removidas da memória.")
        
        # 2. Limpar pending_slots do BankrollManager
        old_pending = len(bankroll_manager.pending_slots)
        old_recent = len(getattr(bankroll_manager, "recent_openings", {}))
        bankroll_manager.pending_slots.clear()
        if hasattr(bankroll_manager, "recent_openings"):
            bankroll_manager.recent_openings.clear()
        report.append(f"✅ Pending slots limpos: {old_pending} locks removidos.")
        report.append(f"✅ Recent openings limpos: {old_recent} cooldowns removidos.")

        # 2.1. Limpar travas voláteis do Capitão
        try:
            from services.agents.captain import captain_agent
            captain_snapshot = captain_agent.reset_runtime_state()
            report.append(f"✅ Capitão destravado: {captain_snapshot}")
        except Exception as e:
            report.append(f"⚠️ Capitão runtime reset parcial: {e}")
        
        # 2.2. Limpar memoria do Guardiao da Banca
        try:
            from services.agents.bankroll_guardian import bankroll_guardian
            guardian_snapshot = bankroll_guardian.reset_runtime_state()
            report.append(f"Guardiao da Banca resetado: {guardian_snapshot}")
        except Exception as e:
            report.append(f"Guardiao da Banca reset parcial: {e}")

        # 3. Persistir estado zerado no Firestore (via firebase_service.update_paper_state)
        try:
            clean_state = {
                "positions": [],
                "moonbags": [],
                "balance": settings.OKX_SIMULATED_BALANCE,
                "history": []
            }
            await firebase_service.update_paper_state(clean_state)
            report.append("✅ Firestore paper_engine zerado.")
        except Exception as e:
            report.append(f"⚠️ Firestore não disponível (SDK disabled): {e}")
        
        # 4. Limpar Postgres slots e moonbags
        try:
            await database_service.reset_system_data()
            report.append("✅ Postgres slots/moonbags/histórico zerado.")
        except Exception as e:
            report.append(f"⚠️ Postgres reset parcial: {e}")
            
        # 5. Limpar Firebase RTDB (Interface Antiga/Híbrida)
        try:
            if firebase_service.rtdb:
                firebase_service.rtdb.child("active_slots").delete()
                firebase_service.rtdb.child("vault_history").delete()
                firebase_service.rtdb.child("banca").update({
                    "configured_balance": 100.0,
                    "pnl_realized": 0.0
                })
                report.append("✅ Firebase RTDB (Slots/Vault/Banca) zerado.")
        except Exception as e:
            report.append(f"⚠️ Firebase RTDB reset parcial: {e}")
        
        # 6. [V111] Limpar Redis (cache de tickers, CVD, OI, LS ratios, locks)
        try:
            redis_client = redis_service.client
            if hasattr(redis_client, 'flushdb') and callable(redis_client.flushdb):
                await redis_client.flushdb()
                report.append("✅ Redis FLUSHDB executado — todos os caches limpos.")
            else:
                # MockRedis fallback — limpar caches manuais
                from services.redis_service import _LOCAL_CACHE, _LOCAL_EXPIRY
                _LOCAL_CACHE.clear()
                _LOCAL_EXPIRY.clear()
                report.append("✅ Redis (Mock/In-Memory) caches limpos.")
        except Exception as e:
            report.append(f"⚠️ Redis reset parcial: {e}")
        
        logger.warning("🚨 [NUCLEAR-RESET] Estado paper zerado por admin. Todas as posições fantasma eliminadas.")
        return {
            "status": "SUCCESS",
            "message": "Sistema zerado com sucesso. Pronto para novas ordens.",
            "report": report,
            "paper_balance": okx_rest_service.paper_balance,
            "paper_positions": 0,
            "paper_moonbags": 0
        }
    except Exception as e:
        logger.error(f"❌ [NUCLEAR-RESET] Falha: {e}")
        return {"status": "ERROR", "message": str(e), "report": report}

@router.post("/system/sniper-toggle", dependencies=[Depends(verify_api_key)])
async def toggle_sniper(payload: dict):
    _, _, vault_service, _, _ = get_services()
    enabled = payload.get("active", True)
    success = await vault_service.set_sniper_mode(enabled)
    return {"status": "success" if success else "error"}

@router.get("/system/captain-runtime", dependencies=[Depends(verify_api_key)])
async def captain_runtime_status():
    """Diagnóstico rápido das travas em memória que podem deixar slots vazios."""
    _, okx_rest_service, _, bankroll_manager, _ = get_services()
    from services.agents.captain import captain_agent
    return {
        "is_running": captain_agent.is_running,
        "active_tocaias_count": len(captain_agent.active_tocaias),
        "active_tocaias": list(captain_agent.active_tocaias)[:20],
        "processing_lock_count": len(captain_agent.processing_lock),
        "processing_lock": list(captain_agent.processing_lock)[:20],
        "cooldown_registry_count": len(captain_agent.cooldown_registry),
        "daily_symbol_trades_count": len(captain_agent.daily_symbol_trades),
        "daily_symbol_trades": captain_agent.daily_symbol_trades,
        "pending_slots_count": len(bankroll_manager.pending_slots),
        "recent_openings_count": len(getattr(bankroll_manager, "recent_openings", {})),
        "paper_positions": len(okx_rest_service.paper_positions),
        "paper_moonbags": len(okx_rest_service.paper_moonbags),
        "execution_mode": okx_rest_service.execution_mode,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

@router.get("/system/settings")
async def get_system_settings():
    """V110.40: Retorna as configurações críticas para o Command Center PRO."""
    from main import VERSION
    return {
        "version": VERSION,
        "execution_mode": settings.OKX_EXECUTION_MODE,
        "max_slots": settings.MAX_SLOTS,
        "leverage": settings.LEVERAGE,
        "risk_cap": settings.RISK_CAP_PERCENT,
        "debug_mode": settings.DEBUG,
        "testnet": settings.OKX_TESTNET,
        "server_time": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

@router.post("/system/calibrate-bankroll", dependencies=[Depends(verify_api_key)])
async def calibrate_bankroll(payload: dict):
    """
    Força a banca configurada (configured_balance) e o saldo atual para recalibrar
    a integridade e a saúde do robô para 100% no modo REAL ou PAPER.
    """
    target = payload.get("balance")
    if not target:
        raise HTTPException(status_code=400, detail="Parâmetro 'balance' é obrigatório.")
    
    firebase_service, okx_rest_service, _, bankroll_manager, _ = get_services()
    from services.database_service import database_service
    
    target_val = float(target)
    report = []
    
    try:
        await database_service.update_banca_status({
            "configured_balance": target_val,
            "saldo_total": target_val,
            "lucro_total_acumulado": 0.0,
            "risco_real_percent": 0.0
        })
        report.append("✅ Postgres calibrado.")
    except Exception as e:
        report.append(f"⚠️ Postgres: {e}")
        
    try:
        if firebase_service.rtdb:
            firebase_service.rtdb.child("banca").update({
                "configured_balance": target_val,
                "saldo_total": target_val,
                "pnl_realized": 0.0
            })
            report.append("✅ Firebase RTDB calibrado.")
    except Exception as e:
        report.append(f"⚠️ Firebase RTDB: {e}")
        
    try:
        if firebase_service.is_active:
            await asyncio.to_thread(
                firebase_service.db.collection("banca_status").document("status").update,
                {
                    "configured_balance": target_val,
                    "saldo_total": target_val,
                    "lucro_total_acumulado": 0.0,
                    "risco_real_percent": 0.0
                }
            )
            await asyncio.to_thread(
                firebase_service.db.collection("users").document("admin").update,
                {
                    "bankroll_balance": target_val
                }
            )
            # Calibra o ciclo do Vault para ajustar a integridade na UI
            await asyncio.to_thread(
                firebase_service.db.collection("vault_management").document("current_cycle").update,
                {
                    "cycle_start_bankroll": target_val,
                    "cycle_bankroll": target_val,
                    "next_entry_value": target_val * 0.10
                }
            )
            report.append("✅ Firestore calibrado.")
    except Exception as e:
        report.append(f"⚠️ Firestore: {e}")
        
    okx_rest_service.paper_balance = target_val
    
    try:
        await bankroll_manager.update_banca_status()
        report.append("✅ BankrollManager atualizado.")
    except Exception as e:
        report.append(f"⚠️ BankrollManager: {e}")
        
    return {
        "status": "SUCCESS",
        "message": f"Banca calibrada para ${target_val:.2f}.",
        "report": report
    }

@router.get("/system/execution-diagnostics")
async def execution_diagnostics():
    """Diagnostico do modo de execucao para debug de ordens nao abertas."""
    try:
        from services.okx_service import okx_service as okx_svc
    except Exception:
        okx_svc = None
    return {
        "execution_mode": settings.OKX_EXECUTION_MODE,
        "has_master_api_key": bool(settings.OKX_API_KEY_MASTER),
        "has_api_key": bool(settings.OKX_API_KEY),
        "okx_service_mock": getattr(okx_svc, "is_mock", "UNKNOWN") if okx_svc else "UNINITIALIZED",
        "okx_testnet": getattr(okx_svc, "testnet", "UNKNOWN") if okx_svc else "UNINITIALIZED",
        "master_key_prefix": (settings.OKX_API_KEY_MASTER or "")[:8] + "..." if settings.OKX_API_KEY_MASTER else None,
        "captain_bypass_condition": bool(settings.OKX_API_KEY_MASTER or settings.OKX_EXECUTION_MODE == "PAPER"),
        "captain_mode": "REAL" if settings.OKX_API_KEY_MASTER and settings.OKX_EXECUTION_MODE != "PAPER" else "PAPER" if (settings.OKX_API_KEY_MASTER or settings.OKX_EXECUTION_MODE == "PAPER") else "DISABLED",
    }
