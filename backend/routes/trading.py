from fastapi import APIRouter, Depends, Header, HTTPException, Request
from typing import Optional, List
from services.auth_service import User, get_current_user
import logging
import asyncio
import datetime
from config import settings

router = APIRouter(prefix="/api", tags=["Trading"])
logger = logging.getLogger("1CRYPTEN-TRADING")

# Imports lazy to avoid circular dependency if any
def get_services():
    from services.firebase_service import firebase_service
    from services.okx_rest import okx_rest_service
    from services.execution_protocol import execution_protocol
    from services.vault_service import vault_service
    from services.bankroll import bankroll_manager
    return firebase_service, okx_rest_service, execution_protocol, vault_service, bankroll_manager

async def verify_api_key(x_api_key: str = Header(None)):
    if settings.DEBUG:
        return True
    if x_api_key != settings.ADMIN_API_KEY:
        logger.warning(f"🔒 Security Alert: Unauthorized access attempt in Trading Route")
        raise HTTPException(status_code=403, detail="Acesso Proibido: Chave de API Inválida")
    return True

@router.get("/slots")
async def get_slots():
    """[V110.999] Rota pública — lê slots globais do Postgres. Auth removida para evitar 401 com Fortress Auth."""
    from services.database_service import database_service as _ds
    from services.order_projection_service import order_projection_service
    _, okx_rest_service, execution_protocol, _, _ = get_services()
    try:
        db_slots = await _ds.get_active_slots()
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
                "rescue_resolved": s.get("rescue_resolved"),
                "projection": s.get("projection")
            })
            
        if slots:
            try:
                resp = await okx_rest_service.get_tickers()
                ticker_list = resp.get("result", {}).get("list", [])
                price_map = {t["symbol"]: float(t.get("lastPrice", 0)) for t in ticker_list}
            except Exception:
                price_map = {}

            for slot in slots:
                # [V110.999] FIX: Só limpa slots sem símbolo — não zero por qty/entry_price
                if not slot.get("symbol"):
                    slot.update({
                        "symbol": None,
                        "status_risco": "IDLE",
                        "visual_status": "SCANNING",
                        "score": 0,
                        "qty": 0,
                        "entry_price": 0,
                        "pnl_percent": 0,
                        "side": None,
                        "opened_at": 0
                    })
                    continue

                if slot.get("symbol") and slot.get("entry_price", 0) > 0:
                    slot_id = int(slot.get("id", 0))
                    slot["slot_type"] = slot.get("slot_type") or "BLITZ"
                    entry = float(slot.get("entry_price", 0))
                    side = slot.get("side", "Buy")
                    sym_clean = okx_rest_service._strip_p(slot["symbol"])
                    live_price = price_map.get(sym_clean, 0)
                    
                    if live_price > 0 and entry > 0:
                        projection = await order_projection_service.build_projection(
                            slot,
                            current_price=live_price,
                            phase_hint="SLOT",
                        )
                        roi = max(-500, min(5000, float(projection.get("roi_percent") or 0)))
                        projection["roi_percent"] = roi
                        slot["pnl_percent"] = round(roi, 1)
                        slot["projection"] = projection
                    
                    roi = slot.get("pnl_percent", 0)
                    phase_info = execution_protocol.get_sl_phase_info(roi, slot_data=slot)
                    slot["sl_phase"] = phase_info["phase"]
                    slot["sl_phase_icon"] = phase_info["icon"]
                    slot["sl_phase_color"] = phase_info["color"]
                    slot["visual_status"] = phase_info["phase"]
                else:
                    slot["sl_phase"] = "IDLE"
                    slot["sl_phase_icon"] = "⏳"
                    slot["sl_phase_color"] = "gray"
            return slots
    except Exception as e:
        logger.error(f"Error fetching slots: {e}")
    
    return [{"id": i, "symbol": None, "entry_price": 0, "current_stop": 0, "side": None, "sl_phase": "IDLE", "sl_phase_icon": "⏳"} for i in range(1, 5)]

