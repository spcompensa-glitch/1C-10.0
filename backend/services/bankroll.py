# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
import asyncio
import time
import math
import os
from typing import Optional, List, Dict, Any, Tuple
from services.firebase_service import firebase_service
from services.database_service import database_service
from services.okx_rest import okx_rest_service as okx_rest_service
from services.vault_service import vault_service
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BankrollManager")

def get_slot_type(slot_id: int) -> str:
    """
    [V110.802.6 ALL-BLITZ] Todos os 4 slots sao BLITZ_30M:
    - Extração rápida em 30M, sem distinção SWING.
    """
    return "BLITZ_30M"

class BankrollManager:
    def __init__(self):
        self.max_slots = settings.MAX_SLOTS  # [V111.0] até 40 slots
        self.risk_cap = settings.RISK_CAP_PERCENT  # 40% da banca (invariante)
        self.margin_per_slot = 0.10  # legacy (substituído por margin_per_trade dinâmico)
        self.initial_slots = 1
        # [V111.0] Margem por trade muda conforme regime de mercado
        self.margin_lateral = settings.MARGIN_PER_TRADE_LATERAL   # $2.00 — DECOR_HUNTER
        self.margin_trending = settings.MARGIN_PER_TRADE_TRENDING  # $1.00 — ELITE_40_MATRIX
        self.max_slots_lateral = settings.MAX_SLOTS_LATERAL    # 20 pares em lateral
        self.max_slots_trending = settings.MAX_SLOTS_TRENDING  # 40 pares em tendência
        self.last_log_times = {} # Cooldown for logs
        # V4.2: Sniper TP = +2% price = 100% ROI @ 50x
        self.sniper_tp_percent = 0.02  # 2% price movement
        self.execution_lock = asyncio.Lock() # Iron Lock Atomic Protector
        self.pending_slots = {} # V4.9.4.2: Local memory lock { (symbol, slot_id): timestamp }
        # [V25.0] Anti-Zombie Shield: Persistent closure registry with timestamps
        # Prevents re-adoption of recently closed positions for 120 seconds
        self.recently_closed: Dict[str, float] = {}  # { norm_symbol: closure_timestamp }
        # [V6.0] RESTRUTURAÇÃO ESTRATÉGICA: Ordem Única Estrita
        self.strict_single_order_mode = False  # [V53.0] Restaurado: 4 slots simultâneos
        # [V58.0] Inertia Shield: Cooldown to prevent duplicate openings for the same symbol
        # due to Firestore synchronization latency.
        self.recent_openings: Dict[str, float] = {} # { symbol: timestamp }
        
        # [V110.8] Exchange State Persistence for Orphan Closure Detection
        # Tracks ALL symbols seen on exchange to detect when they disappear, 
        # even if they weren't assigned to a tactical slot.
        self.last_seen_exchange: Dict[str, Dict] = {} # { norm_symbol: pos_data }
        self.ghost_tracker: Dict[int, int] = {}       # { slot_id: missing_count } (V110.19.0)
        # [V110.19.3] ABSOLUTE GHOST-LOCK: Long-term memory to prevent flickering
        self.active_slot_memory: Dict[int, Dict] = {} # { slot_id: {"symbol": symbol, "last_seen": timestamp} }
        self.boot_time = time.time()  # [V110.23.2] Boot Sequence Tracker for Grace Period
        
        # [V110.62] GUARDIAN HEDGE (Slot Zero)
        self.hedge_active = False
        self.hedge_position_id = None
        self._hedge_lock = asyncio.Lock()

    def is_recently_closed(self, symbol: str) -> bool:
        """
        [V25.0] Check if symbol was closed in the last 120 seconds to prevent phantom re-adoption.
        """
        now = time.time()
        # Clean up old entries
        expired = [s for s, t in self.recently_closed.items() if now - t > 120]
        for s in expired:
            del self.recently_closed[s]
            
        if symbol in self.recently_closed:
            logger.info(f"🛡️ [ANTI-ZOMBIE] Blocking {symbol} - closed {(now - self.recently_closed[symbol]):.1f}s ago.")
            return True
        return False

    def register_recently_closed(self, symbol: str):
        """
        [V25.0] Register a symbol as recently closed to prevent immediate re-entry.
        """
        norm_symbol = symbol.replace(".P", "").upper()
        self.recently_closed[norm_symbol] = time.time()
        logger.info(f"🛡️ [ANTI-ZOMBIE] Registered {norm_symbol} in recently_closed cooldown (120s).")

    async def _force_paper_reset_v110(self):
        """
        [V110.6.2] NUCLEAR RESET: Força a banca ao valor do settings.OKX_SIMULATED_BALANCE absoluto no Firebase.
        Útil para limpar a memória de profit acumulado em ambientes Cloud Run.
        """
        if not firebase_service.is_active:
            await firebase_service.initialize()
            
        if not firebase_service.is_active:
            logger.error("❌ [V110.6.2] Firebase NOT active for force reset. Aborting.")
            return False

        try:
            from services.vault_service import vault_service
            target_bal = settings.OKX_SIMULATED_BALANCE
            logger.warning(f"💥 [V110.6.2] Performing absolute bankroll reset to ${target_bal:.2f}...")
            
            # 1. Reset no DB (Atômico)
            reset_data = {
                "configured_balance": target_bal,
                "saldo_total": target_bal,
                "lucro_ciclo": 0.0,
                "lucro_total_acumulado": 0.0,
                "vault_total": 0.0,
                "risco_real_percent": 0.0,
                "slots_disponiveis": 4,
                "status": "ONLINE",
                "timestamp_last_update": time.time()
            }
            # Use await to thread for consistency with other firebase calls
            await asyncio.to_thread(firebase_service.db.collection("banca_status").document("status").set, reset_data)
            
            if firebase_service.rtdb:
                await asyncio.to_thread(firebase_service.rtdb.child("banca_status").set, reset_data)
            
            logger.info(f"✅ [V110.6.2] Firebase Bankroll Reset COMPLETE (${target_bal}).")
            return True
        except Exception as e:
            logger.error(f"Error in _force_paper_reset_v110: {e}")
            return False

    async def _get_operating_balance(self, username: str = None) -> float:
        """
        [V120] Soberania Multitenant: 
        Busca o saldo total isolado do usuário no Firestore.
        """
        try:
            # [V120] Busca o saldo diretamente do perfil do usuário
            if username:
                user_doc = await firebase_service.db.collection("users").document(username).get()
                if user_doc.exists:
                    data = user_doc.to_dict()
                    ui_saldo_total = float(data.get("bankroll_balance", 100.0))
                    return max(ui_saldo_total, 1.0)

            # Fallback Legacy / Admin
            banca_data = await firebase_service.get_banca_status()
            config_bal = float(banca_data.get("configured_balance", 100.0))
            ui_saldo_total = float(banca_data.get("saldo_total", config_bal))
            return max(ui_saldo_total, 1.0)
            
        except Exception as e:
            logger.error(f"Error calculating operating balance for {username}: {e}")
            return 100.0

    async def get_live_operating_equity(self) -> float:
        """
        Returns live paper equity for operational kill-switches.
        It includes realized history and open PnL, not only configured balance.
        """
        try:
            base_balance = float(settings.OKX_SIMULATED_BALANCE)
            banca = await database_service.get_banca_status()
            if banca:
                configured = self._safe_float(banca.get("configured_balance"), 0.0)
                if configured > 0:
                    base_balance = configured

            slots = await database_service.get_active_slots()
            moonbags = await database_service.get_moonbags()
            history = await database_service.get_trade_history(limit=1000)
            realized_pnl = sum(self._safe_float(trade.get("pnl"), 0.0) for trade in history)
            snapshot = self._paper_equity_snapshot(
                base_balance=base_balance,
                realized_pnl=realized_pnl,
                active_slots=slots,
                active_moonbags=moonbags,
            )
            return float(snapshot["calculated_equity"])
        except Exception as e:
            logger.error(f"Error calculating live operating equity: {e}")
            return await self._get_operating_balance()

    def _is_slot_risk_free(self, slot: dict) -> bool:
        """
        [V10.4] Check if a slot has reached Risk-Free status.
        Risk-Free = Stop Loss at or beyond entry price (locked profit).
        """
        if not slot or not slot.get("symbol"):
            return False
        entry = slot.get("entry_price", 0)
        stop = slot.get("current_stop", 0)
        side = (slot.get("side") or "").upper()
        if entry <= 0 or stop <= 0:
            return False
        if side == "BUY" and stop >= entry:
            return True
        if side == "SELL" and stop <= entry:
            return True
        return False

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value is None or value == "":
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _position_pnl_usd(self, position: Dict[str, Any]) -> float:
        projection = position.get("projection")
        if isinstance(projection, dict):
            projected_pnl = projection.get("pnl_usd")
            if projected_pnl is not None:
                return self._safe_float(projected_pnl, 0.0)

        direct_pnl = position.get("pnl_usd")
        if direct_pnl is not None:
            return self._safe_float(direct_pnl, 0.0)

        pnl = position.get("pnl")
        if pnl is not None:
            return self._safe_float(pnl, 0.0)

        roi = self._safe_float(
            position.get("pnl_percent")
            or position.get("roi_percent")
            or position.get("roi"),
            0.0,
        )
        margin = self._safe_float(position.get("entry_margin"), 0.0)

        if margin <= 0 and isinstance(projection, dict):
            margin = self._safe_float(projection.get("entry_margin"), 0.0)

        if margin <= 0:
            entry = self._safe_float(position.get("entry_price"), 0.0)
            qty = self._safe_float(position.get("qty"), 0.0)
            leverage = self._safe_float(position.get("leverage"), 50.0)
            contract = projection.get("contract") if isinstance(projection, dict) else position.get("contract_meta")
            ct_val = self._safe_float(contract.get("ct_val") if isinstance(contract, dict) else None, 1.0)
            if entry > 0 and qty > 0 and leverage > 0:
                margin = (entry * qty * ct_val) / leverage

        return (roi / 100.0) * margin if margin > 0 else 0.0

    def _paper_equity_snapshot(
        self,
        base_balance: float,
        realized_pnl: float,
        active_slots: List[Dict[str, Any]],
        active_moonbags: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        active_slots = [
            slot for slot in active_slots
            if slot.get("symbol") and self._safe_float(slot.get("qty"), 0.0) > 0
        ]
        active_moonbags = [
            moonbag for moonbag in active_moonbags
            if moonbag.get("symbol") and self._safe_float(moonbag.get("qty"), 0.0) > 0
        ]
        open_slots_pnl = sum(self._position_pnl_usd(slot) for slot in active_slots)
        open_moonbags_pnl = sum(self._position_pnl_usd(moonbag) for moonbag in active_moonbags)
        calculated_equity = base_balance + realized_pnl + open_slots_pnl + open_moonbags_pnl

        return {
            "base_balance": base_balance,
            "realized_pnl": realized_pnl,
            "open_slots_pnl": open_slots_pnl,
            "open_moonbags_pnl": open_moonbags_pnl,
            "float_pnl": open_slots_pnl + open_moonbags_pnl,
            "calculated_equity": calculated_equity,
            "active_slots": float(len(active_slots)),
            "active_moonbags": float(len(active_moonbags)),
        }

    async def _audit_zombie_slots(self, firestore_slots: list, exchange_map: dict):
        """
        [V110.11] GHOSTBUSTER LOOP
        Tolerância Zero para Ordens Fantasmas. Se um slot estiver preenchido no Firebase,
        mas o símbolo não constar na Exchange real (ou na Memória Local em Paper Mode),
        forçamos a imediata purgação do slot.
        """
        for slot in firestore_slots:
            sym = slot.get("symbol")
            slot_id = slot.get("id")
            
            # Pula slots vazios ou já emancipados
            if not sym or not slot_id or slot.get("status") == "EMANCIPATED":
                continue
                
            norm_sym = okx_rest_service._strip_p(sym).upper()
            
            # Fonte da Verdade: A Corretora Real ou a Memória Paper
            is_alive = False
            if okx_rest_service.execution_mode == "PAPER":
                is_alive = any((okx_rest_service._strip_p(p.get("symbol", "")) or "").upper() == norm_sym for p in okx_rest_service.paper_positions)
            else:
                is_alive = norm_sym in exchange_map
                
            if not is_alive:
                # [V110.12.9] GRACE PERIOD SHIELD
                opened_at_raw = slot.get("opened_at", 0)
                life_sec = time.time() - opened_at_raw if opened_at_raw > 0 else 9999
                
                # [V110.61] GENESIS-SHIELD: Proteção Inviolável de Gênese
                # Se existe um registro de nascimento imutável para esta ordem,
                # proibimos a purga por "Ghost" durante os primeiros 30 minutos (1800s).
                order_id = slot.get("order_id")
                if not order_id and sym and opened_at_raw:
                    order_id = f"{sym.replace('.P', '')}_{int(opened_at_raw)}"
                
                if order_id:
                    genesis = await firebase_service.get_order_genesis(order_id)
                    if genesis:
                        # Se temos a gênese, confiamos que a ordem é real, mesmo que a RAM tenha sumido
                        if life_sec < 1800:
                            if int(life_sec) % 30 == 0:
                                logger.info(f"🛡️ [V110.61 GENESIS-SHIELD] Mantendo {sym} (Slot {slot_id}) via imutabilidade. Age: {int(life_sec)}s")
                            continue

                # Fallback: Proteção de Graça Curta
                if life_sec < 600:
                    logger.info(f"⏳ [GRACE] {sym} in slot {slot_id} not found in exchange. Waiting 10m before purge (Current: {life_sec:.0f}s).")
                    continue
                    
                logger.error(f"👻 [GHOSTBUSTER] Slot {slot_id} ({sym}) é um FANTASMA! Não existe na fonte da verdade. Purgando com relatório...")
                
                # [V110.19.1] Build Auditoria Report for Vault History
                from services.time_utils import get_br_iso_str
                close_time_str = get_br_iso_str()
                report = f"--- RELATÓRIO DE AUDITORIA GHOSTBUSTER ---\n"
                report += f"SÍMBOLO: {sym}\n"
                report += f"BATALHÃO: {get_slot_type(slot_id)} (Slot {slot_id})\n"
                report += f"MOTIVO: DESAPARECIMENTO SÚBITO (GHOST)\n"
                report += f"A ordem não foi encontrada na Corretora após o período de carência de 600s.\n"
                report += f"Possível encerramento manual externo ou falha de sincronização da API.\n"
                report += f"\n⏰ Detecção: {close_time_str}\n"
                report += f"------------------------------------------"

                trade_data = {
                    "symbol": sym,
                    "side": slot.get("side", "Unknown"),
                    "entry_price": float(slot.get("entry_price", 0)),
                    "exit_price": float(slot.get("entry_price", 0)), # Fallback
                    "qty": float(slot.get("qty", 0)),
                    "order_id": f"ghost_{sym}_{int(opened_at_raw)}",
                    "pnl": 0.0,
                    "slot_id": slot_id,
                    "slot_type": get_slot_type(slot_id),
                    "close_reason": "GHOSTBUSTER_PURGE",
                    "reasoning_report": report,
                    "closed_at": close_time_str
                }

                # V110.25.1: Bloqueia o registro de lixo $0.00 no histórico se for purga de sistema (Ghost)
                if hasattr(firebase_service, "hard_reset_slot"):
                    await firebase_service.hard_reset_slot(slot_id, reason="GHOSTBUSTER_PURGE", pnl=0.0, trade_data=trade_data)
                    # logger.info("Ghost purgada. Registro de histórico omitido para manter Vault limpo.")
                else:
                    await firebase_service.free_slot(slot_id, reason="GHOSTBUSTER_PURGE")

    async def sync_slots_with_exchange(self):
        """
        [V110.8] Critical Synchronization: Bybit-as-Truth Model.
        Reconciles Firestore slots with real/simulated exchange positions.
        """
        # [V110.25.0] Initialization Safety: Wait until OKXRest is ready (Paper/Real)
        if not okx_rest_service.is_ready:
            # logger.info("🛡️ [SYNC-GUARD] OKXRest base not ready. Postponing sync cycle.")
            return

        logger.info("🛡️ [SYNC] Starting Bybit-as-Truth Synchronization...")
        try:
            # [V110.180] AUTO-ADOPT-DYNAMIC (Amnesia-Guard dinâmico para evitar purga fantasma)
            if okx_rest_service.execution_mode == "PAPER":
                try:
                    slots_for_adopt = await firebase_service.get_active_slots(force_refresh=True)
                    if slots_for_adopt:
                        local_symbols = {p.get("symbol", "").upper().replace(".P", "") for p in okx_rest_service.paper_positions}
                        for f_slot in slots_for_adopt:
                            symbol = f_slot.get("symbol")
                            entry_price = float(f_slot.get("entry_price", 0))
                            qty = float(f_slot.get("qty", 0))
                            if symbol and entry_price > 0 and qty > 0:
                                norm_symbol = symbol.upper().replace(".P", "")
                                if norm_symbol not in local_symbols:
                                    logger.warning(f"🚑 [AUTO-ADOPT-DYNAMIC] Adotando ordem órfã do Postgres para RAM: {symbol} @ ${entry_price} (Qty: {qty})")
                                    recovered_pos = {
                                        "symbol": symbol,
                                        "side": f_slot.get("side", "Buy"),
                                        "size": str(f_slot.get("qty", 0)),
                                        "avgPrice": str(f_slot.get("entry_price", 0)),
                                        "leverage": str(f_slot.get("leverage", 50)),
                                        "status": "RECOVERED",
                                        "stopLoss": str(f_slot.get("current_stop", 0)),
                                        "takeProfit": str(f_slot.get("target_price", 0)),
                                        "opened_at": f_slot.get("opened_at", time.time()),
                                        "is_paper": True,
                                        "slot_id": f_slot.get("id", 0),
                                        "entry_margin": f_slot.get("entry_margin", 0),
                                        "genesis_id": f_slot.get("genesis_id", ""),
                                        "score": f_slot.get("score", 0),
                                        "fleet_intel": f_slot.get("fleet_intel", {}),
                                        "pensamento": f_slot.get("pensamento", ""),
                                        "slot_type": f_slot.get("slot_type", "SNIPER"),
                                    }
                                    okx_rest_service.paper_positions.append(recovered_pos)
                                    local_symbols.add(norm_symbol)
                except Exception as adopt_err:
                    logger.error(f"❌ [AUTO-ADOPT-DYNAMIC-ERROR] Falha ao auto-adotar posições simuladas: {adopt_err}")

            # 1. Fetch Current State
            exchange_positions = await okx_rest_service.get_active_positions()
            slots = await firebase_service.get_active_slots(force_refresh=True)
            
            # Map normalized symbols for comparison (with null-safety)
            exchange_map = {}
            for p in exchange_positions:
                sym = p.get("symbol")
                if sym:
                    exchange_map[okx_rest_service._strip_p(sym).upper()] = p
            
            current_exchange_symbols = set(exchange_map.keys())
            active_symbols = list(current_exchange_symbols)
            logger.info(f"📊 [SYNC] Exchange Positions ({len(active_symbols)}): {active_symbols}")

            # [V110.11] GHOSTBUSTER AUDIT: Executa auditoria antes de qualquer reconciliação pesada
            await self._audit_zombie_slots(slots, exchange_map)

            # [V110.8] ORPHAN SAFETY REAPER: Detect closed positions BEFORE checking slots.
            # Compare what was there in the last heartbeat vs now.
            disappeared = [sym for sym in self.last_seen_exchange if sym not in current_exchange_symbols]
            
            if disappeared:
                # Get tracked tactical symbols
                tactical_symbols = {okx_rest_service._strip_p(s.get("symbol") or "").upper() for s in slots if s.get("symbol")}
                # Also Moonbags
                moonbags = await firebase_service.get_moonbags()
                moon_symbols = {okx_rest_service._strip_p(m.get("symbol") or "").upper() for m in moonbags}
                all_tracked_symbols = tactical_symbols.union(moon_symbols)
                
                for sym in disappeared:
                    # If it's NOT in tactical or moonbags, it was an ORPHAN position.
                    # We MUST register its closure now or it's lost forever.
                    if sym not in all_tracked_symbols:
                        logger.warning(f"⚠️ [SAFETY REAPER] Orphan closure detected for {sym}. Documenting now.")
                        try:
                            closed_list = await okx_rest_service.get_closed_pnl(symbol=sym, limit=3)
                            if closed_list:
                                last_pnl = closed_list[0]
                                pnl_val = float(last_pnl.get("closedPnl", 0))
                                
                                # [V110.12.9] ANTI-MASSACRE: Capping Paper losses at margin value
                                from config import settings
                                if getattr(settings, "EXECUTION_MODE", "PAPER") == "PAPER":
                                    entry_margin_est = float(last_pnl.get("qty", 0)) * float(last_pnl.get("avgEntryPrice", 0)) / 50
                                    if pnl_val < -entry_margin_est:
                                        pnl_val = -entry_margin_est
                                        logger.warning(f"🛡️ [V110.12.9 PAPER CAP] PnL for {sym} capped at {pnl_val:.2f} (Margin Protection).")

                                trade_data = {
                                    "symbol": sym,
                                    "side": last_pnl.get("side", "Unknown"),
                                    "entry_price": float(last_pnl.get("avgEntryPrice", 0)),
                                    "exit_price": float(last_pnl.get("avgExitPrice", 0)),
                                    "qty": float(last_pnl.get("qty", 0)),
                                    "order_id": last_pnl.get("orderId", f"orphan_{sym}_{last_pnl.get('updatedTime', int(time.time()))}"),
                                    "pnl": pnl_val,
                                    "slot_id": 0, # Orphan slot
                                    "slot_type": "ORPHAN_AUTO_SYNC",
                                    "close_reason": "ORPHAN_SYNC_RECOVERY",
                                    "closed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                                }
                                await self.register_sniper_trade(trade_data)
                                logger.info(f"✅ [RECOVERY] Orphan trade {sym} registered in history | PnL: ${pnl_val:.2f}")
                        except Exception as e:
                            logger.error(f"Failed to register orphan closure for {sym}: {e}")

            # Update last_seen for next iteration
            self.last_seen_exchange = exchange_map

            # 2. Fetch DB Slots
            slots = await firebase_service.get_active_slots()
            
            # 3. Persistence Logic for PAPER MODE
            for slot in slots:
                symbol = slot.get("symbol")
                if not symbol: continue
                norm_symbol = (okx_rest_service._strip_p(symbol) or "").upper()
                slot_id = slot["id"]

                entry_ts = slot.get("timestamp_last_update") or 0
                elapsed_shield = time.time() - entry_ts
                # [V53.5] Stronger re-adoption protection: 45s shield.
                # Prevents flapping if the execution loop hasn't picked up the memory change yet.
                if elapsed_shield < 45:
                     continue

                # [V110.36.10] SSOT ADX: Usar o M-ADX Master real para evitar rejeições fantasmas de sinal
                from services.okx_ws_public import okx_ws_public_service
                btc_adx = getattr(okx_ws_public_service, "btc_adx", 0)
                
                if norm_symbol in exchange_map:
                    # [V110.64 FIX] Reduzido de 28→18, consistente com a nova Guilhotina.
                    # Apenas bloqueia RE-ADOÇÃO de órfãos em lateral extremo, não atualização de slots existentes.
                    if btc_adx < 18 and not slot.get("symbol"):
                        # Em lateral, precisamos saber se essa posição é Shadow Strike
                        from services.signal_generator import signal_generator
                        d_res = await signal_generator.detect_btc_decorrelation(symbol)
                        is_shadow_env = d_res.get('is_decorrelated', False) and d_res.get('confidence', 0) >= 85
                        
                        if not is_shadow_env:
                            logger.warning(f"🛡️ [ANTI-GHOST] {symbol} detectado na exchange mas BTC ADX {btc_adx:.1f} < 18 e NÃO é Shadow Strike 85+. Ignorando recuperação para evitar fantasmas.")
                            continue

                    # UPDATING ACTIVE SLOT WITH REAL EXCHANGE DATA
                    pos = exchange_map[norm_symbol]
                    
                    # [V28.1 BUGFIX] No Bybit UTA (Unified Trading Account), o positionIM pode vir próximo a zero 
                    # devido à margem de portfólio cruzada, causando inflação bizarra no cálculo do ROI % (ex: 39196%).
                    # Sempre calcular a margem baseada no tamanho e preço real!
                    leverage = slot.get("leverage", 50)
                    pos_size = float(pos.get("size", 0))
                    pos_entry = float(pos.get("avgPrice", 0))

                    # [V110.10 SANITY GUARD] Se pos_size ou pos_entry for zero/ínfimo,
                    # pode ser dado transitório da API. Aguarda 90s antes de purgar.
                    if pos_size <= 0 or pos_entry <= 0:
                        opened_at_raw = slot.get("opened_at", 0) or 0
                        age_sec = time.time() - opened_at_raw if opened_at_raw > 0 else 9999
                        if age_sec < 90:
                            logger.warning(f"⌛ [SANITY GUARD] {symbol} size={pos_size} entry={pos_entry} — aguardando grace period de 90s (atual: {age_sec:.0f}s).")
                            continue
                        logger.warning(f"🚨 [SANITY GUARD] Ghost slot confirmado: {symbol} size={pos_size} entry={pos_entry} após {age_sec:.0f}s. LIMPANDO.")
                        await firebase_service.hard_reset_slot(slot_id, reason="GHOST_ZERO_SIZE_PURGE")
                        continue

                    real_margin = (pos_size * pos_entry) / leverage if leverage > 0 else 1.0
                    
                    # Se mesmo assim a margem for ínfima/zero, garante um divisor mínimo p/ evitar crash
                    if real_margin < 0.01:
                        real_margin = 1.0
                    
                    unrealised_pnl = float(pos.get("unrealisedPnl", 0))
                    raw_pnl_pct = (unrealised_pnl / real_margin * 100) if real_margin > 0 else 0

                    # [V110.10.1] Verifica ROI irreal ANTES do cap (sinal claro de slot fantasma com dados corrompidos)
                    if raw_pnl_pct > 500 or raw_pnl_pct < -200:
                        logger.warning(f"🚨 [SANITY GUARD] ROI impossível para {symbol}: {raw_pnl_pct:.1f}%. unrealised={unrealised_pnl} margin={real_margin}. PURGANDO SLOT.")
                        await firebase_service.hard_reset_slot(slot_id, reason=f"IMPOSSIBLE_ROI_GHOST_{raw_pnl_pct:.0f}pct")
                        continue

                    # [V110.12.10] ABSOLUTE ROI SHIELD: Cap em -100% (Proteção de Liquidação)
                    pnl_pct = max(raw_pnl_pct, -100.0)
                    if raw_pnl_pct < -100.0:
                        logger.warning(f"💥 [ROI-SHIELD] {symbol} ROI capeado em -100% (era {raw_pnl_pct:.1f}%).")

                    # V42.9: Inject symbol-specific ADX and Regime for Dashboard visibility
                    from services.signal_generator import signal_generator
                    regime_data = await signal_generator.detect_market_regime(symbol)
                    symbol_adx = regime_data.get("adx", 20)
                    market_regime = regime_data.get("regime", "TRANSITION")

                    # [V57.0] Inject Decorrelation Health
                    d_res = await signal_generator.detect_btc_decorrelation(symbol)
                    d_active = d_res.get('is_decorrelated', False)
                    d_score = d_res.get('confidence', 0)
                    
                    d_health = "DEAD"
                    if d_active and d_score >= 60:
                        d_health = "ALIVE"
                    elif d_score >= 30:
                        d_health = "FADING"
                    
                    decorrelation_health = {
                        "score": round(d_score, 1),
                        "status": d_health,
                        "updated_at": time.time()
                    }

                    # [V56.0] Enrich slot with real-time intelligence from Captain
                    try:
                        from services.agents.captain import captain_agent
                        unified_confidence = slot.get("unified_confidence", 50)
                        fleet_intel = slot.get("fleet_intel", {})
                        last_intel_update = slot.get("timestamp_last_intel", 0)
                        # Only fetch if we don't have it or it's old (every 5 mins) or stuck at 50%
                        if (time.time() - last_intel_update > 300) or not fleet_intel or (unified_confidence <= 50):
                            consensus = await captain_agent._get_fleet_consensus({"symbol": symbol, "side": slot.get("side", "Buy")})
                            if consensus:
                                unified_confidence = consensus.get("unified_confidence", 50)
                                fleet_intel = consensus.get("intel", {})
                                last_intel_update = time.time()
                    except Exception as e:
                        logger.warning(f"Failed to enrich slot {slot_id} with intelligence: {e}")

                    # [V110.25.1] DATA INTEGRITY GHOST-BUSTING
                    # Se o ID de ordem ou símbolo mudou mas o slot não foi limpo atomicamente,
                    # podemos ter stops residuais (ex: GALA stop em JUP slot). Fix-on-Fly.
                    initial_stop = slot.get("initial_stop", 0)
                    if initial_stop > 0 and pos_entry > 0:
                        # [V110.28.2 FIX] Usar pos_entry (ja definido) em vez de entry_price (fora do scope)
                        diff_pct = abs(initial_stop - pos_entry) / pos_entry
                        if diff_pct > 0.5: # Discrepância maior que 50% é lixo residual
                            logger.warning(f"🚨 [INTEGRITY-FIX] Garbage Initial Stop detected ({initial_stop}) for {symbol} (Entry: {pos_entry}). Recalculating.")
                            # [V110.63.4] FIX: calculate_initial_stop não existe mais. 
                            # Usamos recuo padrão do HARD_STOP_ROI (-80.0% ROI / 50x = 1.6% preço)
                            side_fix = pos.get("side", "Buy")
                            price_risk_pct = 0.016 
                            initial_stop = pos_entry * (1 - price_risk_pct) if side_fix == "Buy" else pos_entry * (1 + price_risk_pct)

                    await firebase_service.update_slot(slot_id, {
                        "entry_margin": real_margin,
                        "pnl_percent": round(pnl_pct, 1),
                        "qty": float(pos.get("size", 0)),
                        "entry_price": float(pos.get("avgPrice", 0)),
                        "current_stop": float(pos.get("stopLoss", 0)), # V14.2: Active SL Sync from Exchange
                        "initial_stop": initial_stop, # V110.23.4: Preserve INIT (Safeified by Integrity Loop)
                        "liq_price": float(pos.get("liqPrice", 0)),
                        "target_price": slot.get("target_price") or float(pos.get("takeProfit", 0)), # V22.0: Preserve or Extract TP
                        "slot_type": slot.get("slot_type") or get_slot_type(slot_id), # V22.0: Preserve slot type
                        "pattern": slot.get("pattern"), # V22.0: Preserve pattern
                        "symbol_adx": symbol_adx,
                        "market_regime": market_regime,
                        "decorrelation_health": decorrelation_health,
                        "unified_confidence": unified_confidence,
                        "fleet_intel": fleet_intel,
                        "pensamento": f"⚓ [V56.5] Fleet Consensus: {unified_confidence}% | Bias: {fleet_intel.get('bias', 'Analyzing...')}",
                        "timestamp_last_intel": last_intel_update,
                        "sentinel_first_hit_at": slot.get("sentinel_first_hit_at", 0),
                        "timestamp_last_update": time.time()
                    })
                    self.ghost_tracker[slot_id] = 0 # Reset ghost tracker on healthy sync
                    
                    # [V110.19.3] Update LPM (Long Term Memory) when seen on exchange
                    self.active_slot_memory[slot_id] = {
                        "symbol": norm_symbol,
                        "last_seen": time.time()
                    }
                    continue

                if okx_rest_service.execution_mode == "PAPER":
                    # [V25.0] ANTI-ZOMBIE SHIELD (3 Layers):
                    # Layer 1: Check pending_closures (short-term, 15s window)
                    if norm_symbol in okx_rest_service.pending_closures:
                        logger.info(f"Sync [PAPER]: {symbol} has a pending closure. Blocking phantom re-adoption and CLEARING SLOT.")
                        await firebase_service.hard_reset_slot(slot_id, reason="PAPER_CLOSED_SYNC")
                        continue

                    # Layer 2: Check recently_closed registry (persistent, 120s window)
                    if self.is_recently_closed(norm_symbol):
                        logger.info(f"Sync [PAPER]: {symbol} is recently closed. CLEARING SLOT to avoid zombie UI.")
                        await firebase_service.hard_reset_slot(slot_id, reason="PAPER_RECENTLY_CLOSED")
                        continue

                    # [V53.8] Layer 3: Blocklist & Duplicate Safety
                    from services.signal_generator import signal_generator
                    if norm_symbol in getattr(signal_generator, 'asset_blocklist_permanent', set()):
                        logger.warning(f"Sync [PAPER]: {symbol} in PERMANENT BLOCKLIST. Clearing slot {slot_id}.")
                        await firebase_service.update_slot(slot_id, {
                            "symbol": None, "status_risco": "LIVRE", "pnl_percent": 0,
                            "entry_price": 0, "current_stop": 0, "entry_margin": 0, "side": None
                        })
                        continue

                    combined_all = okx_rest_service.paper_positions + okx_rest_service.paper_moonbags
                    if any(p.get("symbol", "").upper() == norm_symbol for p in combined_all):
                        # Se já está no motor de simulação, não precisamos re-adotar, mas atualizamos o mapa local
                        logger.info(f"Sync [PAPER]: {symbol} já está no motor (Positions ou Moonbags). Pulando re-adoção.")
                        match = next(p for p in combined_all if p.get("symbol", "").upper() == norm_symbol)
                        exchange_map[norm_symbol] = match
                        continue

                    entry_price = float(slot.get("entry_price", 0))
                    if entry_price <= 0:
                        logger.warning(f"Sync [PAPER PERSISTENCE]: Slot {slot_id} ({symbol}) has 0.0 entry price. CLEARING GHOST SLOT.")
                        await firebase_service.free_slot(slot_id, "Ghost Position Purge (0.0 Price)")
                        continue

                    # [V110.19.3] GHOST-LOCK PROTECTION
                    # A ordem só é purgada se:
                    # 1. Sumir por mais de 20 ciclos de sincronização (aprox 10-20 min)
                    # 2. OU se a memória de longo prazo (LPM) indicar que a posição sumiu há mais de 15 minutos.
                    
                    current_count = self.ghost_tracker.get(slot_id, 0) + 1
                    self.ghost_tracker[slot_id] = current_count
                    
                    # [V110.19.3] LPM Protection for Paper Mode
                    lpm_data = self.active_slot_memory.get(slot_id, {})
                    lpm_symbol = lpm_data.get("symbol")
                    lpm_last_seen = lpm_data.get("last_seen", 0)
                    lpm_age = time.time() - lpm_last_seen if lpm_last_seen > 0 else 9999
                    
                    # [V110.25.8] EXTREME GHOST-LOCK: 30 minutes (1800s)
                    is_lpm_protected = (lpm_symbol == norm_symbol and lpm_age < 1800)
                    
                    # [V110.60] EXTENDED BOOT GRACE: 20 minutes (was 10) to allow Full Sync on Cloud Run restarts
                    is_boot_grace = (time.time() - self.boot_time) < 1200
                    
                    # [V110.20.0] ABSOLUTE GHOST-LOCK: 50 cycles (~25-50 min)
                    if (current_count < 50 and is_lpm_protected) or is_boot_grace:
                        if current_count % 5 == 0 or is_boot_grace:
                            msg = f"👻 [GHOST-LOCK PAPER] {symbol} missing."
                            if is_boot_grace: msg += " Protected by BOOT GRACE (10m)."
                            else: msg += f" Protected by EXTREME LPM (Age: {int(lpm_age)}s, Limit: 30m)."
                            logger.warning(msg)
                        continue
                        
                    logger.warning(f"🚨 [PAPER-PURGE] Ghost Slot {slot_id} ({symbol}) missing persistently (Age: {int(lpm_age)}s). CLEARING.")
                    
                    from services.time_utils import get_br_iso_str
                    close_time_str = get_br_iso_str()
                    report = f"--- RELATÓRIO DE AUDITORIA PAPER GHOST ---\n"
                    report += f"SÍMBOLO: {symbol}\n"
                    report += f"MOTIVO: DESAPARECIMENTO PERSISTENTE (5/5 checks)\n"
                    report += f"A ordem Shadow em modo Paper sumiu da memória local e não retornou.\n"
                    report += f"\n⏰ Detecção: {close_time_str}\n"
                    report += f"------------------------------------------"

                    trade_data = {
                        "symbol": symbol,
                        "side": slot.get("side", "Unknown"),
                        "entry_price": float(slot.get("entry_price", 0)),
                        "exit_price": float(slot.get("entry_price", 0)),
                        "qty": float(slot.get("qty", 0)),
                        "order_id": f"paper_ghost_{symbol}_{int(slot.get('opened_at', 0))}",
                        "pnl": 0.0,
                        "slot_id": slot_id,
                        "slot_type": "PAPER_GHOST",
                        "close_reason": "PAPER_GHOST_PURGE",
                        "reasoning_report": report,
                        "closed_at": close_time_str
                    }

                    await firebase_service.hard_reset_slot(slot_id, reason="PAPER_GHOST_SLOT_PURGE_PERSISTENT", pnl=0.0, trade_data=trade_data)
                    await self.register_sniper_trade(trade_data)
                    self.ghost_tracker[slot_id] = 0
                    continue
                else:
                    # REAL MODE: Clear if truly stale
                    if norm_symbol not in exchange_map:
                        # [V110.19.3] GHOST-LOCK PROTECTION (REAL)
                        current_count = self.ghost_tracker.get(slot_id, 0) + 1
                        self.ghost_tracker[slot_id] = current_count
                        
                        lpm_data = self.active_slot_memory.get(slot_id, {})
                        lpm_symbol = lpm_data.get("symbol")
                        lpm_last_seen = lpm_data.get("last_seen", 0)
                        lpm_age = time.time() - lpm_last_seen if lpm_last_seen > 0 else 9999
                        
                        is_lpm_protected = (lpm_symbol == norm_symbol and lpm_age < 900)

                        # [V110.25.0] BOOT GRACE PERIOD: 600s
                        is_boot_grace = (time.time() - self.boot_time) < 600

                        # [V110.20.0] ABSOLUTE GHOST-LOCK: 50 ciclos de tolerância
                        if (current_count < 50 and is_lpm_protected) or is_boot_grace:
                            if current_count % 5 == 0 or is_boot_grace:
                                msg = f"👻 [GHOST-LOCK REAL] {symbol} missing."
                                if is_boot_grace: msg += " Protected by BOOT GRACE PERIOD (10m)."
                                else: msg += f" Protected by LPM (Age: {int(lpm_age)}s, Sync: {current_count}/50)."
                                logger.warning(msg)
                            continue
                            
                        logger.warning(f"🚨 [REAL-PURGE] Ghost Slot {slot_id} ({symbol}) missing from Bybit (Age: {int(lpm_age)}s). CLEARING.")
                        self.ghost_tracker[slot_id] = 0
                                       # V5.2.2: Register closed trade before clearing slot
                        try:
                            # [V43.2.3] Robust PnL Search: Wait for Bybit synchronization if necessary (Retries)
                            closed_list = []
                            for attempt in range(3):
                                closed_list = await okx_rest_service.get_closed_pnl(symbol=symbol, limit=5)
                                if closed_list:
                                    break
                                logger.info(f"Sync [REAL]: PnL for {symbol} not available yet (Attempt {attempt+1}/3). Waiting...")
                                await asyncio.sleep(3) # Wait for Bybit API to sync
                            
                            if closed_list:
                                last_pnl = closed_list[0]
                                pnl_val = float(last_pnl.get("closedPnl", 0))
                                exit_price = float(last_pnl.get("avgExitPrice", 0))
                                qty = float(last_pnl.get("qty", 0))
                                order_id = last_pnl.get("orderId", f"manual_{int(time.time())}")
                                
                                entry_price = float(slot.get("entry_price", 0))
                                current_stop = float(slot.get("current_stop", 0))
                                target_price = float(slot.get("target_price", 0))
                                side = slot.get("side", "Buy")
                                side_norm = (side or "").lower()
                                pensamento = slot.get("pensamento", "")
                                entry_margin = float(slot.get("entry_margin", 0))
                                leverage = float(slot.get("leverage", 50))
                                rescue_activated = slot.get("rescue_activated", False)
                                rescue_resolved = slot.get("rescue_resolved", False)
                                sentinel_retests = slot.get("sentinel_retests", 0)
                                score = slot.get("score", 0)
                                pattern = slot.get("pattern", "unknown")
                                structural_target = float(slot.get("structural_target", 0))
                                
                                # [V56.0] Unified Intelligence Persistence
                                unified_conf = slot.get("unified_confidence", 50)
                                fleet_intel = slot.get("fleet_intel", {})
                                
                                # [V36.1] Diagnostic: Determine REAL close reason
                                from services.time_utils import get_br_iso_str
                                close_time_str = get_br_iso_str()
                                diagnostic_reason = "EXCHANGE_SYNC_DETECTED"
                                
                                if exit_price > 0 and entry_price > 0:
                                    # Check if hit SL
                                    if current_stop > 0:
                                        sl_tolerance = entry_price * 0.001  # 0.1% tolerance
                                        if side_norm == "buy" and exit_price <= (current_stop + sl_tolerance):
                                            diagnostic_reason = f"STOP_LOSS_ATINGIDO_{sl_phase}"
                                        elif side_norm == "sell" and exit_price >= (current_stop - sl_tolerance):
                                            diagnostic_reason = f"STOP_LOSS_ATINGIDO_{sl_phase}"
                                    
                                    # Check if hit TP
                                    if target_price > 0:
                                        tp_tolerance = entry_price * 0.001
                                        if side_norm == "buy" and exit_price >= (target_price - tp_tolerance):
                                            diagnostic_reason = "TAKE_PROFIT_ATINGIDO"
                                        elif side_norm == "sell" and exit_price <= (target_price + tp_tolerance):
                                            diagnostic_reason = "TAKE_PROFIT_ATINGIDO"
                                
                                # [V36.1] Calculate ROI at closure
                                from services.execution_protocol import execution_protocol
                                final_roi = execution_protocol.calculate_roi(entry_price, exit_price, side) if entry_price > 0 else 0
                                sl_phase = execution_protocol.get_sl_phase(final_roi) if entry_price > 0 else "UNKNOWN"
                                
                                # [V36.1] Build reasoning report
                                pnl_percent = round((pnl_val / entry_margin) * 100, 2) if entry_margin > 0 else 0
                                outcome_icon = "🚀 WIN" if pnl_val >= 0 else "🛡️ LOSS"
                                
                                report = f"--- RELATÓRIO DE AUDITORIA V110.132 ---\n"
                                report += f"GENESIS ID: {order_id}\n"
                                report += f"SÍMBOLO: {symbol}\n"
                                report += f"DIREÇÃO: {'LONG' if side_norm == 'buy' else 'SHORT'}\n"
                                report += f"BATALHÃO: {get_slot_type(slot_id)} (Slot {slot_id})\n"
                                report += f"SCORE: {score} | PADRÃO: {pattern}\n"
                                report += f"\n📊 EXECUÇÃO:\n"
                                report += f"  Entrada: ${entry_price:.6f}\n"
                                report += f"  Saída:   ${exit_price:.6f}\n"
                                report += f"  Stop SL: ${current_stop:.6f}\n"
                                report += f"  Alvo TP: ${target_price:.6f}\n"
                                report += f"  Margem:  ${entry_margin:.2f} | Alavancagem: {leverage:.0f}x\n"
                                report += f"\n📈 RESULTADO:\n"
                                report += f"  {outcome_icon}\n"
                                report += f"  PnL: ${pnl_val:.2f} ({pnl_percent:.1f}%)\n"
                                report += f"  ROI Final: {final_roi:.1f}%\n"
                                report += f"  Fase Smart SL: {sl_phase}\n"
                                report += f"\n🔍 DIAGNÓSTICO:\n"
                                report += f"  Motivo: {diagnostic_reason}\n"
                                if rescue_activated:
                                    report += f"  🆘 Rescue Mode: ATIVADO"
                                    report += f" {'(Resolvido ✅)' if rescue_resolved else '(Pendente ⏳)'}\n"
                                if sentinel_retests > 0:
                                    report += f"  🛡️ Sentinel Retests: {sentinel_retests}/3\n"
                                if pensamento:
                                    report += f"\n💭 PENSAMENTO IA NA ABERTURA:\n"
                                    report += f"  {pensamento}\n"
                                
                                # [V56.0] Fleet Intelligence Section
                                report += f"\n⚓ INTELIGÊNCIA DE FROTA (V56.0):\n"
                                report += f"  Confiança Unificada: {unified_conf}%\n"
                                report += f"  - Macro: {fleet_intel.get('macro', 50)}%\n"
                                report += f"  - Whale: {fleet_intel.get('micro', 50)}%\n"
                                report += f"  - SMC: {fleet_intel.get('smc', 50)}%\n"
                                report += f"  - OnChain: {fleet_intel.get('onchain', 50)}%\n"
                                if fleet_intel.get('onchain_summary'):
                                    report += f"  💡 {fleet_intel.get('onchain_summary')}\n"
                                
                                report += f"\n⏰ Fechamento: {close_time_str}\n"
                                report += f"-----------------------------------"
                                
                                trade_data = {
                                    "symbol": symbol,
                                    "side": side,
                                    "entry_price": entry_price,
                                    "exit_price": exit_price,
                                    "qty": qty,
                                    "order_id": order_id, # V36.6 Idempotency
                                    "pnl": pnl_val,
                                    "slot_id": slot_id,
                                    "slot_type": get_slot_type(slot_id),
                                    "close_reason": diagnostic_reason,
                                    # [V36.1] Enriched fields
                                    "entry_margin": entry_margin,
                                    "leverage": leverage,
                                    "pnl_percent": pnl_percent,
                                    "close_time": close_time_str,
                                    "closed_at": close_time_str,
                                    "pensamento": pensamento,
                                    "reasoning_report": report,
                                    "final_roi": final_roi,
                                    "sl_phase_at_close": sl_phase,
                                    "current_stop_at_close": current_stop,
                                    "target_price_at_close": target_price,
                                    "score": score,
                                    "pattern": pattern,
                                    "rescue_activated": rescue_activated,
                                    "rescue_resolved": rescue_resolved,
                                    "sentinel_retests": sentinel_retests,
                                    # [V56.0] Persist Intelligence
                                    "unified_confidence": unified_conf,
                                    "fleet_intel": fleet_intel
                                }
                                
                                # 1. Register and Reset using Idempotent Hard Reset
                                # This prevents duplicate logs from concurrent loops (Guardian vs OKXRest)
                                success = await firebase_service.hard_reset_slot(
                                    slot_id=slot_id, 
                                    reason=diagnostic_reason, 
                                    pnl=pnl_val, 
                                    trade_data=trade_data
                                )
                                if success:
                                    logger.info(f"Sync [REAL]: Trade registered via Hard Reset for {symbol} | PnL: ${pnl_val:.2f}")
                                    await self.register_sniper_trade(trade_data)
                                else:
                                    logger.warning(f"Sync [REAL]: Skip duplicate registration for {symbol} (slot already cleared)")

                        except Exception as pnl_err:
                            logger.error(f"Sync [REAL]: Error during history sync for {symbol}: {pnl_err}")

            # 4. Import Missing Positions (Exchange has it, DB doesn't)
            # [V6.4] FIXED: Re-enable adoption even in PAPER mode. 
            # This allows orphan paper positions (reloaded from state) to be pushed to Firestore slots.
            
            # [V110.4] Busca Moonbags para evitar re-adotar trades emancipadas em slots táticos
            moonbags_list = await firebase_service.get_moonbags()
            moon_symbols = {okx_rest_service._strip_p(m.get("symbol") or "").upper() for m in moonbags_list}
            
            logger.info(f"🔍 [SYNC-S4] Checking {len(exchange_map)} exchange positions for import into {sum(1 for s in slots if not s.get('symbol'))} empty slots")
            for symbol, pos in exchange_map.items():
                # [V110.4] Se a trade já estiver nos slots OU no Vault (Moonbag), não importa novamente.
                if any(okx_rest_service._strip_p(s.get("symbol") or "").upper() == symbol for s in slots):
                    continue 
                
                if symbol in moon_symbols:
                    logger.debug(f"🛡️ [BYPASS] Position {symbol} is already in Moonbag Vault. Skipping re-adoption.")
                    continue

                # [V53.8] Blocklist Safety
                from services.signal_generator import signal_generator
                if symbol in getattr(signal_generator, 'asset_blocklist_permanent', set()):
                    logger.warning(f"Sync [RECOVERY]: Blocked symbol {symbol} found in exchange but NOT in slots. Skipping recovery.")
                    continue

                # [V110.25.7] STRICT VACANCY SHIELD
                # A slot is only eligible for recovery if it's EMPTY and NOT recently updated (Race Condition Guard)
                empty_slot = None
                for s in slots:
                    if s["id"] <= 4 and not s.get("symbol"):
                        # [V110.25.7] Shield: Has it been touched in the last 120s?
                        last_upd = s.get("timestamp_last_update") or 0
                        if (time.time() - last_upd) < 120:
                            logger.info(f"🛡️ [VACANCY-SHIELD] Slot {s['id']} empty but recently updated. Protected from orphan adoption.")
                            continue
                        
                        # Double-check against local memory (Atomic Guard)
                        if any(k[1] == s["id"] for k in self.pending_slots):
                            continue
                            
                        empty_slot = s
                        break
                
                if not empty_slot:
                    if any(s.get("symbol") for s in slots if s["id"] <= 4): # If there are occupied slots
                         logger.info(f"🔍 [SYNC-RECOVERY] No truly empty slots available for orphan {symbol}. Ignoring adoption.")
                    continue
                
                # [V110.100.3 DUAL-SYNC GUARD] Race Condition Prevention
                # Puxamos do Firebase ATUALIZADO momentos antes do commit
                fresh_slots = await firebase_service.get_active_slots(force_refresh=True)
                fresh_target = next((s for s in fresh_slots if s["id"] == empty_slot["id"]), None)
                if fresh_target and fresh_target.get("symbol"):
                    logger.warning(f"🚨 [RACE-CONDITION PREVENTED] Slot {empty_slot['id']} foi recém-tomado. Abortando duplicação de {symbol}.")
                    slots = fresh_slots # Atualiza a visão atual para o próximo symbol no loop
                    continue

                logger.info(f"Sync: Recovering {symbol} into Slot {empty_slot['id']}.")
                # V22.0: Auto-calculate target for recovered slots if missing
                entry_price = float(pos.get("avgPrice", 0))
                side = pos.get("side")
                target_p = float(pos.get("takeProfit", 0) or 0)
                if target_p <= 0:
                    tp_pct = 0.03 # [V34.0] All-SWING Transition (150% ROI target)
                    target_p = entry_price * (1 + tp_pct) if side == 'Buy' else entry_price * (1 - tp_pct)

                # Safe Margin Calc
                lev = 50
                pos_size = float(pos.get("size", 0))
                calc_margin = (pos_size * entry_price) / lev
                if calc_margin < 0.01: calc_margin = 1.0

                await firebase_service.update_slot(empty_slot["id"], {
                    "symbol": symbol,
                    "side": side,
                    "entry_price": entry_price,
                    "entry_margin": calc_margin,
                    "current_stop": float(pos.get("stopLoss", 0)),
                    "target_price": target_p, # V22.0: Added target_price persistence
                    "status_risco": "RECOVERED",
                    "slot_type": get_slot_type(empty_slot["id"]), # V5.4.5: Ensure correct logic type
                    "pnl_percent": (float(pos.get("unrealisedPnl", 0)) / calc_margin * 100) if calc_margin > 0 else 0,
                    "qty": float(pos.get("size", 0)),
                    "opened_at": time.time(), # Fallback for recovery
                    "liq_price": float(pos.get("liqPrice", 0)),
                    "timestamp_last_update": time.time()
                })
                # Refresh local list
                slots = await firebase_service.get_active_slots()

            await firebase_service.log_event("Bankroll", f"Sync Complete (V110.8). Active: {len(active_symbols)}", "SUCCESS")

        except Exception as e:
            logger.error(f"Error during slot sync: {e}")

    async def _get_total_unrealized_pnl(self):
        """[V110.8] Calculates unrealized PnL from ALL positions (slots + orphans)."""
        try:
            positions = await okx_rest_service.get_active_positions()
            total_unrealized = 0.0
            for pos in positions:
                total_unrealized += float(pos.get("unrealisedPnl", 0))
            return total_unrealized
        except Exception as e:
            logger.error(f"Error calculating total unrealized PnL: {e}")
            return 0.0


    async def calculate_real_risk(self):
        """
        [V10.4] Calculates the real risk for both Sniper slots.
        Risk = 20% per slot that is NOT Risk-Free.
        Max possible = 40% if both at risk (shouldn't happen with dual logic).
        """
        slots = await firebase_service.get_active_slots()
        real_risk = 0.0
        
        for slot in slots:
            if slot.get("symbol") and not self._is_slot_risk_free(slot):
                real_risk += self.margin_per_slot
        
        # Add pending risk if any
        if self.pending_slots:
            real_risk += self.margin_per_slot
        
        return min(real_risk, self.risk_cap)  # [V12.0] Cap at configured risk limit (e.g. 40%)

    async def get_specific_empty_slot(self, preferred_ids: List[int]) -> Optional[int]:
        """
        [V15.5] Finds an empty slot within a specific list of IDs.
        Used by the Captain to route SCALP/TREND signals to their dedicated slots.
        [V29.0] PAPER MODE FIX: Uses paper_positions to determine slot availability.
        """
        try:
            # [V29.0/V34.2] PAPER MODE FIX: Ensure we check Firestore first
            slots = await firebase_service.get_active_slots()
            
            if okx_rest_service.execution_mode == "PAPER":
                paper_positions = okx_rest_service.paper_positions
                # First, ensure we don't exceed 4 slots TOTAL
                if len(paper_positions) >= 4:
                    return None
                    
                # Iterate through preferred IDs and check BOTH Firestore AND local memory
                used_paper_symbols = {p.get("symbol", "").upper() for p in paper_positions}
                for s_id in preferred_ids:
                    slot = next((s for s in slots if s["id"] == s_id), None)
                    slot_symbol = (slot.get("symbol") or "").upper() if slot else ""
                    
                    # Slot is empty if it has no symbol in Firestore AND no symbol in memory matches it
                    if not slot_symbol:
                        # Check local pending lock
                        if not any(k[1] == s_id for k in self.pending_slots):
                            return s_id
                return None
            
            # REAL MODE: Original Firestore check
            slots = await firebase_service.get_active_slots(force_refresh=True)
            for s_id in preferred_ids:
                slot = next((s for s in slots if s["id"] == s_id), None)
                if slot and not slot.get("symbol"):
                    # Check local pending lock
                    if not any(k[1] == s_id for k in self.pending_slots):
                        return s_id
            return None
        except Exception as e:
            logger.error(f"Error in get_specific_empty_slot: {e}")
            return None

    async def can_open_new_slot(self, symbol: str = None, slot_type: str = "SNIPER") -> Optional[int]:
        """
        [V11.0] QUAD CONCURRENT RULE (Expanded from Dual):
        - Slots 1, 2, 3, 4: Available if empty (10% Margin each)
        All 4 can be active at the same time.
        [V29.0] PAPER MODE FIX: In PAPER mode, count occupied slots from local
        paper_positions (memory) instead of Firestore, because production Cloud Run
        constantly overwrites Firestore with real exchange positions.
        """
        try:
            # Atomic Lock Check & TTL Expiry
            current_time = time.time()
            expired_keys = [k for k, ts in self.pending_slots.items() if (current_time - ts) > 15] # [V86.4] 15s lock for faster PAPER reactivity
            for k in expired_keys:
                logger.warning(f"🔓 Atomic Lock TTL (45s) Expired for {k}. Clearing.")
                del self.pending_slots[k]
                
            if symbol:
                norm_symbol = (okx_rest_service._strip_p(symbol) or "").upper()
                if any(k[0] == norm_symbol for k in self.pending_slots):
                    logger.warning(f"🛡️ [SYMBOL LOCK] {symbol} already being processed. BLOCKED.")
                    return None
            
            # [V92.0] DECENTRALIZED: Global lock removed. Multiple symbols can claim slots in parallel.

            # [V43.2] Pre-fetch slots for Risk-Free check (Ancorado na SSOT Postgres)
            from services.database_service import database_service
            slots = await database_service.get_active_slots()
            # Postgres is the tactical slot SSOT in both REAL and PAPER. In PAPER,
            # paper_positions can temporarily hold stale/emancipated positions, so
            # it must not decide whether the four tactical slots are full.
            active_slots_data = [
                s for s in slots
                if s.get("symbol")
                and s.get("status") != "EMANCIPATED"
                and s.get("status_risco") != "EMANCIPATED"
            ]

            at_risk_count = 0
            for s in active_slots_data:
                if not s.get("symbol"): continue
                
                # [V6.0] Garantia de Lucro: Só libera se SL travado em +60% ROI (reduzido de 80% para melhor preenchimento)
                roi_at_sl = 0
                leverage = float(s.get("leverage", 50))
                entry = float(s.get("entry_price", 0))
                stop = float(s.get("current_stop", 0))
                side = s.get("side", "Buy")

                if entry > 0 and stop > 0:
                    if side.lower() == "buy":
                        roi_at_sl = ((stop - entry) / entry) * leverage * 100
                    else:
                        roi_at_sl = ((entry - stop) / entry) * leverage * 100

                # Regra Nova: Profit-Guaranteed (stop >= 60% ROI) - Reduzido para melhor aproveitamento de slots
                is_profit_guaranteed = roi_at_sl >= 60.0

                if not is_profit_guaranteed:
                    at_risk_count += 1
                    logger.info(f"🛡️ [V6.0] {s.get('symbol')} em andamento (ROI no SL: {roi_at_sl:.1f}%). Aguardando garantia de 60% para próxima Tocaia.")
                else:
                    logger.info(f"✅ [V6.0] {s.get('symbol')} com lucro garantido ({roi_at_sl:.1f}%). Slot liberado para nova Tocaia.")

            # [V43.1] Bankroll Recovery: Limit to 1 slot if balance < $15
            # AND respect the '1-at-risk' rule.
            balance = await self.get_live_operating_equity()
            
            # [V110.0] ZERO EQUITY SHIELD: Stop if balance is too low (Effective Zero)
            if balance < 2.0:
                logger.warning(f"🚫 [ZERO EQUITY] LiveEquity ${balance:.2f} is critically low. Blocked all new openings.")
                await firebase_service.log_event("Bankroll", f"🛑 CRITICAL: Zero Equity Shield Active (${balance:.2f}). System Paused.", "CRITICAL")
                return None

            # [V111.0] ULTRA-DIVERSIFICATION: slots e margem dinâmicos por regime de mercado
            # O regime é determinado pelo campo market_regime do slot_type ou pelo sinal
            is_ranging_mode = slot_type in ("DECOR_HUNTER", "RANGING") or (
                not slot_type or slot_type.upper() not in ("ELITE_40_MATRIX", "TRENDING", "BLITZ_30M", "BLITZ")
            )
            if self.strict_single_order_mode:
                max_total_slots = 1
                max_at_risk_slots = 1
            elif balance < 10.0:
                max_total_slots = 2  # [V110.802.6] Banca crítica: máx 2 slots
                max_at_risk_slots = 2
                logger.info(f"🛡️ [V110.802.6] Low Balance Mode: Max Slots=2 | LiveEquity=${balance:.2f}")
            elif is_ranging_mode:
                max_total_slots = self.max_slots_lateral   # 20 pares — DECOR_HUNTER
                max_at_risk_slots = self.max_slots_lateral
                logger.info(f"🛡️ [V111.0] DECOR_HUNTER Mode: Max Slots={max_total_slots} | Margin=$2.00/par | LiveEquity=${balance:.2f}")
            else:
                max_total_slots = self.max_slots_trending  # 40 pares — ELITE_40_MATRIX
                max_at_risk_slots = self.max_slots_trending
                logger.info(f"🛡️ [V111.0] ELITE_40_MATRIX Mode: Max Slots={max_total_slots} | Margin=$1.00/par | LiveEquity=${balance:.2f}")

            # [V125] Desativado bloqueio por posições sem stop para permitir preenchimento em escala de até 40 slots
            # if at_risk_count >= max_at_risk_slots:
            #     logger.warning(f"🚫 [V43.2] Dual-Slot BLOCK: At least {at_risk_count} position(s) unprotected. Waiting for Risk-Zero.")
            #     return None
            pass

            # [V29.0] PAPER MODE: Use local paper positions as source of truth
            if okx_rest_service.execution_mode == "PAPER":
                paper_positions = okx_rest_service.paper_positions
                moonbags_data = await database_service.get_moonbags()
                moon_symbols = {
                    (okx_rest_service._strip_p(m.get("symbol") or "") or "").upper()
                    for m in moonbags_data
                    if m.get("symbol")
                }

                active_slot_symbols = {
                    (okx_rest_service._strip_p(s.get("symbol") or "") or "").upper()
                    for s in slots
                    if s.get("symbol")
                    and s.get("status") != "EMANCIPATED"
                    and s.get("status_risco") != "EMANCIPATED"
                }
                active_slot_ids = {
                    int(s.get("id"))
                    for s in slots
                    if s.get("id") in [1, 2, 3, 4]
                    and s.get("symbol")
                    and float(s.get("qty", 0) or 0) > 0
                    and float(s.get("entry_price", 0) or 0) > 0
                    and s.get("status") != "EMANCIPATED"
                    and s.get("status_risco") != "EMANCIPATED"
                }
                stale_memory_symbols = []
                tactical_paper_positions = []
                for p in paper_positions:
                    p_symbol = (okx_rest_service._strip_p(p.get("symbol") or "") or "").upper()
                    if not p_symbol:
                        continue
                    if p.get("status") == "EMANCIPATED" or p.get("status_risco") == "EMANCIPATED":
                        stale_memory_symbols.append(p_symbol)
                        continue
                    if p_symbol in moon_symbols:
                        stale_memory_symbols.append(p_symbol)
                        continue
                    if p_symbol in active_slot_symbols:
                        tactical_paper_positions.append(p)
                    else:
                        stale_memory_symbols.append(p_symbol)
                
                # [V29.1] HYBRID OCCUPIED COUNT: Anti-Flap Shield
                # Prevent memory drift from making empty Postgres slots look full.
                occupied_count = len(active_slot_ids)
                if stale_memory_symbols:
                    log_key = "paper_slot_memory_reconcile"
                    now_log = time.time()
                    if now_log - self.last_log_times.get(log_key, 0) > 30:
                        logger.warning(
                            "[PAPER-SLOT-RECONCILE] Ignoring %s stale paper position(s) for capacity: %s | db_active_slots=%s/%s",
                            len(stale_memory_symbols),
                            sorted(set(stale_memory_symbols))[:8],
                            occupied_count,
                            max_total_slots,
                        )
                        self.last_log_times[log_key] = now_log
                
                # Check if symbol is already pending or active
                if symbol:
                    norm_symbol = (okx_rest_service._strip_p(symbol) or "").upper()
                    if any(k[0] == norm_symbol for k in self.pending_slots):
                        return None
                    # Check if symbol already belongs to an active tactical paper slot.
                    for p in tactical_paper_positions:
                        if (p.get("symbol") or "").upper().replace(".P", "") == norm_symbol:
                            return None
                    # [V53.4] DEEP DUPLICATE CHECK: Also check Firestore slots before re-adoption
                    for s in slots:
                        s_sym = (s.get("symbol") or "").upper().replace(".P", "")
                        if s_sym == norm_symbol:
                            logger.warning(f"🛡️ [V53.4] Deep Lock: Symbol {symbol} already in Firestore Slot {s.get('id')}. BLOCKED.")
                            return None
                    
                    # [V58.0] Inertia Shield
                    now = time.time()
                    if norm_symbol in self.recent_openings:
                        if now - self.recent_openings[norm_symbol] < 120:
                            logger.warning(f"🛡️ [V58.0] Inertia Shield: {symbol} was opened very recently. Blocking double fire.")
                            return None
                        else:
                            del self.recent_openings[norm_symbol]
                
                if occupied_count >= max_total_slots:
                    logger.info(f"🚫 V29.0 [PAPER]: {occupied_count}/{max_total_slots} paper positions ativas.")
                    return None
                
                # [V111.0] PAPER: Ignite ANY available slot dynamically (up to max_total_slots)
                # Slots are dynamic — find the first free ID (not in current active set)
                active_ids = {int(s.get("id")) for s in slots if s.get("symbol") and s.get("status_risco") != "EMANCIPATED"}
                pending_ids = {k[1] for k in self.pending_slots}
                for i in range(1, max_total_slots + 1):
                    if i not in active_ids and i not in pending_ids:
                        logger.info(f"💎 [PAPER-TEST-FIRE] Forçando Slot {i} disponivel para {slot_type} (max={max_total_slots}).")
                        return i

                logger.info(f"[PAPER] Todos os {max_total_slots} slots disponíveis ocupados.")
                return None
            
            # REAL MODE: Dynamic slot logic (V111.0)
            # slots already pre-fetched at the top
            # Suporte dinâmico de 1 a max_total_slots (até 40)
            slot_map = {s["id"]: s for s in slots}
            
            # Check if this symbol is already pending
            if symbol:
                norm_symbol = (okx_rest_service._strip_p(symbol) or "").upper()
                if any(k[0] == norm_symbol for k in self.pending_slots):
                    return None
                # [V110.25.6] STRICT SYMBOL NORMALIZATION
                from services.agents.captain import normalize_symbol
                norm_symbol = normalize_symbol(symbol)
                
                # Also check if symbol already in an active slot (Strict)
                for s in slots:
                    s_sym = normalize_symbol(s.get("symbol"))
                    if s_sym == norm_symbol:
                        logger.warning(f"🛡️ [SYMBOL-LOCK] {symbol} already active in Slot {s.get('id')}. Aborting.")
                        return None
                
                # [V58.0] Inertia Shield
                now = time.time()
                if norm_symbol in self.recent_openings:
                    if now - self.recent_openings[norm_symbol] < 120:
                        logger.warning(f"🛡️ [V58.0] Inertia Shield (REAL): {symbol} opened recently. Blocking.")
                        return None
                    else:
                        del self.recent_openings[norm_symbol]

            # [V110.8] Anti-Orphan Exchange Guard
            # Se já temos 4 ordens na Bybit/Simulação, BLOQUEIA mesmo que o Firebase diga que há slots vazios.
            live_positions = await okx_rest_service.get_active_positions()
            
            # [V110.178] Moonbag Exclusion: Ignore positions that are registered as Moonbags in the database
            moonbags_data = await firebase_service.get_moonbags()
            moon_symbols = {m.get("symbol", "").replace(".P", "").upper() for m in moonbags_data}
            tactical_positions = [p for p in live_positions if p.get("symbol", "").replace(".P", "").upper() not in moon_symbols]
            
            if len(tactical_positions) >= max_total_slots:
                logger.warning(f"🚫 [EXCHANGE GUARD] Já existem {len(tactical_positions)} ordens táticas ativas na Bybit. Bloqueando abertura de {symbol} para evitar órfãos.")
                return None

            # [V12.0] Total Limit Check: Expanded to 4
            # [V110.0] Ignora slots emancipados no limite de capacidade (Real Mode)
            occupied_count = sum(1 for s in slots if s.get("symbol") and float(s.get("qty", 0)) > 0 and float(s.get("entry_price", 0)) > 0 and s.get("status") != "EMANCIPATED")
            if occupied_count >= max_total_slots:
                logger.info(f"🚫 V110.0: Limite de {max_total_slots} trades táticos atingido ({occupied_count}). Moonbags não contam.")
                return None

            # [V111.0] REAL: Ignite ANY available slot dynamically (up to max_total_slots)
            active_ids = {int(s["id"]) for s in slots if s.get("symbol") and float(s.get("qty", 0)) > 0 and s.get("status") != "EMANCIPATED"}
            pending_ids = {k[1] for k in self.pending_slots}
            for i in range(1, max_total_slots + 1):
                if i not in active_ids and i not in pending_ids:
                    logger.info(f"💎 [REAL-TEST-FIRE] Forçando Slot {i} disponível para {slot_type} (max={max_total_slots}).")
                    return i

            logger.info(f"[REAL] Todos os {max_total_slots} slots disponíveis ocupados.")
            return None
        
        except Exception as e:
            logger.error(f"Error checking slot availability: {e}")
            return None

    async def update_banca_status(self):
        """Updates the banca_status table in Supabase."""
        try:
            real_risk = await self.calculate_real_risk()
            slots = await firebase_service.get_active_slots()
            available_slots_count = sum(1 for s in slots if s["symbol"] is None)
            
            # Fetch real balance from Bybit - NON-BLOCKING
            total_equity = await okx_rest_service.get_wallet_balance()
            
            banca = await firebase_service.get_banca_status()
            if banca:
                # V5.2.2: Calculate Cumulative Profit from All Trades
                trades = await firebase_service.get_trade_history(limit=1000)
                
                # [V3.0 Hardended PnL Calculation]
                total_pnl = 0.0
                valid_trades_count = 0
                for t in trades:
                    pnl_raw = t.get("pnl", 0)
                    try:
                        pnl_val = float(pnl_raw)
                        # Filter outliers but keep real performance (up to $5000 per trade)
                        if abs(pnl_val) < 5000:
                            total_pnl += pnl_val
                            valid_trades_count += 1
                    except (ValueError, TypeError):
                        continue
                
                logger.info(f"📊 Banca Update: Calculated Total PnL = ${total_pnl:.2f} from {valid_trades_count} trades.")
                
                # [V5.2.5] Fetch cycle-specific data from Vault Service
                vault_status = await vault_service.get_cycle_status()
                cycle_profit = vault_status.get("cycle_profit", 0)
                vault_total = vault_status.get("vault_total", 0)
                
                # [V8.1] Preserve configured_balance if set by user
                config_bal = banca.get("configured_balance")
                if okx_rest_service.execution_mode == "PAPER":
                    config_bal = settings.OKX_SIMULATED_BALANCE
                    banca["configured_balance"] = settings.OKX_SIMULATED_BALANCE
                
                # [V110.9] Calculations logic for PAPER and REAL parity
                if okx_rest_service.execution_mode == "PAPER":
                    # Paper equity follows the Guardian/Postgres source of truth.
                    base_balance = float(settings.OKX_SIMULATED_BALANCE)
                    active_slots = await database_service.get_active_slots()
                    active_moonbags = await database_service.get_moonbags()
                    paper_snapshot = self._paper_equity_snapshot(
                        base_balance=base_balance,
                        realized_pnl=total_pnl,
                        active_slots=active_slots,
                        active_moonbags=active_moonbags,
                    )
                    float_pnl = paper_snapshot["float_pnl"]
                    
                    db_balance = base_balance
                    # Keep sizing anchored to the configured paper bankroll.
                    if abs(okx_rest_service.paper_balance - db_balance) > 0.01:
                        logger.info(f"🔄 Syncing okx_rest_service.paper_balance ({okx_rest_service.paper_balance}) to paper base ({db_balance})")
                        okx_rest_service.paper_balance = db_balance
                    calculated_equity = paper_snapshot["calculated_equity"]
                    reported_real_okx = 0.0
                    logger.info(
                        "📊 [PAPER BALANCE] "
                        f"BaseOperacional={base_balance:.2f} | "
                        f"Realized={total_pnl:.2f} | "
                        f"Slots={paper_snapshot['open_slots_pnl']:.2f} | "
                        f"Moonbags={paper_snapshot['open_moonbags_pnl']:.2f} | "
                        f"EquityVivo={calculated_equity:.2f}"
                    )



                else:
                    # REAL MODE: Bybit/OKX is the source of truth for Equity.
                    # Mas se a API retornar apenas o saldo estático ou precisarmos garantir que os lucros e prejuízos
                    # flutuantes das 4 ordens e moonbags sejam somados à banca:
                    float_pnl = 0.0
                    try:
                        # Pega o PnL não realizado real de todas as posições abertas na corretora
                        real_positions = await okx_rest_service.get_active_positions()
                        for p in real_positions:
                            raw_float = p.get("unrealisedPnl", 0)
                            if raw_float:
                                float_pnl += float(raw_float)
                    except Exception as e:
                        logger.error(f"Error summing real float_pnl: {e}")
                    
                    if total_equity > 0:
                        # Se total_equity já é o Equity líquido total (totalEq) que inclui PnL flutuante na OKX, usamos ele.
                        # Mas se for saldo estático de margem livre, somamos o float_pnl. 
                        # Para garantir segurança e não duplicar, na OKX totalEq já inclui UPL.
                        # No entanto, se o usuário relata números errados ou loucos na banca, 
                        # garantimos que calculated_equity seja exatamente total_equity.
                        calculated_equity = total_equity
                        reported_real_okx = total_equity
                    else:
                        # Fallback if API fails
                        calculated_equity = (config_bal or 100.0) + total_pnl + float_pnl
                        reported_real_okx = 0.0


                update_data = {
                    "id": banca.get("id", "status"),
                    "saldo_real_okx": reported_real_okx,
                    "risco_real_percent": real_risk,
                    "slots_disponiveis": available_slots_count,
                    "lucro_total_acumulado": total_pnl,
                    "lucro_ciclo": cycle_profit,
                    "vault_total": vault_total,
                    "leverage": banca.get("leverage", settings.LEVERAGE),
                    "configured_balance": settings.OKX_SIMULATED_BALANCE if okx_rest_service.execution_mode == "PAPER" else config_bal,
                    "saldo_total": settings.OKX_SIMULATED_BALANCE if okx_rest_service.execution_mode == "PAPER" else calculated_equity,
                    "calculated_equity": calculated_equity,
                    "paper_equity": calculated_equity if okx_rest_service.execution_mode == "PAPER" else None,
                    "paper_float_pnl": float_pnl if okx_rest_service.execution_mode == "PAPER" else None,
                }
                await firebase_service.update_banca_status(update_data)
                
                # [V3.0 Refinement] Explicitly log sync success for user verification
                if firebase_service.rtdb:
                    if okx_rest_service.execution_mode == "PAPER":
                        logger.info(
                            f"🛰️ RTDB SYNC SUCCESS: PaperEquity=${calculated_equity:.2f} | "
                            f"BaseOperacional=${settings.OKX_SIMULATED_BALANCE:.2f} | "
                            f"Accumulated Profit=${total_pnl:.2f}"
                        )
                    else:
                        logger.info(f"🛰️ RTDB SYNC SUCCESS: Banca Total=${calculated_equity:.2f} | Accumulated Profit=${total_pnl:.2f}")
                else:
                    logger.warning("🛰️ RTDB SYNC SKIPPED: RTDB not connected.")
                
                # Snapshot logging: Log once every 6 hours (approx)
                if not hasattr(self, "_last_snapshot_time"):
                    self._last_snapshot_time = 0
                
                current_time = time.time()
                if (current_time - self._last_snapshot_time) > (6 * 3600): # 6 hours
                    await firebase_service.log_banca_snapshot({
                         "saldo_total": total_equity,
                         "risco_real_percent": real_risk,
                         "avail_slots": available_slots_count
                    })
                    self._last_snapshot_time = current_time
                    logger.info("Bankroll snapshot logged to history.")

        except Exception as e:
            logger.error(f"Error updating banca status: {e}")

    async def _calculate_target_margin(self, balance: float, current_leverage: float, dna_margin_pct: float = 0.10) -> float:
        """
        [V110.113] Calcula margem alvo baseada no DNA do ativo.
        
        [V110.3] User Rule: Ordens abertas com % da banca conforme volatilidade:
        - STABLE: 12% da banca (ativos seguros, mais exposição)
        - VOLATILE: 10% da banca (equilíbrio)
        - EXTREME: 8% da banca (ativos voláteis, menos risco)
        
        Se a banca é 100 e DNA=STABLE, vai com 12. Se banca é 40 e DNA=EXTREME, vai com 3.20.
        """
        margin = round(balance * dna_margin_pct, 2)
        if margin < 1.0: margin = 1.0

        logger.info(f"🎯 [V110.113] {dna_margin_pct*100:.0f}% DNA Margin: ${margin:.2f} (Based on UI Balance: ${balance:.2f})")
        return margin

    async def open_position(self, symbol: str, side: str, sl_price: float = 0, tp_price: float = None, pensamento: str = "", slot_type: str = "SNIPER", signal_data: dict = None, target_slot_id: int = None):
        """[V21.0] Executes Sniper entry with structural target-based TP. Accepts target_slot_id from Captain routing."""
        async with self.execution_lock:
            try:
                # 1. Total Awareness: Check availability & local lock
                norm_symbol = (okx_rest_service._strip_p(symbol) or "").upper()
                
                # 1.1 Duplicate Guard (Firebase + Memory + Real Exchange)
                
                # [V25.0] Anti-Zombie Re-Entry Cooldown
                if self.is_recently_closed(norm_symbol):
                    logger.warning(f"Iron Lock: Signal {symbol} is in cooldown (recently closed). BLOCKED.")
                    return None

                from services.database_service import database_service
                active_slots = await database_service.get_active_slots()
                if any(okx_rest_service._strip_p(S.get("symbol") or "").upper() == norm_symbol for S in active_slots):
                    logger.warning(f"Iron Lock: Signal {symbol} already active in Postgres (SSOT). BLOCKED.")
                    return None
                
                if any(k[0] == norm_symbol for k in self.pending_slots):
                     logger.warning(f"Iron Lock: Signal {symbol} already pending in memory. BLOCKED.")
                     return None

                # [V60.0] The Ultimate Duplicate Guard (Exigência Direta do Usuário)
                # Verifica DIRETAMENTE na exchange/simulação se a ordem já existe antes de enviar a nova.
                live_positions = await okx_rest_service.get_active_positions(symbol=symbol)
                if live_positions:
                    logger.warning(f"Iron Lock: {symbol} JÁ ESTÁ ABERTO na Exchange/Paper! Varredura bloqueou duplicata absoluta.")
                    return None

                # 1.2 Vault & Risk Guard
                trading_allowed, reason = await vault_service.is_trading_allowed()
                if not trading_allowed:
                    msg = f"Trading Blocked: {reason}"
                    logger.warning(msg)
                    await firebase_service.log_event("VAULT", msg, "WARNING")
                    return None
                
                # [V6.3] ALWAYS check availability inside the lock, even if Captain routed a slot.
                # This prevents race conditions where two signals pass the early check concurrently.
                slot_id = await self.can_open_new_slot(symbol=symbol, slot_type=slot_type)
                
                if not slot_id:
                    logger.warning(f"Risk Cap (Atomic): No slots available for {symbol} ({slot_type}). Blocked by Strict Single Order rule.")
                    return None
                
                # If Captain suggested a slot but it's different from what we found, we use the found one to be safe
                if target_slot_id and target_slot_id != slot_id:
                     logger.info(f"🛡️ [V6.3] Slot Routing Override: Requested {target_slot_id}, but providing {slot_id} for safety.")
                
                # [V15.0] BANKROLL GUARDIAN ATOMIC CHECK (Double Shield)
                try:
                    from services.agents.bankroll_guardian import bankroll_guardian
                    sig_payload = signal_data or {"symbol": symbol, "score": 90}
                    guardian_decision = await bankroll_guardian.authorize_new_trade(sig_payload)
                    
                    if not guardian_decision.get("approved", False):
                        reason = " | ".join(guardian_decision.get("reasons", []))
                        logger.warning(f"[BANKROLL-GUARDIAN-ATOMIC] {symbol} negado dentro do lock: {reason}")
                        await firebase_service.log_event(
                            "GUARDIAO_BANCA",
                            f"Entrada atômica negada em {symbol}: {reason}",
                            "WARNING"
                        )
                        return None
                except Exception as bge:
                    logger.error(f"[BANKROLL-GUARDIAN-ATOMIC] Falha na validação interna para {symbol}: {bge}")
                
                # [V110.181] ATOMIC SLOT INTEGRITY TRAVA (Anticolisão de Slot)
                check_slot = next((s for s in active_slots if s.get("id") == slot_id), None)
                if check_slot:
                    exist_sym = check_slot.get("symbol")
                    exist_qty = float(check_slot.get("qty", 0))
                    exist_entry = float(check_slot.get("entry_price", 0))
                    if exist_sym and exist_sym.upper().replace(".P","") != norm_symbol.replace(".P","") and exist_qty > 0 and exist_entry > 0:
                        logger.error(f"❌ [SLOT-COLLISION-TRAVA] Bloqueando colisão destrutiva! Tentativa de abrir {symbol} no Slot {slot_id}, mas ele já está ocupado por {exist_sym} (@ ${exist_entry}, Qty: {exist_qty}) no Postgres físico.")
                        return None

                # 1.3 Atomic Lock: Claim the slot in memory before any network calls
                self.pending_slots[(norm_symbol, slot_id)] = time.time()
                
                # [V58.1] PRE-EMPTIVE INERTIA SHIELD (Memory)
                # We record the opening attempt BEFORE the network calls (place_atomic_order)
                # to close the 9s race condition window where Signal B could pass the check.
                self.recent_openings[norm_symbol] = time.time()
                
                # [V60.0] THE IRON DOME (Persistent Database Cooldown)
                # Escreve imediatamente um bloqueio firme e global no Firebase para essa moeda por 120s.
                # Qualquer restart, re-processamento ou atraso gigantesco no Bybit não deixará o Capitão entrar duplicado.
                await firebase_service.register_sl_cooldown(symbol, 120)
                
                logger.info(f"Iron Lock: Claimed Slot {slot_id} for {symbol}. Proceeding with execution...")

            except Exception as e:
                logger.error(f"Error during slot claiming: {e}")
                return None

            try:
                # 2. Fetch Market Data & Calculate Order
                ticker = await okx_rest_service.get_tickers(symbol=symbol)
                ticker_list = ticker.get("result", {}).get("list", [])
                if not ticker_list:
                    logger.error(f"Could not fetch exact price for {symbol} (Match Failed)")
                    return None
            
                current_price = float(ticker_list[0].get("lastPrice", 0))
                
                if current_price == 0:
                    logger.error(f"Could not fetch price for {symbol}")
                    return None

                info = await okx_rest_service.get_instrument_info(symbol)
                if not info:
                    logger.error(f"Could not fetch instrument info for {symbol}")
                    return None
            except Exception as e:
                logger.error(f"Error fetching market data for {symbol}: {e}")
                return None
            
            try:
                # [V110.113] DNA-BASED LEVERAGE & MARGIN SIZING
                # Ajusta alavancagem e margem conforme volatilidade do ativo (Librarian DNA)
                # - EXTREME: 30x, 8% margem (menos exposição em ativos voláteis)
                # - VOLATILE: 40x, 10% margem (equilíbrio)
                # - STABLE: 50x, 12% margem (mais alavancagem em ativos estáveis)
                
                from services.agents.librarian import librarian_agent
                lib_dna = await librarian_agent.get_asset_dna(symbol)
                vol_class = lib_dna.get("volatility_class", "STABLE")
                
                dna_leverage_map = {
                    "EXTREME": 30.0,
                    "VOLATILE": 40.0,
                    "STABLE": 50.0
                }
                dna_margin_map = {
                    "EXTREME": 0.08,   # 8%
                    "VOLATILE": 0.10,  # 10%
                    "STABLE": 0.12     # 12%
                }
                
                # [V110.135] QUARTERMASTER OVERRIDE
                qm_leverage = float(signal_data.get("leverage", 0)) if signal_data else 0
                qm_multiplier = float(signal_data.get("margin_multiplier", 1.0)) if signal_data else 1.0
                
                if qm_leverage > 0:
                    current_leverage = qm_leverage
                    dna_margin_pct = 0.10 * qm_multiplier 
                    logger.info(f"⚓ [V110.135 QUARTERMASTER-OVERRIDE] {symbol} Leverage={current_leverage}x, Adjusted-Margin={dna_margin_pct*100:.1f}%")
                else:
                    dna_leverage = dna_leverage_map.get(vol_class, 50.0)
                    dna_margin_pct = dna_margin_map.get(vol_class, 0.10)
                    max_lev = float(info.get("leverageFilter", {}).get("maxLeverage", 50))
                    current_leverage = min(dna_leverage, max_lev)
                    logger.info(
                        f"🧬 [V110.113 DNA-SIZE] {symbol} Vol={vol_class} | "
                        f"Leverage={current_leverage}x, Margin={dna_margin_pct*100:.0f}%"
                    )

                balance = await self._get_operating_balance()
                margin = round(balance * 0.10, 2)
                
                # Garante um mínimo operacional de $1.00 para não quebrar em ordens de banca extremamente reduzida
                if margin < 1.0:
                    margin = 1.0
                
                # Calibração de leverage
                if settings.OKX_API_KEY_MASTER:
                    current_leverage = 50.0
                else:
                    from services.agents.librarian import librarian_agent
                    lib_dna = await librarian_agent.get_asset_dna(symbol)
                    vol_class = lib_dna.get("volatility_class", "STABLE")
                    dna_leverage_map = {"EXTREME": 30.0, "VOLATILE": 40.0, "STABLE": 50.0}
                    qm_leverage = float(signal_data.get("leverage", 0)) if signal_data else 0
                    current_leverage = qm_leverage if qm_leverage > 0 else dna_leverage_map.get(vol_class, 50.0)
                    
                logger.info(f"💰 [MARGEM ATÔMICA 10%] Calibrado para exatamente ${margin:.2f} (Banca: ${balance:.2f}) com {current_leverage}x alavancagem.")
                
                qty_step = float(info.get("lotSizeFilter", {}).get("qtyStep", 0.001))
                
                if balance < 1:
                    logger.warning(f"❌ BANKROLL BELOW MINIMUM ($1): ${balance:.2f}. Blocked.")
                    return None

                cycle_status = await vault_service.get_cycle_status()
                cycle_bankroll = cycle_status.get("cycle_start_bankroll", 0)
                if cycle_bankroll < 5:
                    # First trade of cycle: initialize cycle bankroll (apenas histórico)
                    await vault_service.initialize_cycle_bankroll(balance)
                
                if margin < 1.0:
                    # [V42.0] Force minimum operational margin if balance allows
                    if balance >= 1.0:
                        margin = 1.0
                    else:
                        logger.warning(f"❌ Balance extremely low (${balance:.2f}). Cannot even afford $1 margin.")
                        return None
                
                # [V42.0] QUANTITY CALCULATION (Critical Fix for OKX Contracts)
                # OKX requires size in CONTRACTS. 
                # Contracts = (margin * leverage) / (price * ctVal)
                ct_val = float(info.get("lotSizeFilter", {}).get("ctVal", 1.0))
                if ct_val <= 0:
                    ct_val = 1.0
                
                raw_qty = (margin * current_leverage) / (current_price * ct_val)
                qty = float(math.floor(raw_qty / qty_step) * qty_step)
                
                if qty <= 0:
                    logger.warning(f"❌ Calculated quantity is zero for {symbol} (Margin Too Small for price/step). Raw qty was {raw_qty}, ctVal={ct_val}, qty_step={qty_step}")
                    return None
                
                # [V110.833] EXECUTION CAPACITY GATE: validate live book capacity before order placement.
                actual_margin_usd = (qty * current_price * ct_val) / current_leverage
                from services.execution_capacity import execution_capacity_gate

                capacity_report = await execution_capacity_gate.evaluate_order_capacity(
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    entry_price=current_price,
                    leverage=current_leverage,
                    ct_val=ct_val,
                    margin_usd=actual_margin_usd,
                    execution_mode=getattr(okx_rest_service, "execution_mode", settings.OKX_EXECUTION_MODE),
                )
                capacity_metrics = capacity_report.get("metrics", {})
                fill_ratio_pct = (capacity_metrics.get("fill_ratio") or 0.0) * 100.0
                spread_metric = capacity_metrics.get("spread_bps")
                slippage_metric = capacity_metrics.get("slippage_bps")
                usage_metric = capacity_metrics.get("book_usage_pct")
                capacity_log = (
                    f"[EXEC-CAPACITY-GATE] {symbol} {side} qty={qty} "
                    f"notional=${capacity_metrics.get('notional_usd', 0.0):.2f} "
                    f"spread={spread_metric:.2f}bps "
                    if isinstance(spread_metric, (int, float))
                    else (
                        f"[EXEC-CAPACITY-GATE] {symbol} {side} qty={qty} "
                        f"notional=${capacity_metrics.get('notional_usd', 0.0):.2f} spread=n/a "
                    )
                )
                capacity_log += (
                    f"slippage={slippage_metric:.2f}bps "
                    if isinstance(slippage_metric, (int, float))
                    else "slippage=n/a "
                )
                capacity_log += (
                    f"book_use={usage_metric:.2f}% "
                    if isinstance(usage_metric, (int, float))
                    else "book_use=n/a "
                )
                capacity_log += (
                    f"fill={fill_ratio_pct:.1f}% "
                    f"max_safe_qty={capacity_metrics.get('max_safe_qty', 0.0)}"
                )

                if not capacity_report.get("approved", False):
                    reasons = "; ".join(capacity_report.get("reasons", [])) or "UNKNOWN"
                    msg = f"{capacity_log} | BLOCKED: {reasons}"
                    logger.warning(msg)
                    await firebase_service.log_event("Captain", msg, "WARNING")
                    return None

                warnings = "; ".join(capacity_report.get("warnings", []))
                logger.info(f"{capacity_log} | APPROVED" + (f" | WARN: {warnings}" if warnings else ""))
                if signal_data is not None:
                    signal_data["execution_capacity"] = capacity_report

                # [ECC llm-trading-agent-security] PRE-SEND SLIPPAGE L2
                # Analisa a profundidade do livro L2 e ajusta a ordem se necessário
                try:
                    slippage_check = await execution_capacity_gate.check_slippage_with_fallback(
                        symbol=symbol,
                        side=side,
                        qty=qty,
                        entry_price=current_price,
                        leverage=current_leverage,
                        ct_val=ct_val,
                        margin_usd=actual_margin_usd,
                        execution_mode=getattr(okx_rest_service, "execution_mode", settings.OKX_EXECUTION_MODE),
                    )
                    slippage_rec = slippage_check.get("recommendation", "MARKET")
                    if slippage_rec == "REDUCE_QTY":
                        new_qty = float(slippage_check.get("adjusted_qty", qty))
                        if new_qty > 0 and new_qty < qty:
                            logger.warning(
                                f"📉 [SLIPPAGE-L2] {symbol} qty reduzida: {qty:.4f} → {new_qty:.4f} | "
                                f"slippage={slippage_check.get('slippage_pct', 0):.3f}%"
                            )
                            qty = new_qty
                    elif slippage_rec == "POST_ONLY":
                        logger.warning(
                            f"📋 [SLIPPAGE-L2] {symbol} livro raso! Convertendo para Limit Post-Only. "
                            f"slippage={slippage_check.get('slippage_pct', 0):.3f}%"
                        )
                        # Sinaliza para o executor usar Limit Post-Only
                        if signal_data is not None:
                            signal_data["use_post_only"] = True
                        else:
                            signal_data = {"use_post_only": True}
                    if signal_data is not None:
                        signal_data["slippage_l2"] = slippage_check
                except Exception as slip_err:
                    logger.warning(f"⚠️ [SLIPPAGE-L2] Falha ao verificar slippage para {symbol}: {slip_err}")

                # -----------------------------------------------------
                # [V24.0] 10D STRICT LOGIC (10% Banca, 50x, 2% TP)
                # -----------------------------------------------------
                # Risk/Reward Ratio enforced natively. SL max 1% (50% ROI), TP EXACTLY 2% (100% ROI).
                

                # [V12.1.2] Extract Indicator Data (V33.1 HARDENED)
                indicators = (signal_data or {}).get("indicators", {}) or {}
                try:
                    atr = float(indicators.get("atr", 0) or 0)
                except (ValueError, TypeError):
                    atr = 0.0
                
                # [V33.0] PULLBACK HUNTER: Tenta usar o Stop Dinâmico da armadilha se existir
                adaptive_sl = signal_data.get("adaptive_sl", 0) if signal_data else 0
                is_swing_macro = signal_data.get("is_swing_macro", False) if signal_data else False
                
                # [V34.0] All-SWING Transition: Removed SCALP constraints
                # [V41.0] RANGING CALIBRATION: Reduz o risco inicial em mercados laterais
                # Se o alvo é curto (1%), o stop deve ser no máximo 1% para manter R:R 1:1.
                is_market_ranging = signal_data.get("is_market_ranging", False) if signal_data else False
                
                is_blitz_slot = (slot_type == "BLITZ_30M")
                
                if is_blitz_slot:
                    max_risk = 0.010  # 1.0% de preço (50% ROI SL com alavancagem 50x)
                    logger.info(f"⚡ [BLITZ_30M] Risco definido para {max_risk*100:.1f}% para alinhar com o stop de -50% ROI da estratégia.")
                elif is_market_ranging:
                    # [V42.5] Volatility-Aware Ranging Cap:
                    # If asset volatility (ATR/Price) is > 0.8%, relax the cap to allow standard SWING protection.
                    asset_volatility = (atr / current_price) if current_price > 0 else 0
                    if asset_volatility > 0.008:
                        max_risk = 0.035 # [V87.0] 3.5% (Swing Respirável para Alts)
                        logger.info(f"🚀 [V87.0] High Volatility Swing: Max_risk expanded to {max_risk*100:.1f}%")
                    else:
                        max_risk = 0.010 # 1.0% preço (50% ROI SL)
                        logger.info(f"🛡️ [V41.0 RANGING] Risco reduzido para {max_risk*100:.1f}% para alinhar com alvo lateral.")
                else:
                    # [V43.2] Zero Tolerance for Low Balance: Cap risk at 2% (100% ROI) if balance < $10
                    if balance < 10.0:
                        max_risk = 0.020
                        logger.info(f"🛡️ [V43.2] Low Balance SL Cap: Risk capped at {max_risk*100:.1f}% (100% ROI) to protect account.")
                    else:
                        max_risk = 0.050 if is_swing_macro else 0.035 # [V87.0] 3.5% a 5% de respiração

                if is_blitz_slot:
                    sl_percent = max_risk  # Garante exatamente o stop da estratégia de -50% ROI (1.0% preço)
                    logger.info(f"🛡️ [BLITZ_30M SL] Forçando SL fixo de {sl_percent*100:.2f}% (50% ROI com alavancagem 50x)")
                    final_sl = current_price * (1 - sl_percent) if side == "Buy" else current_price * (1 + sl_percent)
                elif adaptive_sl > 0:
                    final_sl = adaptive_sl
                    # Calcula o percentual de risco real desse SL cirúrgico para logs
                    sl_percent = abs((current_price - final_sl) / current_price)
                    logger.info(f"🛡️ [V33.0 PULLBACK HUNTER] Usando Stop Dinâmico Cirúrgico: {final_sl:.6f} ({sl_percent*100:.2f}% Risco)")
                else:
                    # Fallback: Cálculo Estrutural por ATR ou Max Risk (Ancoramento e antigas lógicas)
                    if atr > 0:
                        sl_percent = min(max_risk, (atr * 1.5) / current_price)
                    else:
                        sl_percent = max_risk
                    logger.info(f"🛡️ [V41.0] SL Enforcement/Fallback: {sl_percent*100:.2f}% (Cap: {max_risk*100:.1f}%)")
                    final_sl = current_price * (1 - sl_percent) if side == "Buy" else current_price * (1 + sl_percent)

                # [V33.0] Market Ranging Check para Alvo Curto
                is_market_ranging = signal_data.get("is_market_ranging", False) if signal_data else False
                
                # [V110.136] BLITZ R:R GUARANTEE: Para sinais BLITZ_30M, o TP é derivado
                # da distância real do SL estrutural, garantindo R:R ≥ 2:1.
                # Fórmula: TP_dist = max(2 × SL_dist, 2% preço mínimo doutrina)
                is_blitz_slot = (slot_type == "BLITZ_30M")

                if is_blitz_slot:
                    # 1. Calcula distância percentual real do SL
                    sl_dist_pct = abs(final_sl - current_price) / current_price if current_price > 0 else 0.035
                    # 2. TP mínimo = 2× distância SL (R:R 2:1)
                    min_tp_pct = sl_dist_pct * 2.0
                    # 3. Garante mínimo de doutrina Blitz: 100% ROI = 2% de preço @ 50x
                    blitz_tp_pct = max(0.02, min_tp_pct)
                    final_tp = (
                        current_price * (1 - blitz_tp_pct) if side.lower() == "sell"
                        else current_price * (1 + blitz_tp_pct)
                    )
                    move_room_pct = blitz_tp_pct * 100
                    rr_ratio = blitz_tp_pct / sl_dist_pct if sl_dist_pct > 0 else 0
                    expected_desc = (
                        f"BLITZ-RR≥2:1 ({blitz_tp_pct*100:.2f}% preço = "
                        f"{blitz_tp_pct*current_leverage*100:.0f}% ROI | R:R {rr_ratio:.1f}:1)"
                    )
                    logger.info(
                        f"⚡ [BLITZ-RR-GUARANTEE] {symbol} | "
                        f"SL dist={sl_dist_pct*100:.2f}% → TP={blitz_tp_pct*100:.2f}% "
                        f"[{blitz_tp_pct*current_leverage*100:.0f}% ROI] | R:R={rr_ratio:.1f}:1"
                    )

                elif is_market_ranging:
                    tp_percent = 0.02  # [V88.0] 2.0% preço (100% ROI @ 50x) - Alvo Ideal Almirante
                    expected_desc = "2.0% (100% ROI @ 50x) - RANGING"
                    final_tp = current_price * (1 + tp_percent) if side == "Buy" else current_price * (1 - tp_percent)
                    move_room_pct = tp_percent * 100

                elif is_swing_macro:
                    # [V87.0] BIG SWING DO ALMIRANTE: Busca alvos de 23% conforme imagem
                    tp_percent = 0.235  # 23.5% price
                    expected_desc = "23.5% (470% ROI @ 20x) - BIG SWING"
                    final_tp = current_price * (1 + tp_percent) if side == "Buy" else current_price * (1 - tp_percent)
                    move_room_pct = tp_percent * 100

                else:
                    # [V88.2] Trend Surge: Alvo de 10% para aproveitar ADX > 25
                    tp_percent = 0.10  # 10.0% preço (500% ROI @ 50x)
                    expected_desc = "10.0% (500% ROI) - TREND SURGE"
                    final_tp = current_price * (1 + tp_percent) if side == "Buy" else current_price * (1 - tp_percent)
                    move_room_pct = tp_percent * 100

                # Maintain variables for DB logging parity
                structural_target = final_tp
                target_extended = 0
                pattern = signal_data.get("indicators", {}).get("pattern", "unknown") if signal_data else "10D_STRICT"

                logger.info(f"🎯 [V28.1 BATALHÕES] {slot_type} TP {expected_desc}: Target={final_tp:.6f} for {symbol}")

                # 4. Atomic Deployment
                squadron_emoji = "🎯" if slot_type == "SNIPER" else "🏄"
                
                # [V12.0] Leverage Enforcement: Ensure dynamic target leverage before order entry
                await okx_rest_service.set_leverage(symbol, current_leverage)
                
                # Log exact expected margin usage
                margin_usd = actual_margin_usd
                logger.info(f"{squadron_emoji} {slot_type} DEPLOYING: {side} {qty} {symbol} @ {current_price} | Margin: ${margin_usd:.2f} (Expected: 10% of banca)")
                
                await firebase_service.log_event("Captain", f"{squadron_emoji} {slot_type} DEPLOYED: {side} {qty} {symbol} @ {current_price} | Margin: ${margin_usd:.2f}", "SUCCESS")

                # [V110.65] Calcula e passa o Ambush Price para entrada mais precisa
                ambush_price = 0
                if signal_data:
                    ambush_price = signal_data.get("ambush_price", 0)
                    if not ambush_price and final_sl > 0:
                        # Calcula zona de lambida automaticamente se não veio no sinal
                        from services.execution_protocol import execution_protocol
                        ambush_price = execution_protocol.calculate_ambush_price(current_price, final_sl, side, multiplier=0.50)
                        logger.info(f"🎯 [V110.65] Ambush Zone calculada: ${ambush_price:.6f} (Entry: ${current_price:.6f})")
                
                execution_started_at = time.time()
                order = await asyncio.wait_for(okx_rest_service.place_atomic_order(symbol, side, qty, final_sl, final_tp, slot_id=slot_id, leverage=current_leverage, ambush_price=ambush_price), timeout=10.0)
                execution_completed_at = time.time()
                
                if order and order.get("retCode") == 0:
                    # [V58.0] Refresh opening timestamp on success
                    self.recent_openings[norm_symbol] = time.time()

                    position_snapshot = None
                    order_result = order.get("result", {}) if isinstance(order, dict) else {}
                    if not (order_result.get("avgPrice") or order_result.get("avgPx")):
                        try:
                            pos_list = await asyncio.wait_for(okx_rest_service.get_active_positions(symbol=symbol), timeout=3.0)
                            position_snapshot = pos_list[0] if pos_list else None
                        except Exception as _pos_audit_err:
                            logger.warning(f"[EXEC-AUDIT] Could not fetch post-order position snapshot for {symbol}: {_pos_audit_err}")

                    try:
                        funding_rate = await asyncio.wait_for(okx_rest_service.get_funding_rate(symbol), timeout=3.0)
                    except Exception:
                        funding_rate = 0.0

                    from services.execution_audit import execution_audit_service
                    execution_audit = execution_audit_service.build_open_order_audit(
                        symbol=symbol,
                        side=side,
                        requested_qty=qty,
                        expected_price=current_price,
                        ct_val=ct_val,
                        leverage=current_leverage,
                        order_response=order,
                        capacity_report=capacity_report,
                        started_at=execution_started_at,
                        completed_at=execution_completed_at,
                        funding_rate=funding_rate,
                        position_snapshot=position_snapshot,
                    )
                    if execution_audit.get("status") == "WARN":
                        await firebase_service.log_event(
                            "Captain",
                            f"[EXEC-AUDIT] {symbol} WARN: {execution_audit.get('reasons', [])} {execution_audit.get('warnings', [])}",
                            "WARNING",
                        )
                    
                    # [V33.0] Extract reverse sniper flag for Regime Shield
                    is_reverse_sniper = signal_data.get("is_reverse_sniper", False) if signal_data else False
                    # [V84.2] FORCE PURGE: Limpa o slot fisicamente antes de preencher com o novo trade
                    # Isso garante que maestria_guard_active e outras flags sejam DELETADAS do Firestore.
                    await firebase_service.hard_reset_slot(slot_id, reason=f"Pre-Open Purge for {symbol}")

                    # [V110.137 GENESIS] Gera o RG unico da ordem (passaporte do trade)
                    import uuid as _uuid
                    strategy_type = "BLITZ_30M" if slot_type == "BLITZ_30M" else "SWING"
                    strategy_prefix = "BLZ" if strategy_type == "BLITZ_30M" else "SWG"
                    genesis_id = f"{strategy_prefix}-{int(time.time())}-{norm_symbol[:4]}-{_uuid.uuid4().hex[:6].upper()}"
                    opened_ts = time.time()

                    await firebase_service.update_slot(slot_id, {
                        "symbol": symbol,
                        "side": side,
                        "qty": qty,
                        "entry_price": current_price,
                        "entry_margin": margin,
                        "current_stop": final_sl,
                        "initial_stop": final_sl,
                        "order_id": signal_data.get("order_id") if signal_data else None,
                        "genesis_id": genesis_id,  # [V110.137] RG unico da ordem
                        "target_price": final_tp,
                        "leverage": current_leverage,
                        "slot_type": slot_type,
                        "status_risco": "ATIVO",
                        "pnl_percent": 0.0,
                        "pensamento": pensamento,
                        "opened_at": opened_ts,
                        "liq_price": 0,
                        "structural_target": structural_target,
                        "target_extended": target_extended,
                        "is_ranging_sniper": signal_data.get("is_ranging_sniper", False) if signal_data else False,
                        "v42_tag": signal_data.get("v42_tag", "STANDARD") if signal_data else "STANDARD",
                        "move_room_pct": move_room_pct,
                        "pattern": pattern,
                        "unified_confidence": signal_data.get("unified_confidence", 50) if signal_data else 50,
                        "fleet_intel": signal_data.get("fleet_intel", {}) if signal_data else {},
                        "is_reverse_sniper": is_reverse_sniper,
                        "market_regime": "RANGING" if is_market_ranging else "TRENDING",
                        "rescue_activated": False,
                        "rescue_resolved": False,
                        "is_shadow_strike": signal_data.get("is_shadow_strike", False) if signal_data else False,
                        "score": signal_data.get("score", 0) if signal_data else 0,
                        "execution_audit": execution_audit,
                        "timestamp_last_update": opened_ts
                    })

                    # [V110.137 GENESIS] Registra certidao de nascimento completa da ordem (Atômico)
                    base_genesis = signal_data.get("genesis_payload", {}) if signal_data else {}
                    genesis_payload = {
                        **base_genesis,  # Merge payload preparatório do Captain (se houver)
                        "genesis_id": genesis_id,
                        "strategy": strategy_type,
                        "symbol": symbol,
                        "side": side,
                        "slot_id": slot_id,
                        "leverage": current_leverage,
                        "entry_price": current_price,
                        "sl_price": final_sl,
                        "tp_price": final_tp,
                        "margin_usd": round(actual_margin_usd, 4),
                        "execution_capacity": signal_data.get("execution_capacity", {}) if signal_data else {},
                        "execution_audit": execution_audit,
                        "signal_score": signal_data.get("score", 0) if signal_data else 0,
                        "signal_timestamp": signal_data.get("timestamp", opened_ts) if signal_data else opened_ts,
                        "opened_at": opened_ts,
                        "events": [{"ts": opened_ts, "action": "ORDER_OPENED", "roi": 0.0}],
                        "units_extracted": 0,
                        "moonbag_id": None,
                        "closed_at": None,
                        "exit_price": None,
                        "final_roi": None,
                        "final_pnl_usd": None,
                        "close_reason": None,
                        "status": "ACTIVE"
                    }
                    try:
                        await firebase_service.register_order_genesis(genesis_payload)
                        logger.info(f"[GENESIS] {genesis_id} registrado para {symbol} de forma atômica pós-validação.")
                    except Exception as _ge:
                        logger.warning(f"[GENESIS] Falha ao registrar genesis para {symbol}: {_ge}")
                    
                    # [V110.19.3] Update LPM (Long Term Memory) on success
                    self.active_slot_memory[slot_id] = {
                        "symbol": norm_symbol,
                        "last_seen": time.time()
                    }
                    
                    await self.update_banca_status()
                    return order
                else:
                    return None

            except Exception as e:
                logger.error(f"Execution Error for {symbol}: {e}")
                return None
            finally:
                # 5. Release Lock
                if (norm_symbol, slot_id) in self.pending_slots:
                    del self.pending_slots[(norm_symbol, slot_id)]

    async def close_slot_for_preemption(self, slot_id: int, reason: str = "PREEMPTED_BY_SHADOW"):
        """
        [V110.13.0] SURGICAL CLOSE: Closes a specific slot's position to make room for a higher priority signal.
        """
        try:
            # Atomic lock to prevent sync interference
            async with self.execution_lock:
                slots = await firebase_service.get_active_slots(force_refresh=True)
                slot = next((s for s in slots if s["id"] == slot_id), None)
                
                if not slot or not slot.get("symbol"):
                    logger.warning(f"⚠️ [PREEMPTION] Slot {slot_id} is already empty. No need to close.")
                    return True

                symbol = slot["symbol"]
                side = slot.get("side", "Buy")
                qty = float(slot.get("qty", 0))
                
                logger.info(f"🛡️ [PREEMPTION] Surgically closing {symbol} (Slot {slot_id}) for: {reason}")
                
                # 1. Close on Exchange/Paper
                # O close_position no modo PAPER já cuida de: calcular PNL, registrar no Vault e dar hard_reset_slot.
                # No modo REAL, ele fecha na Bybit e o sync_slots_with_exchange registra o PNL depois.
                if qty > 0:
                    await okx_rest_service.close_position(symbol, side, qty, reason=reason)
                else:
                    # Lixo residual sem quantidade: Limpeza manual
                    await firebase_service.hard_reset_slot(slot_id, reason=f"CLEANUP_{reason}")
                
                # 3. Register in recently_closed to avoid immediate ghost re-entry
                self.register_recently_closed(symbol)
                
                # [V110.19.3] Clear LPM on explicit closure
                if slot_id in self.active_slot_memory:
                    del self.active_slot_memory[slot_id]
                
                await firebase_service.log_event("Bankroll", f"🛡️ [PREEMPTION] Slot {slot_id} ({symbol}) closed successfully.", "SUCCESS")
                return True
                
        except Exception as e:
            logger.error(f"❌ [PREEMPTION-ERROR] Failed to close slot {slot_id}: {e}")
            return False

    async def emergency_close_all(self):
        """Panic Button: Closes all open positions immediately."""
        logger.warning("\U0001f6a8 PANIC BUTTON ACTIVATED: Closing all positions!")
        slots = await firebase_service.get_active_slots()
        
        for slot in slots:
            symbol = slot.get("symbol")
            if symbol:
                side = slot.get("side")
                try:
                    # Fetch position to get size (Simulation aware)
                    pos_list = await okx_rest_service.get_active_positions(symbol=symbol)
                    for pos in pos_list:
                        size = float(pos.get("size", 0))
                        if size > 0:
                            await okx_rest_service.close_position(symbol, pos["side"], size)
                except Exception as e:
                    logger.error(f"Error closing {symbol}: {e}")
                
                # Reset Slot in DB
                await firebase_service.update_slot(slot["id"], {
                    "symbol": None, "side": None, "entry_price": 0, "current_stop": 0, 
                    "status_risco": "LIVRE", "pnl_percent": 0
                })
        
        await firebase_service.log_event("Captain", "PANIC BUTTON: All positions closed.", "WARNING")
        await self.update_banca_status()
        return {"status": "success", "message": "All positions closed"}

    async def position_reaper_loop(self):
        """
        Background loop that runs every 30s to detect closed positions on Bybit
        and finalize their data in Firebase (History + Slot clearing).
        """
        logger.info("Position Reaper loop active.")
        while True:
            try:
                await self.sync_slots_with_exchange()
                await self.update_banca_status()
            except Exception as e:
                logger.error(f"Error in Position Reaper: {e}")
            await asyncio.sleep(30) # Scan every 30s

    async def register_sniper_trade(self, trade_data: dict):
        """
        V4.2/V4.3.1: Registra um trade no ciclo (Sniper ou Surf).
        Chamado pelo Position Reaper quando um trade fecha.
        """
        try:
            slot_type = trade_data.get("slot_type", "SNIPER")
            pnl = trade_data.get("pnl", 0)
            
            # [V110.64 FIX] Use the updated vault service method
            # BUGFIX: get_slot_type() retorna "SWING" para todos os slots,
            # mas antes só "SNIPER" era aceito — causando ZERO registros no Vault.
            # [V125] BLITZ_30M incluido — antes todos os trades BLITZ eram ignorados
            valid_slot_types = {"SNIPER", "SWING", "TREND", "SCALP", "SURF", "BLITZ_30M", "BLITZ", "MOONBAG", "PAPER_GHOST"}
            if slot_type in valid_slot_types:
                await vault_service.register_sniper_trade(trade_data)
                status_msg = "Win" if pnl > 0 else "Loss"
                logger.info(f"Sniper {status_msg} registered in Vault: {trade_data.get('symbol')} ${pnl:.2f}")

            # [V33.0] TRADE OUTCOME TRACKER: Update Blocklist + Hot Asset
            try:
                from services.signal_generator import signal_generator
                sym = trade_data.get("symbol", "")
                norm_sym = sym.replace(".P", "").upper() if sym else ""
                
                if norm_sym:
                    if pnl > 0:
                        # WIN: Update Hot Asset
                        hot = signal_generator.hot_assets.get(norm_sym, {'wins': 0, 'last_win_at': 0})
                        hot['wins'] = hot.get('wins', 0) + 1
                        hot['last_win_at'] = time.time()
                        signal_generator.hot_assets[norm_sym] = hot
                        logger.info(f"🔥 [V33.0] Hot Asset updated: {norm_sym} (wins: {hot['wins']})")
                        # [V110.5] HOT STREAK SHIELD: 15-minute cool-down instead of 4h
                        block = signal_generator.auto_blocked_assets.get(norm_sym, {'consecutive_losses': 0, 'blocked_until': 0})
                        block['consecutive_losses'] = 0
                        block['blocked_until'] = time.time() + (15 * 60) # 15 minutes block
                        signal_generator.auto_blocked_assets[norm_sym] = block
                        signal_generator._save_auto_blocks()
                        logger.info(f"✅ [HOT STREAK] {norm_sym} finalizado com WIN. Bloqueado por apenas 15m para respiro.")
                        
                        if norm_sym in signal_generator.hot_assets:
                            signal_generator.hot_assets[norm_sym]['wins'] += 1
                    else:
                        # LOSS: Update Blocklist
                        block = signal_generator.auto_blocked_assets.get(norm_sym, {'consecutive_losses': 0, 'blocked_until': 0})
                        block['consecutive_losses'] = block.get('consecutive_losses', 0) + 1
                        
                        # [V6.4.2] TIERED BLOCKING:
                        # 1. Deep Loss Shield: If ROI < -80%, block for 48h immediately
                        final_roi = trade_data.get("final_roi", 0)
                        is_deep_loss = float(final_roi) <= -80.0
                        
                        if is_deep_loss:
                            block['blocked_until'] = time.time() + (86400 * 2) # 48h block
                            logger.warning(f"🚨 [V6.4.2 DEEP-LOSS BLOCK] {norm_sym} bloqueado por 48h (ROI: {final_roi:.1f}%)")
                        elif block['consecutive_losses'] >= 2:
                            block['blocked_until'] = time.time() + 86400  # 24h block standard
                            logger.warning(f"🚫 [V33.0] AUTO-BLOCK: {norm_sym} bloqueado por 24h ({block['consecutive_losses']} losses consecutivas)")
                        else:
                            # Standard LOSS cooldown (4h)
                            block['blocked_until'] = time.time() + (3600 * 4)
                            logger.warning(f"🚫 [V100.1 COOLDOWN] {norm_sym} finalizado com LOSS. Bloqueado por 4h para descanso.")
                            
                        signal_generator.auto_blocked_assets[norm_sym] = block
                        signal_generator._save_auto_blocks() # Persistence
                        # Reset hot asset on loss
                        if norm_sym in signal_generator.hot_assets:
                            del signal_generator.hot_assets[norm_sym]
            except Exception as track_err:
                logger.warning(f"[V33.0] Trade outcome tracking error: {track_err}")

            # [V110.5] PAPER MODE BANKROLL PARITY:
            # REMOVED double-counting. We do NOT add PnL to configured_balance anymore.
            # BankrollManager.update_banca_status() naturally calculates total_pnl from Vault History
            # and adds it to the base configured_balance to yield exactly accurate `saldo_total`.
            from services.okx_rest import okx_rest_service
            if okx_rest_service.execution_mode == "PAPER":
                logger.info(f"✅ [PAPER PARITY] Trade {trade_data.get('symbol')} fechado. O saldo_total será atualizado via sincronização do Vault.")
        except Exception as e:
            logger.error(f"Error registering trade in vault: {e}")

    # =========================================================================
    # ████ [V110.62] GUARDIAN HEDGE PROTOCOL (SLOT ZERO) ████
    # =========================================================================

    async def activate_emergency_hedge(self, reason: str = "Market Crash"):
        """
        [V110.62] Ativa um SHORT de Hedge em BTCUSDT para proteger a banca.
        Usado apenas em quedas violentas detectadas pelo Oráculo.
        """
        logger.warning(f"🛡️ [GUARDIAN-HEDGE] Guardian Hedge desativado conforme User Rule (Sem BTC). Motivo: {reason}")
        return

    async def auto_close_hedge(self, reason: str = "Recovery"):
        """
        [V110.62] Encerra o Seguro de Banca quando o mercado estabiliza.
        """
        async with self._hedge_lock:
            if not self.hedge_active:
                return
                
            logger.info(f"🛡️ [GUARDIAN-HEDGE] Encerrando seguro. Motivo: {reason}")
            try:
                # Encerra a posição no BTC
                success = await okx_rest_service.close_position("BTCUSDT", side="Sell") # Close Short
                if success:
                    self.hedge_active = False
                    self.hedge_position_id = None
                    await firebase_service.log_event("SENTINELA", f"✅ GUARDIAN HEDGE ENCERRADO: {reason}", "SUCCESS")
                else:
                    logger.error("❌ Erro ao fechar posição de Hedge.")
            except Exception as e:
                logger.error(f"Erro ao encerrar Hedge: {e}")

bankroll_manager = BankrollManager()
