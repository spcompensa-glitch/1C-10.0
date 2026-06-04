import logging
import asyncio
import time
import traceback
from typing import Dict, Any, List
from services.firebase_service import firebase_service
from services.okx_rest import okx_rest_service
from services.agents.aios_adapter import AIOSAgent

logger = logging.getLogger("FleetAudit")

class FleetAudit(AIOSAgent):
    """
    V16.5: Specialized Agent for state parity and order reconciliation.
    V7.0: Enhanced with Early ROI Panic and Flash Protection.
    """
    def __init__(self):
        super().__init__(
            agent_id="agent-fleet-audit",
            role="auditor",
            capabilities=["reconciliation", "integrity", "cleanup"]
        )
        self.is_running = False
        self.reconciliation_interval = 20 # [V7.0] Higher frequency for Early ROI Panic
        self.last_reconciliation_time = 0

    async def on_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handles incoming messages from the Dispatcher (Kernel)."""
        logger.info(f"🔍 FleetAudit received message: {message.get('type')}")
        return {"status": "ACK", "agent": self.agent_id}

    async def start(self):
        self.is_running = True
        logger.info("🔍 FleetAudit ONLINE: Ensuring system parity & Early ROI Safety.")
        asyncio.create_task(self.run_loop())

    async def stop(self):
        self.is_running = False
        logger.info("🔍 FleetAudit OFFLINE.")

    async def run_loop(self):
        while self.is_running:
            try:
                await self.reconcile_orders()
            except Exception as e:
                logger.error(f"FleetAudit Loop Error: {e}")
            
            await asyncio.sleep(self.reconciliation_interval)

    async def reconcile_orders(self):
        """
        [V16.5] Systematic reconciliation moved from Captain.
        [V7.0] Added Early ROI Panic: Prevents immediate drawdowns.
        """
        now = time.time()
        self.last_reconciliation_time = now
        logger.info("🛡️ [AUDIT] Monitoring state parity & Early ROI Safety...")
        
        execution_mode = okx_rest_service.execution_mode
        
        try:
            # 1. Fetch current state
            slots = await firebase_service.get_active_slots()
            active_slots = [s for s in slots if s.get("symbol")]
            
            # 2. [V7.0] EARLY ROI PANIC PROTECTION
            for s in active_slots:
                sym = s.get("symbol")
                opened_at = s.get("opened_at", 0)
                pnl = s.get("pnl_percent", 0)
                side = s.get("side")
                qty = s.get("qty", 0)
                
                # [V80.6] Relaxed Panic for 50x/75x Leverage (Allow breathing room)
                # Age < 60s is COMPLETELY IMMUNE to panic (Diplomatic Immunity)
                try:
                    # Blindagem contra timestamp no formato datetime ou strings
                    if isinstance(opened_at, (int, float)):
                        opened_at_ts = float(opened_at)
                    elif hasattr(opened_at, "timestamp"):
                        opened_at_ts = opened_at.timestamp()
                    else:
                        opened_at_ts = float(opened_at or 0)
                except Exception:
                    opened_at_ts = now # fallback neutro se quebrar
                
                age = now - opened_at_ts
                if age < 60:
                    continue

                if age < 300 and pnl <= -80.0:
                    from services.signal_generator import signal_generator
                    is_spike, stretch = await signal_generator.is_price_stretched(sym, s.get("entry_price", 0))
                    
                    # If it's a fast spike against us OR ROI is already extreme
                    if is_spike or pnl <= -90.0:
                        msg = f"🛡️ [V70.1 EARLY PANIC] {sym} | ROI: {pnl:.2f}% | Age: {(now-opened_at):.1f}s. Emergency Exit protected banca."
                        logger.warning(msg)
                        
                        if execution_mode == "REAL":
                            await okx_rest_service.close_position(sym, side, qty)
                        else:
                            await okx_rest_service.paper_close_position(sym)
                            
                        await firebase_service.hard_reset_slot(s["id"], "EARLY_ROI_PANIC", pnl)
                        await firebase_service.log_event("AUDIT", msg, "CRITICAL")
                        continue

            # 3. [V110.125] State Parity (REAL MODE ONLY)
            if execution_mode == "REAL":
                real_positions = await okx_rest_service.get_active_positions()
                moonbags = await firebase_service.get_moonbags()
                
                # Active symbols on Bybit (Normalized)
                active_real_symbols = { p.get("symbol", "").replace(".P","").upper() for p in real_positions }
                
                # Unified Map for Position Check (Slots + Moonbags)
                active_db_map = {}
                for s in slots:
                    sym = (s.get("symbol") or "").replace(".P","").upper()
                    if sym: active_db_map[sym] = {"type": "SLOT", "data": s}
                
                for m in moonbags:
                    sym = (m.get("symbol") or "").replace(".P","").upper()
                    if sym: active_db_map[sym] = {"type": "MOONBAG", "data": m}

                # --- A. Check Bybit -> DB (Find Ghosts on Corretora) ---
                for pos in real_positions:
                    symbol = pos.get("symbol")
                    norm_symbol = symbol.replace(".P", "").upper()
                    side = pos.get("side")
                    size = float(pos.get("size", 0))
                    sl = float(pos.get("stopLoss", 0))
                    entry = float(pos.get("avgPrice") or pos.get("entryPrice", 0))
                    
                    db_entry = active_db_map.get(norm_symbol)
                    
                    if not db_entry:
                        logger.warning(f"🚨 [AUDIT] GHOST POSITION ON OKX: {symbol}. AUTO-CLOSING.")
                        await okx_rest_service.close_position(symbol, side, size, reason="AUDIT_GHOST_OKX")
                        continue
                    
                    slot_or_moon = db_entry["data"]
                    
                    # SL Recovery
                    db_stop = float(slot_or_moon.get("current_stop", 0))
                    is_sl_missing_or_deviant = False
                    
                    if sl == 0:
                        logger.warning(f"🚨 [AUDIT] MISSING SL for {symbol}. Recovering...")
                        is_sl_missing_or_deviant = True
                    elif db_stop > 0 and abs(sl - db_stop) / db_stop > 0.002: # Diferença > 0.2%
                        logger.warning(f"🚨 [AUDIT] DEVIANT SL for {symbol}: OKX={sl} vs DB={db_stop}. Synchronizing...")
                        is_sl_missing_or_deviant = True
                        
                    if is_sl_missing_or_deviant:
                        recovery_sl = db_stop
                        if recovery_sl <= 0:
                            recovery_sl = entry * 0.99 if side == "Buy" else entry * 1.01
                        
                        recovery_sl = await okx_rest_service.round_price(symbol, recovery_sl)
                        await okx_rest_service.set_trading_stop(category="linear", symbol=symbol, stopLoss=str(recovery_sl))
                        
                        if db_entry["type"] == "SLOT":
                            await firebase_service.update_slot(slot_or_moon["id"], {"current_stop": recovery_sl})
                        else:
                            await firebase_service.update_moonbag(slot_or_moon["id"], {"current_stop": recovery_sl})

                # --- B. Check DB -> Bybit (Find Ghost Moonbags in Firestore) ---
                for m in moonbags:
                    moon_id = m.get("id")
                    symbol = (m.get("symbol") or "").replace(".P", "").upper()
                    promoted_at = m.get("promoted_at", 0)
                    
                    # Buffer de 5 minutos para evitar race conditions durante a promoção
                    if (now - promoted_at) < 300:
                        continue
                        
                    if symbol not in active_real_symbols:
                        logger.warning(f"🌙 [AUDIT] GHOST MOONBAG IN DB: {symbol} ({moon_id}). PURGING.")
                        await firebase_service.remove_moonbag(moon_id, reason="AUDIT_GHOST_DB")
                        await firebase_service.log_event("AUDIT", f"Purga de Moonbag Fantasma: {symbol}", "INFO")

            # 4. [V110.136.2 F2] PAPER Ghost Moonbag Cleanup
            # Em PAPER mode, a verificacao de paridade nao rodava. Moonbags fantasmas
            # (fechados na simulacao mas ainda no Firestore) se acumulavam para sempre.
            elif execution_mode == "PAPER":
                try:
                    from services.okx_rest import okx_rest_service as bbs
                    moonbags_fb = await firebase_service.get_moonbags()
                    paper_moon_syms = {
                        p.get("symbol", "").replace(".P", "").upper()
                        for p in bbs.paper_moonbags
                    }
                    for m in moonbags_fb:
                        moon_id  = m.get("id")
                        m_symbol = (m.get("symbol") or "").replace(".P", "").upper()
                        promoted_at = m.get("promoted_at", 0)
                        
                        try:
                            if isinstance(promoted_at, (int, float)):
                                promoted_at_ts = float(promoted_at)
                            elif hasattr(promoted_at, "timestamp"):
                                promoted_at_ts = promoted_at.timestamp()
                            else:
                                promoted_at_ts = float(promoted_at or 0)
                        except Exception:
                            promoted_at_ts = now

                        # Buffer de 5 min para evitar race-condition na promocao
                        if (now - promoted_at_ts) < 300:
                            continue
                        if m_symbol not in paper_moon_syms:
                            msg = f"[PAPER-AUDIT] GHOST MOONBAG: {m_symbol} ({moon_id}) no Firestore mas ausente em paper_moonbags. Purgando."
                            logger.warning(msg)
                            await firebase_service.remove_moonbag(moon_id, reason="PAPER_AUDIT_GHOST")
                            await firebase_service.log_event("AUDIT", msg, "INFO")
                except Exception as paper_err:
                    logger.error(f"[PAPER-AUDIT] Erro no ghost cleanup: {paper_err}")

            # Update system pulse
            await firebase_service.update_system_state(
                "SCANNING",
                0,
                "Fleet Audit Complete",
                last_reconciliation=now
            )
            
        except Exception as e:
            logger.error(f"Audit execution error: {e}")
            traceback.print_exc()

# Global Instance
fleet_audit = FleetAudit()