@router.get("/signals")
async def get_signals(min_score: int = 0, limit: int = 20):
    firebase_service, _, _, _, _ = get_services()
    try:
        signals = await firebase_service.get_recent_signals(limit=limit)
        filtered = [s for s in signals if s.get("score", 0) >= min_score]
        if not filtered:
             return [{
                "id": "forced_debug",
                "symbol": "BTCUSDT",
                "score": 95,
                "indicators": {"cvd": 12.5},
                "is_elite": True,
                "timestamp": "Now"
            }]
        return filtered
    except Exception as e:
        logger.error(f"Error fetching signals: {e}")
        return [{"id": "forced_debug", "symbol": "BTCUSDT", "score": 95, "indicators": {"cvd": 10.5}, "is_elite": True, "timestamp": "Now"}]

@router.get("/history")
async def get_history(limit: int = 50, last_timestamp: str = None, symbol: str = None, start_date: str = None, end_date: str = None):
    firebase_service, _, _, _, _ = get_services()
    try:
        return await firebase_service.get_trade_history(
            limit=limit, 
            last_timestamp=last_timestamp,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date
        )
    except Exception as e:
        logger.error(f"Error fetching trade history: {e}")
        return []

@router.get("/history/stats")
async def get_history_stats(symbol: str = None, start_date: str = None, end_date: str = None):
    firebase_service, _, _, _, _ = get_services()
    try:
        return await firebase_service.get_trade_history_stats(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date
        )
    except Exception as e:
        logger.error(f"Error fetching trade stats: {e}")
        return {"total_count": 0, "total_pnl": 0.0}

@router.post("/history/report")
async def get_trade_report(payload: dict):
    trade_data = payload.get("trade_data")
    if not trade_data:
        return {"error": "Missing trade data"}
    
    symbol = trade_data.get("symbol", "Desconhecido")
    pnl = trade_data.get("pnl", 0)
    side = trade_data.get("side", "N/A")
    roi = trade_data.get("roi", 0)
    
    report = f"""**Telemetria de Combate: {symbol}**
Posição {side} encerrada com resultado de **${pnl:.2f}** ({roi:.2f}% ROI).
A justificativa primária de fechamento computada foi: `{trade_data.get('close_reason', 'N/A')}`.
A diretriz segue inalterada: Disciplina sobre a emoção."""
    return {"report": report}

@router.get("/moonbags")
async def get_moonbags(limit: int = 10):
    try:
        from services.database_service import database_service as _ds

        moonbags_list = await _ds.get_moonbags()
        # Se for None ou não for lista, garante lista vazia
        if not isinstance(moonbags_list, list):
            moonbags_list = []
        return moonbags_list[:limit]
    except Exception as e:
        logger.error(f"Error fetching moonbags: {e}")
        return []

@router.post("/nuke-paper")
async def nuke_paper_state(current_user: User = Depends(get_current_user)):
    _, okx_rest_service, _, _, bankroll_manager = get_services()
    from services.firebase_service import firebase_service
    cleared = []
    if okx_rest_service:
        okx_rest_service.paper_positions.clear()
        okx_rest_service.paper_moonbags.clear()
        okx_rest_service.paper_orders_history.clear()
        okx_rest_service.paper_balance = 100.0
        if hasattr(okx_rest_service, 'pending_closures'):
             okx_rest_service.pending_closures.clear()
        if hasattr(okx_rest_service, 'emancipating_symbols'):
             okx_rest_service.emancipating_symbols.clear()
        cleared.append("RAM deep cleanup")
        okx_rest_service._save_paper_state()
        cleared.append("disk-sync")
    if firebase_service:
        for i in range(1, 5):
            try: await firebase_service.hard_reset_slot(i, "NUKE_PAPER_API", pnl=0.0)
            except: pass
        try:
            await firebase_service.update_bankroll(100.0)
            cleared.append("banca_status_global_firestore")
        except: pass
        try:
            await asyncio.to_thread(firebase_service.rtdb.child("banca_status/status").update, {"saldo_total": 100.0, "lucro_acumulado": 0.0, "base_capital": 100.0})
            cleared.append("banca_status_rtdb")
        except: pass
        if current_user and current_user.username:
            try:
                await asyncio.to_thread(
                    firebase_service.db.collection("users").document(current_user.username).update,
                    {"bankroll_balance": 100.0}
                )
                cleared.append(f"user-{current_user.username}-bankroll")
            except Exception as e:
                logger.error(f"Error resetting Firestore user bankroll: {e}")
    return {"status": "success", "cleared": cleared}

