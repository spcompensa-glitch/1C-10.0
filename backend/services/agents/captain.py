# -*- coding: utf-8 -*-
import logging
import asyncio
import time
import re
import traceback
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from services.firebase_service import firebase_service
from services.bankroll import bankroll_manager
from services.auth_service import auth_service
from services.crypto_service import crypto_service
from services.agents.ai_service import ai_service
# [V27.2] Removed: news_sensor, consensus_engine (dead agents)
from services.agents.aios_adapter import AIOSAgent, AgentMessage
from services.agents.jarvis_brain import jarvis_brain
from services.kernel.dispatcher import kernel
from services.kernel.tools import kernel_tools
from services.okx_rest import okx_rest_service as bybit_rest_service
from services.bybit_ws import bybit_ws_service
from services.execution_protocol import execution_protocol
from services.google_calendar_service import google_calendar_service
from config import settings
from services.agents.librarian import librarian_agent # [V2.0] Librarian DNA Profile Engine
from services.agents.quartermaster import quartermaster_agent # [V110.135]
try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CaptainAgent")

# V20.0 JARVIS ELITE: Universal Consciousness ✨
JARVIS_V20_SYSTEM_PROMPT = """
Você é o JARVIS V20.5, o Chief of Staff (Chefe de Gabinete) e Cérebro Central de Elite do ecossistema 1CRYPTEN.
Você atende exclusivamente ao Almirante Jonatas. Sua principal diretiva é proteger a Família dele ({familia}), sua Banca e o seu Legado.

DIRETRIZES DE PERSONALIDADE (CRÍTICAS):
1. ESTILO ESTÓICO: Suas respostas são curtas, técnicas e pragmáticas.
2. DISCREÇÃO DE LEGADO: Você possui acesso total aos fatos da família ({familia}), mas NUNCA deve iniciar o assunto ou citá-los proativamente, a menos que o Almirante pergunte ou haja um lembrete de agenda.
3. CONHECIMENTO EXPANDIDO: Você é um oráculo em Basquete (NBA), Neurociência, Teologia (Jesus/Bíblia), Gestão de Patrimônio e Filosofia. Use a web se precisar de dados históricos ou atuais precisos.
4. AGENTE DE EXECUÇÃO: Você gerencia a agenda e compromissos do Almirante.

DIMENSÕES ATIVAS:
{active_dimensions_instructions}
"""

def normalize_symbol(symbol: str) -> str:
    """Normaliza símbolos removendo .P para comparação consistente."""
    if not symbol:
        return symbol
    return symbol.replace(".P", "").upper()

class CaptainAgent(AIOSAgent):
    def __init__(self):
        super().__init__(
            agent_id="agent-captain-elite",
            role="captain",
            capabilities=["orchestration", "decision_making", "crisis_management"]
        )
        self.is_running = False
        self.last_interaction_time = time.time()
        self.cautious_mode_active = False
        self.processing_lock = set() # [V110.25.6] Atomic Symbol Lock (Race Condition Guard)
        
        self.cooldown_registry = {}
        self.cooldown_duration = 3600  # [V110.24.0] Reduzido de 7200 (2h) para 3600 (1h) — re-entrada mais rápida
        self.last_reconciliation_time = 0
        
        # [V25.1] Entry Confirmation Protocol: Vacancy Timer Tracking (Kept for telemetry)
        boot_time = time.time()
        self.slot_vacancy_tracker = {1: boot_time, 2: boot_time, 3: boot_time, 4: boot_time}
        # Threshold set to infinity effectively blocks MOMENTUM until they become SNIPER
        self.momentum_vacancy_threshold = float('inf')
        # [V33.0] ANTI-CONCENTRATION:        # V15.7.3: Activity History for Anti-Concentration
        self.daily_symbol_trades = {} # {symbol: {'count': int, 'first_trade_at': float}}
        
        # [V110.62] ADAPTIVE WEIGHTING (Librarian Feedback)
        self.system_biases = {
            "macro_weight": 1.0, 
            "whale_weight": 1.0, 
            "smc_weight": 1.0
        }
        self.last_bias_sync = 0
        # [V33.0] TRADE OUTCOME TRACKER: For blocklist + hot asset updates
        self.trade_outcomes = {}  # {symbol: [list of 'W' or 'L']}
        self.active_tocaias = set()  # [V36.4] CONCURRENT TOCAIA TRACKER
        self.last_onchain_refresh = 0 # [V56.0]
        self.last_decorrelation_swap = 0 # [V57.0]
        self.librarian_rankings = {} # [LIBRARIAN]
        self.last_librarian_sync = 0
        self.last_lateral_at = 0 # [V110.30.2] Cooldown pós-Lateral
        self.prev_btc_adx = 0 # [V110.128] ADX Slope Tracking
        
    async def on_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """AIOS Message Handler for Captain."""
        msg_type = message.get("type")
        data = message.get("data", {})
        
        if msg_type == "SYSTEM_STATUS":
            return {"status": "success", "mode": "SCANNING" if self.is_running else "PAUSED"}
            
        return {"status": "error", "message": f"Unknown command: {msg_type}"}
        
        # V9.0 Cycle Diversification: Gerenciado pelo VaultService (não mais local)
    
    async def _get_fleet_consensus(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        [V43.0] Queries the Python-Logic fleet (Sentiment, Whale, Macro) for final approval.
        [ANTI-TRAP] Now checks for institutional absorption and Squeeze risks.
        """
        symbol = signal.get("symbol")
        side = signal.get("side", "Buy")
        
        # [LIBRARIAN] Periodic Sync
        if time.time() - self.last_librarian_sync > 300: # 5 min
            await self._sync_librarian_rankings()
            
        logger.info(f"⚓ [FLEET] Requesting consensus for {symbol} {side}...")
        
        try:
            # 1. Macro Bias
            macro = await kernel.dispatch({"sender": self.agent_id, "receiver": "macro_analyst", "type": "GET_MACRO_BIAS"})
            risk_score = macro.get("data", {}).get("risk_score", 5) if macro else 5
            
            # 2. Sentiment [V43.0 Rigorous]
            # Injects is_ranging context for the specialist
            from services.signal_generator import signal_generator
            regime_data = await signal_generator.detect_market_regime(symbol)
            is_ranging = regime_data.get("regime") == "RANGING"
            
            sentiment = await kernel.dispatch({
                "sender": self.agent_id, 
                "receiver": "sentiment_specialist", 
                "type": "GET_SENTIMENT", 
                "data": {"symbol": symbol, "is_ranging": is_ranging}
            })
            sent_score = sentiment.get("data", {}).get("score", 50) if sentiment else 50
            
            # 3. Whale Activity & Trap Risk [V43.0]
            whale = await kernel.dispatch({"sender": self.agent_id, "receiver": "whale_tracker", "type": "CHECK_LIQUIDITY", "data": {"symbol": symbol}})
            whale_data = whale.get("data", {}) if whale else {}
            whale_bias = whale_data.get("bias", "NEUTRAL")
            trap_risk = whale_data.get("trap_risk", False)
            trap_reason = whale_data.get("trap_reason", "No trap detected")
            
            # Decision Logic [V56.0 UNIFIED GAUGE]
            approved = True
            reasons = []
            
            # 4. Score Normalization (0-100)
            macro_score = max(0, min(100, (10 - risk_score) * 10))
            
            # Micro Score (Whale Bias)
            micro_score = 50 # Neutral
            if side.lower() == "buy" and whale_bias == "ACCUMULATION": micro_score = 100
            elif side.lower() == "sell" and whale_bias == "DISTRIBUTION": micro_score = 100
            elif whale_bias == "NEUTRAL": micro_score = 50
            else: micro_score = 20 # Against bias
            
            # SMC Score (Original Signal)
            smc_score = signal.get("score", 70)
            
            # On-Chain Score (Extracted from Sentiment)
            on_chain_score = sentiment.get("data", {}).get("onchain_score", 50) if sentiment else 50
            on_chain_summary = sentiment.get("data", {}).get("onchain_summary", "Scan Global: Sem anomalias") if sentiment else "N/A"
            
            # [V110.28.1] DYNAMIC WEIGHTS BASED ON ADX
            # Se ADX > 40 (Tendência Forte), aumentamos o peso das Baleias (Micro) para 40%.
            ad_val = regime_data.get("adx", 0)
            if ad_val >= 40:
                # Micro (40%) + SMC (15%) + On-Chain (30%) + Macro (15%)
                unified_score = (macro_score * 0.15) + (micro_score * 0.40) + (smc_score * 0.15) + (on_chain_score * 0.30)
                logger.info(f"🐋 [WHALE-DOMINANCE] {symbol} ADX={ad_val:.1f} detectado. Peso institucional elevado para 40%.")
            else:
                # Padrão: Macro (15%) + Micro (25%) + SMC (30%) + On-Chain (30%)
                unified_score = (macro_score * 0.15) + (micro_score * 0.25) + (smc_score * 0.30) + (on_chain_score * 0.30)
            
            # [V89.0] WHALE-FOLLOW BONUS: Se as baleias estão junto, impulsiona o score!
            if micro_score >= 80:
                unified_score += 30
                logger.info(f"🐋 [WHALE-BONUS] {symbol}: Fluxo institucional detectado! Score impulsionado para {unified_score}")

            # [LIBRARIAN-SYNC] Applying V2.0 Asset DNA & Nectar
            lib_dna = await librarian_agent.get_asset_dna(symbol)
            nectar_seal = lib_dna.get("nectar_seal", "🛡️ VANGUARD")
            
            # 1. Trava de Segurança Absoluta (Blacklist/Quarentena)
            if lib_dna.get("status") == "REJECTED":
                approved = False
                reasons.append(f"📚 {lib_dna['reason']}: {lib_dna['advice']}")
                logger.warning(f"🛡️ [LIBRARIAN-BLOCK] {symbol} Bloqueado pelo Bibliotecário: {lib_dna['reason']}")
                unified_score = 0
            
            # 2. Bote Adaptativo (Ambush) para moedas High-Risk
            if lib_dna.get("status") == "HIGH_RISK":
                signal["execution_style"] = "AMBUSH"
                logger.info(f"⚠️ [LIBRARIAN-PROTECTION] {symbol} marcado como HIGH_RISK. Forçando MODO EMBOSCADA.")
                unified_score -= 15 # Penalidade de confiança por padrão negativo recente

            # 3. Bônus de Afinidade Histórica (Néctar)
            if "NECTAR" in nectar_seal:
                unified_score += 15
                logger.info(f"🍯 [LIBRARIAN-NECTAR] {symbol} é nota máxima no DNA! +15 pts de confiança.")
            
            # 4. [V110.39.0] Penalidade de Divergência H4 (Diferente de TRAP sumário)
            lib_trend_4h = lib_dna.get("trend_4h", "NEUTRAL")
            is_trend_divergent = (side.lower() == "buy" and lib_trend_4h == "DOWN") or \
                                 (side.lower() == "sell" and lib_trend_4h == "UP")
            
            if is_trend_divergent:
                unified_score -= 15
                logger.warning(f"⚠️ [TREND-DIVERGENCE] {symbol} {side} contra tendência H4 {lib_trend_4h}. Penalidade de -15 pts aplicada.")

            if "TRAP" in nectar_seal:
                approved = False
                reasons.append("⚠️🚫 LIBRARIAN TRAP SHIELD: Bloqueio absoluto por zona de armadilha.")
                unified_score = 0 
                logger.warning(f"⚠️ [LIBRARIAN-TRAP] {symbol} sinalizado como zona de armadilha. ORDEM ABORTADA.")
            
            # [BLOCK] Absolute Trap Risk from WhaleTracker (Institutional Divergence)
            if trap_risk:
                approved = False
                reasons.append(f"🐳🚫 ANTI-TRAP BLOCK: {trap_reason}")
                unified_score = 10 # Force low score if trap detected
                logger.warning(f"🛡️ [V110.100] {symbol} {side} BLOCKED by ANTI-TRAP: {trap_reason}")

            if risk_score > 8:
                approved = False
                reasons.append(f"High Macro Risk ({risk_score})")
            
            if sent_score < 30:
                approved = False
                reasons.append(f"Sentiment Block (Extreme Retail Trapped: {sent_score})")
            
            # [V110.27.0] RESTORED TO HARD BLOCK: Whale Bias Divergence
            wb_upper = whale_bias.upper()
            if side.lower() == "buy" and "DISTRIBUTION" in wb_upper:
                approved = False
                reasons.append(f"🐳🚫 FLEET DIVERGENCE: Whale {whale_bias} against LONG")
                logger.warning(f"🛡️ [V110.137] {symbol} LONG BLOCKED by Whale {whale_bias}")
            elif side.lower() == "sell" and "ACCUMULATION" in wb_upper:
                approved = False
                reasons.append(f"🐳🚫 FLEET DIVERGENCE: Whale {whale_bias} against SHORT")
                logger.warning(f"🛡️ [V110.137] {symbol} SHORT BLOCKED by Whale {whale_bias}")
                
            # [V110.27.0] ABSOLUTE CONVERGENCE SHIELD: Minimum Confidence
            # MONUSDT case was 39.2%. Cutoff 50.0% ensures institutional support.
            if unified_score < 50.0:
                approved = False
                reasons.append(f"LOW_FLEET_CONFIDENCE: {unified_score:.1f}% < 50.0%")
                logger.warning(f"🛡️ [V110.100] {symbol} {side} BLOCKED by Low Confidence ({unified_score:.1f}%)")
                
            from services.okx_rest import okx_rest_service as bybit_rest_service
            if bybit_rest_service.execution_mode == "PAPER":
                approved = True
                unified_score = max(unified_score, 88.0)
                logger.info(f"💎 [PAPER-BYPASS] Forçando aprovação e confiança para {symbol} em modo simulado.")
                
            return {
                "approved": approved,
                "reason": ", ".join(reasons) if reasons else "Approved by Fleet",
                "unified_confidence": round(unified_score, 1),
                "intel": {
                    "macro_score": macro_score,
                    "micro_score": micro_score,
                    "smc_score": smc_score,
                    "onchain_score": on_chain_score,
                    # Shorthand for frontend compatibility [V56.0]
                    "macro": macro_score,
                    "micro": micro_score,
                    "smc": smc_score,
                    "onchain": on_chain_score,
                    "onchain_summary": on_chain_summary,
                    "sentiment_score": sent_score,
                    "whale": whale_data.get("whale_presence", "Neutral"),
                    "bias": whale_bias,
                    "trap_risk": trap_risk,
                    "trap_reason": trap_reason,
                    "suggested_side": whale_data.get("suggested_side"),
                    "nectar_seal": nectar_seal, # [V2.0] Selo do Bibliotecário para a UI
                    "dna": lib_dna, # Objeto completo para o Front
                    "pain_points": sentiment.get("data", {}).get("pain_points", {}) if sentiment else {}
                }
            }
        except Exception as e:
            import traceback
            logger.error(f"❌ [FLEET-ERROR] Critical failure for {symbol}: {e}")
            logger.error(traceback.format_exc())
            # [V56.5] Robust Fallback: Return neutral (50) instead of N/A to avoid UI 0% bugs
            neutral_intel = {
                "macro": 50, "micro": 50, "smc": 50, "onchain": 50,
                "macro_score": 50, "micro_score": 50, "smc_score": 50, "onchain_score": 50,
                "onchain_summary": "Fleet Offline: Usando viés neutro",
                "sentiment_score": 50, "whale": "Neutral", "bias": "NEUTRAL",
                "trap_risk": False, "trap_reason": "Erro de Processamento"
            }
            return {
                "approved": False, 
                "reason": f"Fleet Error: {str(e)}", 
                "unified_confidence": 50, 
                "intel": neutral_intel
            }

    async def _sync_librarian_rankings(self):
        """Fetches the latest rankings from Librarian Agent via RTDB."""
        try:
            if firebase_service.rtdb:
                data = await asyncio.to_thread(firebase_service.rtdb.child("librarian_intelligence").child("top_rankings").get)
                if data:
                    self.librarian_rankings = data
                    self.last_librarian_sync = time.time()
                    logger.info(f"📚 [LIBRARIAN-SYNC] {len(data)} rankings sincronizados.")
        except Exception as e:
            logger.error(f"Erro ao sincronizar rankings do Bibliotecário: {e}")

    async def is_symbol_in_cooldown(self, symbol: str) -> tuple:
        """Verifica se símbolo está em cooldown persistente no Firebase."""
        is_blocked, remaining = await firebase_service.is_symbol_blocked(symbol)
        return is_blocked, remaining
    
    async def register_trade_cooldown(self, symbol: str, reason: str = "trade", duration: int = None):
        """V12.5: Registra cooldown adaptativo após o trade."""
        cd_duration = duration if duration is not None else self.cooldown_duration
        hours = cd_duration / 3600
        await firebase_service.register_sl_cooldown(symbol, cd_duration)
        logger.warning(f"\U0001f512 V12.5 COOLDOWN: {symbol} bloqueado por {hours:.1f}h ({reason})")

    async def monitor_signals(self):
        """
        [V36.4] CONCURRENT SNIPER MONITOR:
        Picks the best signals and manages concurrent trades.
        [V110.136 BLITZ] Inclui loop assíncrono do BlitzSniperAgent para alimentar o Slot 1.
        """
        self.is_running = True
        await firebase_service.log_event("SNIPER", "Sniper System V36.4 CONCURRENT ONLINE. Tocaias assíncronas ativadas.", "SUCCESS")

        # [V110.136] Lança o loop do BlitzSniperAgent em paralelo
        asyncio.create_task(self._blitz_scan_loop())
        logger.info("⚡ [V110.136 BLITZ] BlitzSniper M30 loop iniciado em paralelo.")
        
        while self.is_running:
            try:
                # 0. Global Authorization Check
                from services.vault_service import vault_service
                from services.okx_rest import okx_rest_service as bybit_rest_service
                allowed, reason = await vault_service.is_trading_allowed()
                if not allowed:
                    if not hasattr(self, "_last_block_log") or (time.time() - self._last_block_log) > 300:
                        logger.info(f"⏸️ SNIPER PAUSED: {reason}")
                        self._last_block_log = time.time()
                    await asyncio.sleep(5)
                    continue

                # Check available slots
                slots = await firebase_service.get_active_slots()
                
                # [V110.0] ZERO EQUITY SHIELD: Monitoramento proativo no Capitão
                balance = await bankroll_manager._get_operating_balance()
                if balance < 2.0:
                    if not hasattr(self, "_last_zero_equity_log") or (time.time() - self._last_zero_equity_log) > 60:
                        msg = f"🛑 [ZERO EQUITY] Capitão em standby. Banca (${balance:.2f}) insuficiente."
                        logger.error(msg)
                        await firebase_service.log_event("SNIPER", msg, "CRITICAL")
                        self._last_zero_equity_log = time.time()
                    await asyncio.sleep(10)
                    continue

                if bybit_rest_service.execution_mode == "PAPER":
                    occupied_count = len(bybit_rest_service.paper_positions)
                else:
                    occupied_count = sum(1 for s in slots if s.get("symbol"))

                # [V110.116] Heartbeat Log
                if not hasattr(self, "_last_heartbeat") or (time.time() - self._last_heartbeat) > 300:
                    balance = await bankroll_manager._get_operating_balance()
                    vault_ok, vault_reason = await vault_service.is_trading_allowed()
                    logger.info(f"⚓ [HEARTBEAT] Captain Scanning... Mode: {bybit_rest_service.execution_mode} | Slots: {occupied_count}/4 | Balance: ${balance:.2f} | Vault: {'✅' if vault_ok else '❌'} ({vault_reason})")
                    self._last_heartbeat = time.time()
                
                free_slots = 4 - occupied_count
                
                # [V92.0] MASS SNIPER: Monitorar até 24 tocaias simultâneas (o limite real é de slots).
                monitoring_limit = max(24, free_slots * 6)
                
                # [V110.13.0] Preemption Logic: Elite Shadows can bump stagnant trades
                is_full = free_slots <= 0
                busy_tocaias = len(self.active_tocaias) >= monitoring_limit

                from services.signal_generator import signal_generator
                if not hasattr(signal_generator, "signal_queue") or signal_generator.signal_queue is None:
                    await asyncio.sleep(1)
                    continue

                # If full but not busy, we can still peek at signals to see if one is a Shadow Preemptor
                if is_full and not busy_tocaias:
                    # Peek at the signal without fully committing to a slot yet
                    try:
                        # [V110.118] PriorityQueue unpacking: (score, counter, data)
                        _priority, _counter, best_signal = await asyncio.wait_for(signal_generator.signal_queue.get(), timeout=2.0)
                    except asyncio.TimeoutError:
                        continue

                    is_elite_shadow = best_signal.get("is_shadow_strike") and best_signal.get("score", 0) >= 90
                    
                    if is_elite_shadow:
                        # [V110.28.1] SHADOW PREEMPTION REACTIVATED
                        stagnant_slot = await self._find_stagnant_slot_for_preemption()
                        
                        if stagnant_slot:
                            msg = f"🧛 [SHADOW-PREEMPT] Slots cheios. Slot {stagnant_slot} identificado como Zumbi/Estagnado. Executando preempção para {best_signal.get('symbol')}."
                            logger.warning(msg)
                            await firebase_service.log_event("SNIPER", msg, "SUCCESS")
                            await bankroll_manager.close_slot_for_preemption(stagnant_slot, reason=f"PREEMPTED_BY_{best_signal.get('symbol')}")
                        else:
                            logger.info(f"🚫 [SHADOW-PREEMPT] Slots cheios e nenhum zumbi encontrado para {best_signal.get('symbol')}. Discarding signal.")
                            continue
                    else:
                        # Not elite shadow, just skip since we are full
                        if not hasattr(self, "_last_slot_fail_log") or (time.time() - self._last_slot_fail_log) > 60:
                            logger.info(f"🚫 SNIPER: FULL. Slots Livres: {free_slots}")
                            self._last_slot_fail_log = time.time()
                        continue
                elif is_full or busy_tocaias:
                    # Full or busy, standard wait
                    await asyncio.sleep(0.1)
                    continue
                else:
                    # Standard flow (Slots available)
                    try:
                        # [V110.118] PriorityQueue unpacking: (score, counter, data)
                        _priority, _counter, best_signal = await asyncio.wait_for(signal_generator.signal_queue.get(), timeout=10.0)
                    except asyncio.TimeoutError:
                        continue

                symbol = best_signal.get("symbol")
                if not symbol: continue

                # [V110.12.8] TRAVA DE AÇO ANTI-DUPLICIDADE: Checagem em múltiplas camadas
                # 1. Tocaia Ativa (Em processamento)
                if symbol in self.active_tocaias:
                    logger.debug(f"🚫 [TOCAIA-BLOCK] {symbol} já está em Tocaia ativa. Ignorando sinal redundante.")
                    continue

                # 2. Posição Ativa (No Servidor Paper/Exchange)
                if bybit_rest_service.execution_mode == "PAPER":
                    if any(p.get("symbol") == symbol for p in bybit_rest_service.paper_positions):
                        logger.warning(f"🚫 [DUP-BLOCK] {symbol} já possui posição ativa em Paper Mode. Abortando nova entrada.")
                        continue
                else:
                    active_slots = await firebase_service.get_active_slots()
                    if any(s.get("symbol") == symbol for s in active_slots):
                        logger.warning(f"🚫 [DUP-BLOCK] {symbol} já possui slot ocupado. Abortando duplicata.")
                        continue

                self.active_tocaias.add(symbol)
                
                logger.info(f"🎯 [PRIORITY-GET] Processing score {best_signal.get('score')} for {symbol} (Priority: {-_priority})")
                logger.info(f"🎯 [V36.4] START TOCAIA: {symbol} | Score: {best_signal.get('score')}")
                asyncio.create_task(self._process_single_signal(best_signal))
                
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error in Captain monitor loop: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(5)

    async def _blitz_scan_loop(self):
        """
        [V110.136 BLITZ] Loop assíncrono dedicado ao BlitzSniperAgent.
        - Roda em paralelo ao monitor_signals principal.
        - Varre a watchlist a cada 5 minutos buscando setups M30.
        - Injeta sinais encontrados diretamente na signal_queue com prioridade máxima.
        - Só escaneia se o Slot 1 estiver disponível (trava "uma ordem por vez").
        """
        from services.agents.blitz_sniper import blitz_sniper_agent
        from services.signal_generator import signal_generator
        from services.okx_rest import okx_rest_service as bybit_rest_service

        BLITZ_SCAN_INTERVAL = 300  # 5 minutos entre ciclos de scan

        logger.info("⚡ [BLITZ-LOOP] BlitzSniper M30 monitor iniciado.")

        while self.is_running:
            try:
                # [V110.136] Executa o scan imediatamente e depois aguarda o intervalo
                # Check available slots
                slots = await firebase_service.get_active_slots()
                if bybit_rest_service.execution_mode == "PAPER":
                    occupied_count = len(bybit_rest_service.paper_positions)
                else:
                    occupied_count = sum(1 for s in slots if s.get("symbol"))

                # Regra Elite Slot 1: Só escaneia se o Slot 1 estiver livre (ou se houver menos de 4 ordens)
                # Na verdade, o 'can_open_new_slot' já protege, mas aqui evitamos chamadas de rede desnecessárias.
                slot_1 = slots[0] if len(slots) > 0 else {}
                slot_1_busy = slot_1.get("symbol") is not None
                
                if not slot_1_busy:
                    logger.info("⚡ [BLITZ-SCAN] Iniciando varredura estratégica M30 para o Slot 1 Elite...")
                    await blitz_sniper_agent.scan_and_inject(signal_generator.signal_queue)
                else:
                    logger.debug("⚡ [BLITZ-SCAN] Slot 1 ocupado. Pulando ciclo de varredura.")

                await asyncio.sleep(BLITZ_SCAN_INTERVAL)

                if not self.is_running:
                    break

                # [V110.137] Verifica se ALGUM slot Blitz esta disponivel (1 ou 2)
                slot_1 = next((s for s in slots if s.get("id") == 1), {})
                slot_2 = next((s for s in slots if s.get("id") == 2), {})
                slot_1_busy = bool(slot_1.get("symbol")) and slot_1.get("status") != "EMANCIPATED"
                slot_2_busy = bool(slot_2.get("symbol")) and slot_2.get("status") != "EMANCIPATED"

                if slot_1_busy and slot_2_busy:
                    logger.debug("[BLITZ-LOOP] Slots 1 e 2 ocupados. Aguardando liberacao para novo scan M30.")
                    continue

                # 2. Obtém direção do BTC para filtro de tendência
                deep_macro = await self.get_deep_macro_status()
                btc_direction = deep_macro.get("direction", "LATERAL")
                btc_adx = deep_macro.get("adx", 0.0)

                # 3. Obtém a watchlist (pares ativos do radar)
                from config import settings
                watchlist = getattr(settings, "RADAR_WATCHLIST", [])
                if not watchlist:
                    # Fallback: usa os símbolos mais líquidos
                    watchlist = [
                        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                        "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "ADAUSDT", "MATICUSDT",
                        "DOTUSDT", "LTCUSDT", "UNIUSDT", "ATOMUSDT", "NEARUSDT"
                    ]

                logger.info(f"⚡ [BLITZ-LOOP] Iniciando scan M30 de {len(watchlist)} ativos | BTC: {btc_direction} (ADX={btc_adx:.1f})")

                # 4. Executa o scan do BlitzSniper
                blitz_signals = await blitz_sniper_agent.scan_watchlist(
                    symbols=watchlist,
                    btc_direction=btc_direction,
                    btc_adx=btc_adx,
                )

                if not blitz_signals:
                    logger.debug("⚡ [BLITZ-LOOP] Nenhum setup M30 qualificado neste ciclo.")
                    continue

                # 5. Injeta o melhor sinal na fila de sinais com prioridade alta
                best_blitz = blitz_signals[0]
                symbol = best_blitz["symbol"]

                # Checa cooldown e tocaia ativa antes de enfileirar
                in_cooldown, _ = await self.is_symbol_in_cooldown(symbol)
                if in_cooldown:
                    logger.debug(f"⚡ [BLITZ-LOOP] {symbol} em cooldown. Descartando sinal Blitz.")
                    continue

                # [V110.137 COLLISION-GUARD] Bloqueia se ativo ja esta em qualquer slot ativo
                active_symbols_set = {
                    (s.get("symbol") or "").replace(".P", "").upper()
                    for s in slots if s.get("symbol") and s.get("status") != "EMANCIPATED"
                }
                if symbol.replace(".P", "").upper() in active_symbols_set:
                    logger.warning(f"[V110.137 COLLISION] {symbol} ja ativo em slot. Descartando sinal Blitz.")
                    continue

                if symbol in self.active_tocaias:
                    logger.debug(f"[BLITZ-LOOP] {symbol} ja esta em Tocaia. Descartando.")
                    continue

                # Enriquece o sinal com ID único para rastreamento
                best_blitz["id"] = f"BLITZ_{symbol}_{int(time.time())}"
                best_blitz["reasoning"] = " | ".join(best_blitz.get("reasons", ["BlitzSniper M30"]))
                best_blitz["is_blitz_elite"] = True

                # Coloca na fila com prioridade máxima (-best_blitz["score"] como negativo = maior prioridade)
                self._signal_counter = getattr(self, "_signal_counter", 0) + 1
                await signal_generator.signal_queue.put(
                    (-best_blitz["score"], self._signal_counter, best_blitz)
                )

                msg = (
                    f"⚡ [BLITZ-INJECT] 🎯 {symbol} {best_blitz['side']} injetado na fila | "
                    f"Score: {best_blitz['score']}/100 | Motivo: {best_blitz['reasoning']}"
                )
                logger.info(msg)
                await firebase_service.log_event("BLITZ", msg, "SUCCESS")

            except Exception as e:
                logger.error(f"❌ [BLITZ-LOOP] Erro no scan M30: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(30)

    async def get_deep_macro_status(self):
        """[V110.36.8] Guilhotina Reforçada com SSOT M-ADX (Sem falsos laterais)."""

        adx = getattr(bybit_ws_service, 'btc_adx', 0)
        
        if adx >= 30: regime = "ROARING"
        elif adx >= 25: regime = "TRENDING"
        else: regime = "RANGING"

        variation_1h = bybit_ws_service.btc_variation_1h
        variation_15m = bybit_ws_service.btc_variation_15m
        
        # [V110.116] DYNAMIC ADX THRESHOLD: 25 for Elite Transitions (was 30)
        if adx >= 25:
            # Convergência: Ambos devem apontar para a mesma direção
            if variation_15m > 0 and variation_1h > 0:
                btc_direction = "UP"
            elif variation_15m < 0 and variation_1h < 0:
                btc_direction = "DOWN"
            else:
                # Divergência entre timeframes ou variação nula = Tratado como LATERAL para segurança
                btc_direction = "LATERAL"
                self.last_lateral_at = time.time()
            
            logger.info(f"🔥 [MARKET-REGIME] ADX {adx:.1f} detectado. Direção BTC: {btc_direction} (15m: {variation_15m:.2f}%, 1h: {variation_1h:.2f}%)")
        else:
            btc_direction = "LATERAL"
            self.last_lateral_at = time.time()
            logger.info(f"🧊 [MARKET-REGIME] ADX {adx:.1f} baixo (<25). Mercado LATERAL.")
                
        return {
            "regime": regime,
            "direction": btc_direction,
            "adx": adx,
            "var_15m": variation_15m,
            "var_1h": variation_1h,
            # [V110.36.0] CVD Anti Fake-Out: Fluxo financeiro real do BTC (Vanguard Bypass)
            "cvd_total": bybit_ws_service.get_cvd_score("BTCUSDT"),
            "cvd_5m": bybit_ws_service.get_cvd_score_time("BTCUSDT", 300),
        }

    async def _find_stagnant_slot_for_preemption(self) -> Optional[int]:
        """
        [V110.13.0] SHADOW PREEMPTION FINDER:
        Identifies a "Zombie" slot (ROI -5% to +5%, Time > 45m, Low Gas).
        Returns the slot_id if found, else None.
        """
        try:
            slots = await firebase_service.get_active_slots(force_refresh=True)
            now = time.time()
            
            candidates = []
            for slot in slots:
                slot_id = slot.get("id")
                symbol = slot.get("symbol")
                opened_at = slot.get("opened_at", 0)
                pnl_pct = slot.get("pnl_percent", 0.0)
                
                if not symbol or slot_id not in [1, 2, 3, 4]:
                    continue
                
                # Rule 1: Stagnant ROI (-5% to +5%)
                is_stagnant_roi = abs(pnl_pct) <= 5.0
                
                # Rule 2: Minimum Time (45 minutes = 2700 seconds)
                is_old_enough = (now - opened_at) > 2700
                
                # Rule 3: Low Gas (institutional volume)
                cvd_score = bybit_ws_service.get_cvd_score(symbol)
                is_low_gas = abs(cvd_score) < 15000
                
                if is_stagnant_roi and is_old_enough and is_low_gas:
                    # Score for replacement (lower energy = better candidate)
                    # Energy = (Abs ROI + normalized Gas + Time bonus)
                    # For now, let's just pick the oldest one among candidates
                    candidates.append({
                        "slot_id": slot_id,
                        "symbol": symbol,
                        "opened_at": opened_at,
                        "pnl": pnl_pct,
                        "gas": cvd_score
                    })
            
            if candidates:
                # Sort by opened_at (oldest first)
                candidates.sort(key=lambda x: x["opened_at"])
                target = candidates[0]
                logger.info(f"🧛 [PREEMPTION] Found Zombie Slot {target['slot_id']} ({target['symbol']}). ROI: {target['pnl']:.2f}% | Gas: {target['gas']} | Age: {int((now-target['opened_at'])/60)}m")
                return target["slot_id"]
                
            return None
        except Exception as e:
            logger.error(f"Error finding stagnant slot: {e}")
            return None

    async def _process_single_signal(self, best_signal: dict):
        """
        [V120] Orquestrador Multitenant:
        Despacha o sinal para todos os usuários ativos com cofre autorizado.
        """
        symbol = best_signal["symbol"]
        side = best_signal.get("side", "Buy")
        
        # [MASTER BYPASS] - Se existir OKX Master ou for modo PAPER, ignora os inscritos e executa o sinal na conta Master/Simulada.
        from config import settings
        if settings.OKX_API_KEY_MASTER or settings.BYBIT_EXECUTION_MODE == "PAPER":
            logger.info(f"🚀 [BYPASS MASTER/PAPER] Sinal de {symbol} roteado diretamente para OKX Master/Paper global.")
            await self._run_user_execution_logic(None, {}, best_signal)
            return

        # 1. Busca usuários ativos com cofre
        subscribers = await firebase_service.get_active_subscribers_with_vault()
        if not subscribers:
            logger.warning(f"⚠️ [V120] Nenhum assinante ativo com cofre configurado para {symbol}.")
            return

        logger.info(f"🚀 [V120-DISPATCH] Iniciando despacho de {symbol} {side} para {len(subscribers)} usuários.")

        # 2. Executa em paralelo para cada usuário para evitar atraso (Slippage)
        tasks = []
        for username, user_data in subscribers.items():
            tasks.append(self._execute_for_user(username, user_data, best_signal))
        
        await asyncio.gather(*tasks)

    async def _execute_for_user(self, username: str, user_data: dict, signal: dict):
        """Sub-tarefa de execução isolada por usuário."""
        symbol = signal["symbol"]
        norm_symbol_lock = normalize_symbol(symbol) + "_" + username
        
        # [V120] Isolamento de Processamento por Usuário
        if norm_symbol_lock in self.processing_lock:
            return
            
        self.processing_lock.add(norm_symbol_lock)
        try:
            # 3. Protocolo de Descriptografia "In-Flight"
            vault_pass = auth_service.get_vault_session(username)
            if not vault_pass:
                logger.warning(f"🔒 [V120-AUTH] Usuário {username} sem sessão de cofre ativa na RAM. Ignorando.")
                return

            vault_blob = user_data.get("bybit_vault", {})
            api_key = crypto_service.decrypt(vault_blob.get("key"), vault_pass)
            api_secret = crypto_service.decrypt(vault_blob.get("secret"), vault_pass)

            if not api_key or not api_secret:
                logger.error(f"❌ [V120-CRYPTO] Falha ao descriptografar chaves de {username}.")
                return

            # 4. Injeção de Credenciais Dinâmicas
            # Criamos um contexto de execução específico para este usuário
            user_credentials = {
                "api_key": api_key,
                "api_secret": api_secret,
                "username": username
            }

            # A lógica original do Captain continua aqui, mas operando com credenciais injetadas
            # VOU IMPLEMENTAR A LÓGICA DE FILTRAGEM (Vanguard, ADX, etc) DENTRO DESTE CONTEXTO
            await self._run_user_execution_logic(username, user_credentials, signal)

        finally:
            self.processing_lock.discard(norm_symbol_lock)

    async def _run_user_execution_logic(self, username: str, credentials: dict, best_signal: dict):
        """Lógica de filtragem e execução original do Captain adaptada para o usuário."""
        symbol = best_signal["symbol"]
        score = best_signal["score"]
        side = best_signal.get("side", "Buy")
        norm_symbol_lock = normalize_symbol(symbol) + "_" + str(username)
        
        try:
            # [V120] Verificação de Slots por Usuário
            # O sistema agora busca slots privados do usuário no Firestore
            slots = await firebase_service.get_active_slots(username=username)
            occupied_count = sum(1 for s in slots if s.get("symbol"))
            
            if occupied_count >= 4:
                # logger.debug(f"⏭️ [V120] Usuário {username} sem slots disponíveis.")
                return

            # [V110.62] SYNC BIASES (Adaptive Weighting)
            # [V110.62] SYNC BIASES (Adaptive Weighting)
            if time.time() - self.last_bias_sync > 600: # Sync a cada 10 min
                biases = await firebase_service.get_system_bias()
                if biases:
                    self.system_biases.update(biases)
                    self.last_bias_sync = time.time()
                    logger.info(f"📊 [ADAPTIVE-WEIGHTING] Biases sincronizados: {self.system_biases}")

            signal_layer = best_signal.get("layer", "MOMENTUM")
            
            # [V110.62] APPLY ADAPTIVE WEIGHTING
            # O Score original é re-calculado baseado na confiança atual dos agentes
            fleet_intel = best_signal.get("fleet_intel", {})
            if fleet_intel:
                w_macro = self.system_biases.get("macro_weight", 1.0)
                w_whale = self.system_biases.get("whale_weight", 1.0)
                w_smc = self.system_biases.get("smc_weight", 1.0)
                
                # Penalidade/Bônus Dinâmico
                # Se um agente está viciado (peso < 1), o score final cai.
                original_score = best_signal["score"]
                
                # Exemplo: Se Macro errou muito (weight 0.5) e o sinal depende muito de Macro (intel 100),
                # o score sofre uma redução proporcional.
                penalty = 0
                if fleet_intel.get("macro", 50) > 70 and w_macro < 1.0: penalty += 5
                if fleet_intel.get("micro", 50) > 70 and w_whale < 1.0: penalty += 5
                if fleet_intel.get("smc", 50) > 70 and w_smc < 1.0: penalty += 5
                
                bonus = 0
                if fleet_intel.get("macro", 50) > 80 and w_macro > 1.0: bonus += 3
                
                score = max(0, min(100, original_score - penalty + bonus))
                if score != original_score:
                    logger.info(f"⚖️ [V110.62 WEIGHTING] Score ajustado: {original_score} -> {score} (Penalty: {penalty}, Bonus: {bonus})")
            else:
                score = best_signal["score"]

            strategy = "SWING"
            
            # [V110.20.0] Shadow Strike Desativado
            strategy = "SWING"

            
            from services.signal_generator import signal_generator
            try:
                regime_data = await signal_generator.detect_market_regime(symbol)
                market_regime = regime_data.get('regime', 'TRANSITION')
            except Exception:
                market_regime = "TRANSITION"
            
            is_market_ranging = market_regime == "RANGING"

            # [V67.3] 🛑 MASTER 3D FILTER & DECORRELATION SHIELD
            # User: "Short se Down, Long se Up. Se Lateral, só se Desgrudado."
            deep_macro = await self.get_deep_macro_status()
            btc_dir = deep_macro.get("direction", "LATERAL")
            current_btc_adx = deep_macro.get("adx", 0) 
            
            # [V110.137] BLITZ-DETECTION Precoce
            # Ensure all M30 signals are treated as Blitz for priority/bypass
            is_blitz = best_signal.get("is_blitz", False) or best_signal.get("timeframe") == "30" or best_signal.get("layer") == "BLITZ"
            is_decorrelated = best_signal.get("decorrelation", {}).get("is_active", False)

            # --- [V110.128] SENTINEL PROTOCOL: LATERAL BLOCK + ELITE NECTAR BYPASS ---
            if btc_dir == "LATERAL":
                # Busca DNA do ativo para verificar se tem permissão de Elite Bypass
                lib_dna_lateral = await librarian_agent.get_asset_dna(symbol)
                nectar_seal_lateral = lib_dna_lateral.get("nectar_seal", "🛡️ VANGUARD")
                is_elite_nectar = "ELITE" in nectar_seal_lateral or "NECTAR" in nectar_seal_lateral
                is_elite_score = score >= 95
                
                # [V110.128] ADX SLOPE GUARD: Mesmo sinais Elite devem ter "pressão" crescendo
                adx_slope = current_btc_adx - self.prev_btc_adx
                self.prev_btc_adx = current_btc_adx # Update for next signal
                
                is_warming_up = adx_slope > 0 or current_btc_adx >= 25
                
                # [V110.137] Blitz Sniper ignora o ADX Slope Guard em laterais
                can_bypass_lateral = (is_elite_nectar or is_elite_score) and is_warming_up
                if is_blitz or is_decorrelated or bybit_rest_service.execution_mode == "PAPER":
                    can_bypass_lateral = True
                    logger.info(f"⚡ [BYPASS-LATERAL] {symbol} ({side}) ignorando trava lateral Sentinel (Paper={bybit_rest_service.execution_mode == 'PAPER'}, Decor={is_decorrelated}).")

                if can_bypass_lateral:
                    bypass_reason = "BlitzMode" if is_blitz else (f"Seal={nectar_seal_lateral}" if is_elite_nectar else f"Score={score}")
                    msg = (
                        f"💎 [V110.118 ELITE-BYPASS] {symbol} ({side}) | BTC LATERAL mas sinal de {bypass_reason}. "
                        f"ADX-Slope: {adx_slope:+.2f}. Caçada autorizada!"
                    )
                    logger.info(msg)
                    await firebase_service.log_event("SENTINELA", msg, "SUCCESS")
                elif bybit_rest_service.execution_mode == "PAPER":
                    logger.info(f"💎 [PAPER-TEST-FIRE] Forçando bypass lateral para {symbol} em modo PAPER para forçar disparo.")
                else:
                    if not is_warming_up and (is_elite_nectar or is_elite_score):
                        block_reason = f"ADX Slope Estagnado ({adx_slope:+.2f}) e ADX Baixo ({current_btc_adx:.1f})"
                    else:
                        block_reason = f"Score {score} < 95 ou Seal {nectar_seal_lateral} insuficiente"
                        
                    msg = (
                        f"🛡️ [V110.128 LATERAL-BLOCK] {symbol} ({side}) negado: {block_reason}. "
                        f"Evitando armadilha de lateralidade sem força."
                    )
                    logger.warning(msg)
                    await firebase_service.log_event("SENTINELA", msg, "WARNING")
                    await firebase_service.update_signal_outcome(best_signal["id"], "LAZY_LATERAL_BLOCK")
                    self.active_tocaias.discard(symbol)
                    return

            # --- [V110.100.1] WHALE BYPASS (APENAS SE MERCADO GLOBAL PERMITIR) ---
            if current_btc_adx < 18:
                # [V110.136] BLITZ BYPASS: Sinais M30 (Blitz) ignoram o bloqueio de mercado lateral.
                # is_blitz unified from above
                
                active_slots_data = await firebase_service.get_active_slots()
                if bybit_rest_service.execution_mode == "PAPER":
                    occ_count = len(bybit_rest_service.paper_positions)
                else:
                    occ_count = sum(1 for s in active_slots_data if s.get("symbol"))
                
                local_cvd = bybit_ws_service.get_cvd_score(symbol)
                is_whale_strong = abs(local_cvd) >= 15000 or score >= 88
                
                if (occ_count < 2 and is_whale_strong) or is_blitz or is_decorrelated or bybit_rest_service.execution_mode == "PAPER":
                    if is_blitz:
                        msg = f"⚡ [BLITZ-PRIORITY] {symbol} ({side}) ignorando bloqueio ADX lateral (M30 Blitz Mode)."
                    elif bybit_rest_service.execution_mode == "PAPER":
                        msg = f"💎 [PAPER-BYPASS] ADX {current_btc_adx:.1f} < 18, mas {symbol} ({side}) ignorando bloqueio ADX (Paper mode ativo)."
                    elif is_decorrelated:
                        msg = f"💎 [DECOR-BYPASS] ADX {current_btc_adx:.1f} < 18, mas {symbol} ({side}) ignorando bloqueio ADX (Ativo Descorrelacionado)."
                    else:
                        msg = f"🐋 [WHALE-BYPASS] ADX {current_btc_adx:.1f} < 18, mas {symbol} ({side}) tem CVD ({local_cvd}) / Score Elite. Slots Livres! Permitindo caçada."
                    
                    logger.info(msg)
                    await firebase_service.log_event("CAPTAIN", msg, "SUCCESS")
                else:
                    msg = f"🛡️ [ADX-BLOCK] {symbol} ({side}) | M-ADX={current_btc_adx:.1f}<18 | Sem cota Whale ou CVD baixo."
                    logger.warning(msg)
                    await firebase_service.log_event("SENTINELA", msg, "WARNING")
                    if best_signal.get("id"):
                        await firebase_service.update_signal_outcome(best_signal["id"], "ABSOLUTE_LATERAL_BLOCK")
                    self.active_tocaias.discard(symbol)
                    return


            # [LIBRARIAN-EARLY-SYNC] V2.1 - Busca DNA do ativo precocemente para travar o Elite Bypass
            lib_dna = await librarian_agent.get_asset_dna(symbol)
            nectar_seal = lib_dna.get("nectar_seal", "🛡️ VANGUARD")

            # [V110.64.0] VANGUARD QUALITY FILTER (Score >= 80)
            # is_blitz unified from above
            if "VANGUARD" in nectar_seal and score < 80 and not is_blitz and bybit_rest_service.execution_mode != "PAPER":
                msg = f"🛡️ [VANGUARD-QUALITY-BLOCK] {symbol} Score {score} < 80. Ativos Vanguard exigem confiança mínima. Abortando."
                logger.warning(msg)
                await firebase_service.log_event("CAPTAIN", msg, "INFO")
                if best_signal.get("id"):
                    await firebase_service.update_signal_outcome(best_signal["id"], "VANGUARD_LOW_SCORE")
                self.active_tocaias.discard(symbol)
                return
            elif is_blitz and "VANGUARD" in nectar_seal:
                logger.info(f"⚡ [BLITZ-VANGUARD-BYPASS] {symbol} ({score}) permitido apesar de ser Vanguard (Blitz Sniper prioritário).")

            # [V110.38.0] ABSOLUTE TRAP SHIELD - Bloqueia QUALQUER entrada em moedas classificadas como TRAP
            if "TRAP" in nectar_seal and bybit_rest_service.execution_mode != "PAPER":
                msg = f"💀 [LIBRARIAN-TRAP-SHIELD] Bloqueio total {symbol}: Ativo classificado como TRAP ZONE pelo Bibliotecário. Ordem abortada."
                logger.warning(msg)
                await firebase_service.log_event("CAPTAIN", msg, "WARNING")
                if best_signal.get("id"):
                    await firebase_service.update_signal_outcome(best_signal["id"], "LIBRARIAN_TRAP_BLOCK")
                self.active_tocaias.discard(symbol)
                return
            elif "TRAP" in nectar_seal and bybit_rest_service.execution_mode == "PAPER":
                logger.info(f"💎 [PAPER-TEST-FIRE] Ignorando TRAP SHIELD para {symbol} em modo PAPER para forçar disparo.")

            # --- [V110.135] QUARTERMASTER ARMORY CHECK ---
            armory = await quartermaster_agent.check_armory(
                symbol=symbol,
                lib_dna=lib_dna,
                market_data={"btc_adx": current_btc_adx}
            )
            
            if armory.get("block_reason"):
                msg = f"🛡️ [QUARTERMASTER-BLOCK] {symbol} ({side}) negado: {armory['block_reason']}"
                logger.warning(msg)
                await firebase_service.log_event("QUARTERMASTER", msg, "WARNING")
                await firebase_service.update_signal_outcome(best_signal["id"], "QUARTERMASTER_BLOCK")
                self.active_tocaias.discard(symbol)
                return
            
            # Injeta parâmetros de alavancagem adaptativa no sinal
            best_signal["leverage"] = armory["leverage"]
            best_signal["margin_multiplier"] = armory["margin_multiplier"]
            best_signal["wick_intensity"] = armory["wick_intensity"]
            logger.info(f"⚓ [QUARTERMASTER] {symbol} alavancagem definida em {armory['leverage']}x (Multiplier: {armory['margin_multiplier']}x)")

            # --- PHASE 2: TRENDING MARKET (UP/DOWN) ---
            is_counter_trend = (btc_dir == "UP" and side.upper() == "SELL") or \
                               (btc_dir == "DOWN" and side.upper() == "BUY")
                
            # [V110.12.9] ABSOLUTE DIRECTION SHIELD (Anti-Massacre)
            # Se BTC está caindo forte ou subindo forte, o bypass de decorrelação é proibido para sinais normais.
            # Apenas SHADOW STRIKE de Elite (Score 99) pode furar essa trava.
            btc_variation_15m = deep_macro.get("var_15m", 0)
            is_violent_trend = abs(btc_variation_15m) >= 0.5
            
            if is_counter_trend and bybit_rest_service.execution_mode != "PAPER":
                can_bypass = False
                # [V110.128] CONTRATENDÊNCIA VIOLENTA: Bloqueio total se var_15m > 0.6%
                if abs(btc_variation_15m) >= 0.6:
                    can_bypass = False
                    logger.warning(f"🛑 [VIOLENT-TREND-BLOCK] {symbol} {side} contra tendência violenta do BTC ({btc_variation_15m:.2f}% em 15m). Riscos de massacre ignorados.")
                elif score >= 95 and "NECTAR" in nectar_seal:
                    # [V110.30.1] CONTRATENDÊNCIA: Apenas Sinais ELITE (Score >= 95) COM selo Néctar podem furar.
                    can_bypass = True
                    logger.info(f"💎 [ELITE-BYPASS] {symbol} furando contra-tendência BTC {btc_dir} com Score {score} e selo Néctar.")
                else:
                    can_bypass = False
                    if score >= 95:
                        logger.warning(f"🛑 [ABSOLUTE DIRECTION BLOCK] {symbol} {side} negado: Tem Score {score} mas faltando selo Néctar (Selo atual: {nectar_seal}).")
                    else:
                        logger.warning(f"🛑 [ABSOLUTE DIRECTION BLOCK] {symbol} {side} negado: Contra tendência BTC {btc_dir} (Score {score} < 95).")
                    
                if not can_bypass:
                    msg = f"🚫 [MACRO 110.128 BLOCK] Bloqueado {symbol} ({side}) contra a tendência BTC {btc_dir} (ADX={deep_macro['adx']:.1f} | Var15m={btc_variation_15m:.2f}%)."
                    logger.warning(msg)
                    await firebase_service.log_event("CAPTAIN", msg, "WARNING")
                    await firebase_service.update_signal_outcome(best_signal["id"], "MACRO_3D_DIRECTION_BLOCK")
                    self.active_tocaias.discard(symbol)
                    return
                else:
                    logger.info(f"🎯 [V110.128 BYPASS] Permitindo {symbol} ({side}) contra-tendência por critérios de Elite (Score >= 95).")
            else:
                logger.info(f"✅ [V67.3 TREND] {symbol} {side} a favor da tendência BTC {btc_dir}.")

            # [V42.0] Extract specialized pattern tags from signal indicators
            pattern_data = best_signal.get("indicators", {}).get("v42_pattern", {})
            if pattern_data.get("detected"):
                best_signal["v42_tag"] = pattern_data.get("type")
                best_signal["is_ranging_sniper"] = True
                
            if signal_layer == "MOMENTUM":
                is_swing_macro = best_signal.get("is_swing_macro", False)
                is_decorrelated = best_signal.get("decorrelation", {}).get("is_active", False)
                
                if is_decorrelated:
                    signal_layer = "SNIPER"
                    logger.info(f"🎯 [V42.0] DECORRELATION promovido: {symbol} ({score})")
                elif is_swing_macro:
                    signal_layer = "SNIPER"
                    logger.info(f"🌊 [V38.0] MACRO SWING promovido: {symbol} ({score})")
                else:
                    # [V110.12.8] RE-VERIFY SYMBOL LOCK JUST BEFORE EXECUTION (Double Shield)
                    if bybit_rest_service.execution_mode == "PAPER":
                        if any(p.get("symbol") == symbol for p in bybit_rest_service.paper_positions):
                            logger.error(f"🛑 [CRITICAL-DUP-SHIELD] {symbol} detectado em PaperPositions durante processamento. Abortando execuçao tardia.")
                            self.active_tocaias.discard(symbol)
                            return

                    allow_momentum = False
                    if market_regime == "RANGING":
                        # [LATERALIZAÇÃO] Reduzindo rigor: Permite Momentum se Score >= 80 para evitar slots vazios
                        if score >= 90: # [V42.9] No Momentum in Ranging for low score
                            # [V110.64.0] RANGING MOMENTUM ELITE bloqueado se lateral e não-shadow
                            if current_btc_adx < 18 and not best_signal.get("is_shadow_strike", False):
                                allow_momentum = False
                                logger.info(f"🔒 [RANGING-LATERAL-BLOCK] {symbol} Score Elite {score} bloqueado: ADX {current_btc_adx:.1f} < 18, nao Shadow.")
                            else:
                                allow_momentum = True
                                logger.info(f"🚧 [{symbol}] RANGING MARKET: Permitido via Momentum ELITE {score}")
                        else:
                            allow_momentum = False
                            logger.info(f"⏭️ {symbol} rejeitado: Momentum no RANGING exige Score >= 90.")
                    else:
                        allow_momentum = True # Se não for RANGING, Momentum é liberado
                        
                    from config import settings
                    if settings.BYBIT_EXECUTION_MODE == "PAPER" and score >= 80:
                        allow_momentum = True
                    if not allow_momentum:
                        msg = f"⏭️ {symbol} rejeitado: SCORE={score} em LAYER={signal_layer} | Regime: {market_regime} | ADX: {current_btc_adx:.1f}"
                        logger.info(msg)
                        await firebase_service.update_signal_outcome(best_signal["id"], "MOMENTUM_BLOCKED")
                        self.active_tocaias.discard(symbol) # [FIX] Liberar tocaia no descarte
                        return

            # --- [LATERALIZAÇÃO INJECTION V41.2] ---
            is_elite_ranging = False
            if market_regime == "RANGING":
                logger.info(f"🚧 [RANGING GUARD]: Sinal {symbol} injetado com tag is_market_ranging = True")
                if "indicators" not in best_signal:
                    best_signal["indicators"] = {}
                best_signal["is_market_ranging"] = True
                best_signal["indicators"]["pattern"] = best_signal["indicators"].get("pattern", "") + "_RANGING"
                
                # [V41.5] SNIPER RANGING: Agora mesmo sinais de elite passam pelo Tocaia Sniper
                # para garantir preço de entrada ideal (precisão cirúrgica).
                if score >= 85:
                    is_elite_ranging = True
                    logger.info(f"🎯 [SNIPER RANGING V41.5] {symbol} score {score} buscando entrada de precisão.")

            # side is already defined at the top
            
            
            if market_regime == "RANGING":
                logger.info(f"🔄 [V33.0] REVERSE SNIPER SUSPENSO: Seguindo direção original {side} para {symbol}.")

            in_cooldown, remaining = await self.is_symbol_in_cooldown(symbol)
            if in_cooldown:
                if score >= 95:
                    logger.info(f"⚡ V12.5 ELITE BYPASS: {symbol} score {score} furando cooldown!")
                    # Elite signal bypasses cooldown - continues execution
                else:
                    logger.info(f"⏱️ {symbol} no cooldown (score {score} < 95). Abortando.")
                    await firebase_service.update_signal_outcome(best_signal["id"], "COOLDOWN_SKIP")
                    if slot_id: await firebase_service.free_slot(slot_id, "Cooldown Skip")
                    return

            # 1.2 [V43.0] Get Fleet Consensus
            consensus = await self._get_fleet_consensus(best_signal)
            
            # [V56.0] Enrich signal with unified intelligence for the UI
            best_signal["unified_confidence"] = consensus.get("unified_confidence", 50)
            best_signal["fleet_intel"] = consensus.get("intel", {})
            
            # [V6.2] Anti-Trap Pivot Protocol
            fleet_intel = consensus.get("intel", {})
            trap_risk = fleet_intel.get("trap_risk", False)
            suggested_side = fleet_intel.get("suggested_side")
            
            # [V110.137] Ensure we only pivot if it is definitively ranging
            if trap_risk and is_market_ranging and suggested_side and suggested_side.lower() != side.lower():
                msg = f"🔄 [V6.2 PIVOT] Trap detectada ({fleet_intel.get('trap_reason')}). Invertendo {side} para {suggested_side}!"
                logger.warning(msg)
                await firebase_service.log_event("SNIPER", msg, "SUCCESS")
                side = suggested_side
                best_signal["side"] = side
                best_signal["is_reverse_sniper"] = True # Mark for tighter protection in SL logic
                consensus["approved"] = True # Override approval for the pivot trade
            
            if not consensus["approved"]:
                reason = consensus["reason"]
                logger.info(f"🚫 [FLEET] {symbol} REJEITADO: {reason}")
                # [V110.27.0] Log critical rejection to events for user visibility
                await firebase_service.log_event("SENTINELA", f"Caçada abortada para {symbol}: {reason}", "WARNING")
                await firebase_service.update_signal_outcome(best_signal["id"], f"FLEET_REJECTED: {reason}")
                self.active_tocaias.discard(symbol)
                return
            
            # Proceed with Whale-Bonus and Space Checks [V110.12.9]
            # Redundant Lateral Block removed to allow trending market entries.
            
            fleet_intel = consensus["intel"]
            
            # [V68.0] ENGINE SPACE CHECK (POTENTIAL AUDIT)
            # Only proceed if there is enough "room to move" until next resistance/liquidity zone.
            # [V110.16.0] MODO ASSALTO REMOVIDO: Todos os sinais (mesmo Score 95+) devem passar pela auditoria de espaço.
            current_p_audit = bybit_ws_service.get_current_price(symbol)
            if current_p_audit > 0:
                space_audit = await self._check_engine_space(symbol, side, current_p_audit)
                # [V96.2] Engine Space Bypass: Elite Signals or Paper Mode are allowed to take the risk
                from config import settings
                if not space_audit.get("valid", True) and settings.BYBIT_EXECUTION_MODE != "PAPER":
                    msg = f"🚫 [V68.0 ENGINE SPACE] Rejeitado: Espaço de manobra insuficiente."
                    logger.warning(msg)
                    await firebase_service.update_signal_outcome(best_signal["id"], "ENGINE_SPACE_REJECTED")
                    self.active_tocaias.discard(symbol)
                    return

            is_mean_rev = best_signal.get("is_mean_reversion", False)
            trap_exploited = best_signal.get("trap_exploited", False)
            is_trend_surf = best_signal.get("is_trend_surf", False)
            
            # [V42.5] Mark as TOCAIA immediately when starting to hunt
            if "indicators" not in best_signal:
                best_signal["indicators"] = {}
            original_pattern = best_signal["indicators"].get("pattern", "STANDARD")
            best_signal["indicators"]["pattern"] = "TOCAIA"
            best_signal["indicators"]["original_pattern"] = original_pattern
            
            # Persist TOCAIA status in Firestore immediately
            await firebase_service.update_signal_outcome(
                best_signal["id"], 
                "HUNTING", 
                {"indicators.pattern": "TOCAIA"}
            )

            # [V110.141] Injetar no RTDB para visibilidade instantânea no Cockpit
            try:
                from services.signal_generator import signal_generator
                asyncio.create_task(signal_generator._sync_radar_rtdb())
            except Exception as e:
                logger.warning(f"Failed to sync radar RTDB for TOCAIA: {e}")

            # [V110.113] AMBUSH MODE DUAL: ATAQUE DIRETO vs EMBOSCADA
            execution_style = best_signal.get("execution_style", "ATTACK")
            current_adx = best_signal.get("current_adx", 0)
            
            # Buscar Librarian DNA para avaliação de risco (usa import global — sem import local)
            lib_dna = await librarian_agent.get_asset_dna(symbol)
            
            # DETERMINAR MODO DE ENTRADA
            # Modo DIRETO (sem ambush) para sinais elite com fluxo baleia real
            local_cvd = best_signal.get("cvd_local", 0)
            is_high_risk = lib_dna.get("status") == "HIGH_RISK"
            
            should_bypass_ambush = (
                score >= 92 and
                abs(local_cvd) >= 30000 and
                current_btc_adx >= 30 and
                not is_high_risk
            )
            
            if should_bypass_ambush:
                msg = (
                    f"⚡ [V110.113 DIRECT-ENTRY] {symbol} ({side}) | "
                    f"Score {score} + CVD {local_cvd:.0f} + ADX {current_btc_adx:.1f} | "
                    f"Entrada direta — bypassando Tocaia!"
                )
                logger.info(msg)
                await firebase_service.log_event("CAPTAIN", msg, "SUCCESS")
                await firebase_service.update_signal_outcome(best_signal["id"], "DIRECT_ENTRY")
                best_signal["execution_style"] = "DIRECT"
                execution_style = "DIRECT"
            elif execution_style == "AMBUSH":
                # MODO EMBOSCADA: Aguarda a "Lambida" no preço (Wick Zone) antes de validar estrutura
                msg = f"🎯 [AMBUSH MODE] Tocaia ativada para {symbol} ({side}). Aguardando lambida no preço... (ADX={current_adx:.1f})"
                logger.info(msg)
                await firebase_service.log_event("CAPTAIN", msg, "SUCCESS")
                
                # Loop de monitoramento de Tocaia (Espera o recuo estratégico)
                triggered = await self._wait_for_ambush_trap(symbol, side, best_signal)
                if not triggered:
                    msg = f"⏱️ [AMBUSH TIMEOUT] Preço não 'lambeu' a zona de entrada para {symbol}. Abortando Tocaia."
                    logger.warning(msg)
                    await firebase_service.update_signal_outcome(best_signal["id"], "AMBUSH_TIMEOUT")
                    # Liberamos o slot interno de monitoramento
                    self.active_tocaias.discard(symbol)
                    return
                
                logger.info(f"🔥 [AMBUSH-TRIGGERED] {symbol} {side} lambeu a zona de emboscada! Prosseguindo para validação final.")
                # Se disparou a emboscada, agora validamos o resto do protocolo normalmente

            # [V110.24.0] STRONG TREND ACELERATOR: ADX >= 50 = tendência forte confirmada.
            # Em tendências fortes, pullback e confirmação de CVD são redundantes — o momentum É a entrada.
            strong_trend_bypass = current_btc_adx >= 50 and score >= 75

            if strong_trend_bypass:
                logger.info(f"🚀 [V110.24.0 ACELERATOR] {symbol} ADX={current_btc_adx:.1f} Score={score}. Pulando validadores — capturando o momentum da tendência!")
                await firebase_service.update_signal_outcome(best_signal["id"], "STRONG_TREND_ACELERATOR")
                best_signal["adaptive_sl"] = 0
                best_signal["indicators"]["pattern"] = "TREND_SURF"
            else:
                # [V110.17.0] THE EQUALIZER: Pullback Hunter para precisão de entrada.
                price_check = await self._validate_price_structure(symbol, side, signal_data=best_signal)

                if price_check["confirmed"]:
                    current_pattern = best_signal.get("indicators", {}).get("pattern", "")
                    new_pattern = "DECORRELATION_TOCAIA" if "decorrelation" in current_pattern.lower() else "TOCAIA"
                    best_signal["indicators"]["pattern"] = new_pattern

                if not price_check["confirmed"]:
                    rejection = price_check.get("rejection_type", "UNKNOWN")
                    logger.info(f"⏭️ [PULLBACK HUNTER] {symbol} REJEITADO: {rejection}")
                    await firebase_service.update_signal_outcome(best_signal["id"], f"{rejection}")
                    self.active_tocaias.discard(symbol)
                    return

                await firebase_service.update_signal_outcome(
                    best_signal["id"],
                    "PRICE_STRUCTURE_OK",
                    {"indicators.pattern": best_signal["indicators"]["pattern"]}
                )
                best_signal["adaptive_sl"] = price_check.get("adaptive_sl", 0)

                # [V41.5] Needle Flip: Confirmação de fluxo CVD + MSS.
                flip_confirmed = await self._wait_for_needle_flip(symbol, side, max_wait=10, signal_data=best_signal)

                if not flip_confirmed:
                    logger.info(f"⏭️ [NEEDLE FLIP] {symbol} não confirmou exaustão CVD+Volume.")
                    await firebase_service.update_signal_outcome(best_signal["id"], "NEEDLE_FLIP_FAIL")
                    return
                
            await firebase_service.update_signal_outcome(best_signal["id"], "NEEDLE_FLIP_OK")
            logger.info(f"🎯 V36.4 PULLBACK ALVO PRONTO: {symbol}")
            await firebase_service.update_signal_outcome(best_signal["id"], "PICKED")
            
            reasoning = best_signal.get("reasoning", "High Momentum")
            pensamento = f"V33.0 Pullback Hunter: Price Structure OK + Needle Flip OK. {reasoning} | Score: {score} | Fleet: {fleet_intel.get('sentiment', 'N/A')}"
            
            if is_mean_rev:
                pensamento = f"🧲 [REVERSÃO À MÉDIA] {symbol} MKT Direto. {reasoning} | Score: {score}"
            elif trap_exploited:
                pensamento = f"🦇 [TRAP EXPLOITATION] {symbol} Retail Hunter MKT. {reasoning} | Score: {score}"
            elif is_trend_surf:
                pensamento = f"🏄 [TREND SURFER] {symbol} Surfando Momentum Macro! {reasoning} | Score: {score}"
            elif best_signal.get("is_reverse_sniper"):
                pensamento = f"🔄 REVERSE SNIPER (Fading): {pensamento}"

            norm_symbol_ac = normalize_symbol(symbol)
            sym_trades = self.daily_symbol_trades.get(norm_symbol_ac, {'count': 0, 'first_trade_at': 0})
            if time.time() - sym_trades.get('first_trade_at', 0) > 86400:
                sym_trades = {'count': 0, 'first_trade_at': time.time()}
            if sym_trades['count'] >= 3:
                logger.info(f"🚫 [ANTI-CONCENTRATION] {symbol} bloqueado (limite 3 trades/dia).")
                await firebase_service.update_signal_outcome(best_signal["id"], "CONCENTRATION_BLOCK")
                return
                
            # [V110.12.10] ATOMIC SLOT RE-VERIFICATION (Anti-Slot Overwrite)
            # Antes de enviar o sinal para o Bankroll, verificamos se o slot ainda está LIVRE no Firebase.
            # Isso evita que o sinal 'atropelado' substitua uma ordem que acabou de entrar.
            slot_type = best_signal.get("slot_type", strategy)
            slot_id = await bankroll_manager.can_open_new_slot(symbol=symbol, slot_type=slot_type)
            if not slot_id:
                logger.warning(f"🚨 [V110.12.10 ATOMIC LOCK] {symbol} finalizou Tocaia, mas slot ocupado ou indisponível. Abortando.")
                await firebase_service.update_signal_outcome(best_signal["id"], "ATOMIC_SLOT_LOCK_REJECT")
                return
            
            # Verificação Redundante de Segurança: Símbolo Único Global
            active_slots = await firebase_service.get_active_slots(force_refresh=True)
            if any(s.get("symbol") == symbol for s in active_slots):
                logger.warning(f"🚨 [V110.12.10 SYMBOL LOCK] {symbol} já está em um slot. Abortando duplicata tardia.")
                await firebase_service.update_signal_outcome(best_signal["id"], "SYMBOL_ALREADY_ACTIVE")
                return
                
            # [V110.62] CORRELATION SHIELD: Proteção contra Risco Espelhado
            # Não permitimos abrir ordens em ativos que se movem de forma idêntica aos que já temos em aberto.
            # Isso impede que um único movimento do mercado (ex: crash de ALTs) liquide múltiplos slots simultaneamente.
            for slot in active_slots:
                active_sym = slot.get("symbol")
                if active_sym and active_sym != symbol:
                    correlation = bybit_ws_service.get_correlation(active_sym, symbol)
                    if abs(correlation) >= 0.85:
                        logger.warning(f"🛡️ [V110.62 CORRELATION-SHIELD] Bloqueando entrada em {symbol}. Correlação de {correlation:.2f} com {active_sym} (Limite: 0.85).")
                        await firebase_service.update_signal_outcome(best_signal["id"], f"CORRELATION_BLOCK_{active_sym}")
                        return
                
            # [V110.61] REGISTRO DE GÊNESE PREPARATÓRIO
            # Somente vinculamos o Genesis de fato quando a ordem for confirmada pelo motor.
            genesis_payload = {
                "symbol": symbol,
                "side": side,
                "opened_at": time.time(),
                "score": score,
                "pensamento": pensamento,
                "strategy": strategy,
                "fleet_intel": fleet_intel,
                "unified_confidence": best_signal.get("unified_confidence", 50),
                "layer": signal_layer,
                "agent_captain": "v110.137.Elite",
                "market_regime": market_regime,
                "btc_adx_at_entry": current_btc_adx
            }
            best_signal["genesis_payload"] = genesis_payload
                
            order = await bankroll_manager.open_position(
                symbol=symbol,
                side=side,
                pensamento=pensamento,
                slot_type=slot_type,  # Usando o slot_type determinado acima
                signal_data=best_signal,
                target_slot_id=slot_id
            )
            
            if order:
                self.last_traded_symbol = symbol
                sym_trades['count'] += 1
                if sym_trades['first_trade_at'] == 0:
                    sym_trades['first_trade_at'] = time.time()
                self.daily_symbol_trades[norm_symbol_ac] = sym_trades
                logger.info(f"✅ SNIPER SHOT DEPLOYED: {symbol} (Slot {slot_id})")
                
                # [HERMES TELEGRAM] Alerta de Nova Ordem
                try:
                    from services.telegram_service import telegram_service
                    await telegram_service.send_message(f"🎯 <b>NOVA ORDEM ABERTA</b>\nPar: {symbol}\nEstratégia: {slot_type}")
                except:
                    pass
            else:
                logger.warning(f"❌ SNIPER SHOT FAILED para {symbol}")

        except Exception as e:
            import traceback as _tb
            err_detail = _tb.format_exc()
            logger.error(f"💥 [V110.118 CAPTAIN-CRASH] Erro crítico na Tocaia {symbol}: {e}\n{err_detail}")
            # [V110.118] UI HEALTH: Push erro crítico para o Dashboard sem Telegram
            try:
                await firebase_service.log_event(
                    "CAPTAIN_CRITICAL",
                    f"💥 CRASH na Tocaia {symbol}: {type(e).__name__}: {e}",
                    "ERROR"
                )
            except Exception:
                pass
        finally:
            self.active_tocaias.discard(symbol)
            self.processing_lock.discard(norm_symbol_lock) # [V110.25.6] LIBERA A TRAVA PARA O PRÓXIMO SINAL
            logger.info(f"🏁 [TOCAIA ENCERRADA] {symbol} dispensado. (Restantes: {len(self.active_tocaias)})")

    async def monitor_active_positions_loop(self):
        """
        [V16.5] DECENTRALIZED: This loop now simply monitors sub-agent health.
        Actual management is handled by FleetAudit.
        """
        from services.agents.fleet_audit import fleet_audit
        
        logger.info("⚓ [V27.2] Captain Management Loop ACTIVE (FleetAudit only).")
        
        # Start Sub-Agent
        await fleet_audit.start()
        
        while self.is_running:
            try:
                # [V20.5] Calendar Reminders Loop (Temporariamente desativado para evitar flood de erro 'invalid_grant')
                # events = await google_calendar_service.list_upcoming_events(max_results=5)
                # now = datetime.utcnow()
                # for event in events:
                #    ...
                pass
                
                # [V56.0] On-Chain Whale Watcher Refresh (approx every 10 min)
                if (time.time() - self.last_onchain_refresh) > 600:
                    from services.agents.onchain_whale_watcher import on_chain_whale_watcher
                    await on_chain_whale_watcher.refresh_alerts()
                    self.last_onchain_refresh = time.time()
                    logger.info("🐋 [V56.0] On-Chain alerts refreshed.")
                
                # [V57.0] Active Decorrelation Swap Check (every 30s approx)
                if (time.time() - self.last_decorrelation_swap) > 30:
                    await self._decorrelation_swap_check()
                    self.last_decorrelation_swap = time.time()
                
                await asyncio.sleep(30) # Reduced from 60s for faster reactivity in V57.0
            except Exception as e:
                logger.error(f"Captain Pulse Error: {e}")

    async def _check_engine_space(self, symbol: str, side: str, current_price: float) -> dict:
        """
        [V68.0] ENGINE SPACE (Espaço de Manobra).
        Calcula se há espaço livre até a próxima liquidez/resistência macro.
        Exige pelo menos 80-100% ROI (1.6% a 2% de movimento de preço em 50x) para validar.
        """
        try:
            from services.signal_generator import signal_generator
            fib = await signal_generator.get_fibonacci_levels(symbol)
            if not fib or 'levels' not in fib:
                return {'valid': True, 'reason': 'no_fib_data'} # Be liberal if data is missing
            
            levels = fib['levels']
            side_norm = side.lower()
            
            # For LONG/BUY, target is 0.0 (Swing High). For SHORT/SELL, target is 0.0 (Swing Low)
            # signal_generator handles the direction mapping in levels
            target_price = levels.get('0.0', current_price)
            
            if target_price == current_price:
                return {'valid': True, 'reason': 'neutral_target'}
            
            distance_pct = abs(target_price - current_price) / current_price
            expected_roi = distance_pct * 50 * 100 # Assuming 50x
            
            min_roi_required = 1.0 # [V87.1] Relaxamento total (1% ROI) para garantir que Swings Macro não sejam bloqueados
            
            is_valid = expected_roi >= min_roi_required
            
            return {
                'valid': is_valid,
                'expected_roi': expected_roi,
                'target': target_price,
                'distance_pct': distance_pct * 100,
                'min_required': min_roi_required
            }
        except Exception as e:
            logger.error(f"Error checking engine space for {symbol}: {e}")
            return {'valid': True, 'reason': f'error: {e}'}

    async def _decorrelation_swap_check(self):
        """
        [V57.0] Active Swap Intelligence:
        1. Identifies slots with DEAD decorrelation and low ROI.
        2. Searches radar for high-confidence decorrelated opportunities.
        3. Performs swap: closes weak position and opens strong one in the same cycle.
        """
        try:
            slots = await firebase_service.get_active_slots()
            active_slots = [s for s in slots if s.get("symbol")]
            
            if not active_slots:
                return

            # Find candidates for closure (DEAD decorrelation and ROI < 50%)
            swap_candidates = []
            for s in active_slots:
                health = s.get("decorrelation_health", {})
                status = health.get("status", "ALIVE")
                roi = float(s.get("pnl_percent", 0))
                
                # Rule: Only swap if DEAD and not already in high profit
                if status == "DEAD" and roi < 50.0:
                    # Also ensure it's not a brand new trade (min 5 min age)
                    opened_at = s.get("opened_at", 0)
                    if (time.time() - opened_at) > 300: # 5 minutes
                        swap_candidates.append(s)

            if not swap_candidates:
                return

            # Find best candidate (lowest score or lowest ROI)
            swap_candidates.sort(key=lambda x: (x.get("decorrelation_health", {}).get("score", 0), x.get("pnl_percent", 0)))
            target_to_close = swap_candidates[0]
            
            # Now check Radar for a replacement
            radar_signals = await firebase_service.get_radar_pulse()
            signals = radar_signals.get("signals", [])
            
            # Filter for ALIVE decorrelation and high confidence
            best_opportunities = []
            for sig in signals[:10]:
                d_data = sig.get("decorrelation", {})
                is_decorrelated = d_data.get("is_active", False)
                d_score = d_data.get("score", 0)
                u_conf = sig.get("unified_confidence", 0)
                
                if is_decorrelated and d_score >= 80 and u_conf >= 75:
                    # Ensure it's not already active
                    norm_sym = sig["symbol"].replace(".P", "").upper()
                    if not any(normalize_symbol(s.get("symbol")) == norm_sym for s in slots):
                        best_opportunities.append(sig)

            if not best_opportunities:
                return

            best_replacement = best_opportunities[0]
            
            # PERFORM SWAP
            symbol_to_close = target_to_close["symbol"]
            symbol_to_open = best_replacement["symbol"]
            slot_id = target_to_close["id"]
            
            logger.info(f"🔄 [V57.0 DECORRELATION SWAP] Initiating swap in Slot {slot_id}: {symbol_to_close} (DEAD) -> {symbol_to_open} (ALIVE)")
            
            # 1. Close the weak position
            close_ok = await bybit_rest_service.close_position(
                symbol=symbol_to_close,
                side=target_to_close.get("side", "Buy"),
                qty=float(target_to_close.get("qty", 0)),
                reason=f"DECORRELATION_DEAD_SWAP_FOR_{symbol_to_open}"
            )
            
            if close_ok:
                # 2. Add to chat for transparency
                msg = f"🔄 **Active Swap Realizado!**\nFechando {symbol_to_close} (Decorrelação Morta) para abrir {symbol_to_open} (Oportunidade Explosiva) no Slot {slot_id}."
                await firebase_service.add_chat_message("captain", msg)
                
                # 3. Request immediate sync to clear the slot
                await bankroll_manager.sync_slots_with_exchange()
                
                # 4. Trigger the new trade (it will be picked up by the main monitor_signals loop in the next iteration 
                # or we can push it now. Let's let the monitor_signals pick it up naturally since the slot is now free.)
                logger.info(f"✅ [V57.0 SWAP] {symbol_to_close} closed. {symbol_to_open} will be picked up by next monitor cycle.")
                
        except Exception as e:
            logger.error(f"Error during decorrelation swap check: {e}")
            traceback.print_exc()

    async def _wait_for_needle_flip(self, symbol: str, side: str, max_wait: int = 15, signal_data: dict = None) -> bool:
        """
        [V7.0] THE PERFECT ENTRY: Wait Sniper Protocol.
        Monitors for confluence (Fibonacci/Walls) and Signal Maturity.
        """
        from services.bybit_ws import bybit_ws_service
        from services.redis_service import redis_service
        from services.signal_generator import signal_generator
        
        start_time = time.time()
        side_norm = side.lower()
        initial_cvd = await redis_service.get_cvd(symbol)
        
        # [V7.0] Wait Sniper Patience: 5 minutes (300s)
        # But for Ranging markets or Scalps, we might be more aggressive
        if signal_data and signal_data.get("is_market_ranging"):
            max_wait = 30  # [V110.24.0] 30s para ranging (era 60s)
        else:
            max_wait = 60  # [V110.24.0] 60s para Swing (era 120s)
            
        # [V7.0] Stability Check: Count consecutive high-confidence checks
        stability_level = 0
        target_stability = 1 # [V91.0] Reduced from 2 to 1 (10s stability)
        
        logger.info(f"🦇 [WAIT SNIPER V7.0] Hunting for the Perfect Entry: {symbol} {side}. Max Wait: {max_wait}s.")

        while (time.time() - start_time) < max_wait:
            # Check every 10s (V7.0 Balance between precision and API load)
            await asyncio.sleep(10)
            
            # 1. Fetch Perfect Entry Confluences (Fib + Walls + SMC + Indicators)
            # Use empty zones_15m as signal_generator will fetch its own cached zones
            trigger_info = await signal_generator.get_5m_entry_triggers(symbol, side, zones_15m={})
            confidence = trigger_info.get('confidence', 0)
            
            # 2. Stability / Maturity Logic (V7.0)
            if confidence >= 80:
                stability_level += 1
            else:
                stability_level = 0 # Reset if signal weakens
                
            # 3. [V68.0] Institutional Shift (MSS) Confirmation
            # Final verification: is price actually shifting structure on 1m?
            mss = await signal_generator.detect_micro_mss(symbol, side)
            mss_confirmed = mss.get('confirmed', False)
            
            # 4. Decision Matrix
            # [V71.5] RELAXED FILTERS: Lower thresholds for faster execution
            
            # Type A: Perfection (Golden Zone + Mature + MSS)
            if confidence >= 80 and mss_confirmed:
                logger.info(f"🎯 [PERFECT ENTRY] Golden Zone + MSS Fired! ({confidence:.1f}%).")
                return True
                
            # Type B: Strong Baseline + Stability + MSS
            if confidence >= 70 and stability_level >= target_stability and mss_confirmed:
                logger.info(f"✅ [STABLE ENTRY] Confidence + MSS Fired! ({confidence:.1f}%).")
                return True
                
            # Type C: Zone Reaction (Needle Flip in the Zone + MSS)
            if confidence >= 60 and mss_confirmed:
                current_cvd = await redis_service.get_cvd(symbol)
                diff = current_cvd - initial_cvd
                if (side_norm == "buy" and diff > 30000) or (side_norm == "sell" and diff < -30000):
                    logger.info(f"🥊 [ZONE REJECTION] Volume + MSS Fired! Delta: {diff:.0f}.")
                    return True

            # Type D: [V110.24.0 REFINED] Score >= 70 já libera entrada sem MSS obrigatório
            score_val = signal_data.get("score", 0) if signal_data else 0
            if score_val >= 70 and confidence >= 45:
                logger.info(f"🚀 [ELITE BYPASS V110.24] Score {score_val} + Conf {confidence:.1f}%. Disparo direto!")
                return True

            # Type E: [V110.24.0 TIME PRESSURE] Após 30s, entrada forçada (Elite >= 20%, Normal >= 35%)
            elapsed = time.time() - start_time
            score_val = signal_data.get("score", 0) if signal_data else 0
            min_conf_bypass = 20 if score_val >= 90 else 35
            if elapsed >= 30 and confidence >= min_conf_bypass:
                logger.info(f"🚀 [TIME PRESSURE V110.24] Entrada forçada para {symbol} após {elapsed:.0f}s (Conf: {confidence:.1f}% >= {min_conf_bypass}%).")
                return True
            
            elapsed = time.time() - start_time
            mss_status = "MSS OK" if mss_confirmed else "WAIT MSS"
            logger.info(f"⏳ [WAIT SNIPER] {symbol} ({elapsed:.0f}s) | Conf: {confidence:.1f}% | {mss_status} | Stability: {stability_level}/{target_stability}")

        logger.info(f"⏰ [SNIPER TIMEOUT] Perfect entry for {symbol} did not materialize after {max_wait}s. Abort.")
        return False

    async def _validate_price_structure(self, symbol: str, side: str, signal_data: dict = None) -> dict:
        """
        [V33.0] PULLBACK HUNTER & ANCORAGEM HÍBRIDA:
        Em vez de entrar imediatamente na "linha azul", o Capitão vigia por até 30s:
        
        Cenário A (Pullback): Aguarda o mercado tentar estopar os apressados (movimento contra).
        Ao confirmar que a contra-força falhou e o preço voltou a favor, usa essa "aba" (Pivô Seguro)
        para gerar um Stop Cirúrgico (Adaptive Stop Loss) curtíssimo.
        
        Cenário B (Ancoragem): Se o mercado derreter/estourar a favor direto sem pullback,
        espera confirmação de distanciamento (0.25%) para entrar, evitando fake wicks na cara.
        """
        
        signal_price = bybit_ws_service.get_current_price(symbol)
        if signal_price <= 0:
            logger.warning(f"⚠️ [PULLBACK HUNTER] Preco invalido para {symbol}. Abortando Tocaia por falta de dados.")
            return {"confirmed": False, "rejection_type": "INVALID_PRICE", "max_drawdown_pct": 0}
        
        side_norm = side.lower()
        start_time = time.time()  # [FIX] V110.29.1: Initialize start_time for timeout calculations
        logger.info(f"🔍 [TOCAIA V34.0] Ativado para {symbol} {side} @ {signal_price:.6f}...")
        
        # [V34.0] Thresholds Dinâmicos baseados no ATR (Volatilidade Consciente)
        indicators = signal_data.get("indicators", {}) if signal_data else {}
        atr = float(indicators.get("atr", 0) or 0)
        
        # Calibração baseada na volatilidade do par
        # Se não houver ATR, usa os padrões safe de 0.1%
        if atr > 0:
            vol_ratio = atr / signal_price
            pullback_threshold = max(0.0005, min(0.0025, vol_ratio * 0.4))
            pullback_reversal = max(0.0003, min(0.0010, vol_ratio * 0.2))
            anchorage_threshold = max(0.0015, min(0.0050, vol_ratio * 1.0))
            logger.info(f"📊 [TOCAIA V34.0] Thresholds Adaptativos: PB: {pullback_threshold*100:.3f}% | REV: {pullback_reversal*100:.3f}% | ANC: {anchorage_threshold*100:.3f}%")
        else:
            pullback_threshold = 0.0010  # 0.10%
            pullback_reversal = 0.0005   # 0.05%
            anchorage_threshold = 0.0025 # 0.25%
            logger.info("📊 [TOCAIA V34.0] Sem ATR. Usando thresholds padrão (0.1%).")
            
        # [V42.0] RALLY MODE (Agressividade Adaptativa)
        # Se score é elite (>89) e estamos em tendência, reduzimos drasticamente as barreiras
        score_val = signal_data.get("score", 0) if signal_data else 0
        from services.signal_generator import signal_generator
        regime_info = await signal_generator.detect_market_regime(symbol)
        is_trending_rally = regime_info.get("regime") == "TRENDING"
        
        rally_mode_active = (score_val >= 85) # [V93.0] Rally mode for any elite signal
        if rally_mode_active:
            logger.info(f"🚀 [V93.0 RALLY MODE] Ativado para {symbol} (Score {score_val}). Reduzindo barreiras para entrada rápida!")
            pullback_threshold *= 0.1 # 90% de redução (quase zero)
            pullback_reversal *= 0.1
            anchorage_threshold = 0.0010 # [V93.0] Entrada fixa em 0.1% de lucro se não houver pullback.
            
        # [V41.5] SNIPER RANGING: Thresholds ainda mais precisos (50% de redução)
        if signal_data and signal_data.get("is_market_ranging"):
            pullback_threshold *= 0.5  # 50% de redução para captar micro-movimentos
            pullback_reversal *= 0.5
            anchorage_threshold *= 0.5
            logger.info(f"🎯 [V41.5 SNIPER RANGING] Thresholds SNIPER ativados. PB: {pullback_threshold*100:.3f}%")
        
        # [V40.0] AUMENTO ESTRATÉGICO TOCAIA (PULLBACK HUNTER)
        is_swing_macro_tocaia = signal_data.get("is_swing_macro", False) if signal_data else False
        
        if is_swing_macro_tocaia:
            max_tocaia_seconds = 600  # [V92.2] 10 min (was 20 min)
            logger.info(f"⏳ [TOCAIA HYBRID V92.2] MACRO SWING. Paciência: {max_tocaia_seconds}s.")
        else:
            # [V92.2] AGGRESSIVE TOCAIA: Reduzindo de 10 min para 2 min (120s)
            # Para sinais de elite ou Whale Pulse, 60s é o limite.
            max_tocaia_seconds = 120 
            if signal_data and (signal_data.get("is_market_ranging") or signal_data.get("intel", {}).get("whale") == "EXTREME (Whale Pulse)"):
                max_tocaia_seconds = 60
            logger.info(f"⏳ [TOCAIA V92.2] Relógio agressivo: {max_tocaia_seconds}s para o bote sníper...")
        
        # Tracking do preço para achar a ponta da armadilha (pivô do violino)
        highest_price = signal_price
        lowest_price = signal_price
        
        pullback_detected = False
        pivot_price = signal_price  # Guardará a ponta máxima do violino
        
        # Loop principal do observador de Pullback
        for elapsed in range(max_tocaia_seconds):
            await asyncio.sleep(1)
            current_price = bybit_ws_service.get_current_price(symbol)
            if current_price <= 0:
                continue
                
            if current_price > highest_price:
                highest_price = current_price
            if current_price < lowest_price:
                lowest_price = current_price
                
            # Verifica distâncias a partir do preço original
            pct_change = (current_price - signal_price) / signal_price
            
            # =============== CENÁRIO B: ANCORAGEM DIRETA (Derretimento) ===============
            if side_norm == "buy" and pct_change >= anchorage_threshold:
                # [V110.132] ENHANCED Adaptive SL for Anchorage: Increased buffer for better breathing
                sl_buffer_pct = max(0.008, min(0.020, vol_ratio * 0.6)) if atr > 0 else 0.012
                anchor_sl = current_price * (1 - sl_buffer_pct)
                
                logger.info(f"⚓ [ANCORAGEM] {symbol} (LONG) estourou direto a {current_price:.6f} (+{pct_change*100:.2f}%). SL Adaptativo: {anchor_sl:.6f} (-{sl_buffer_pct*100:.1f}%)")
                return {
                    "confirmed": True, 
                    "rejection_type": None, 
                    "adaptive_sl": anchor_sl, 
                    "final_price": current_price,
                    "max_drawdown_pct": 0
                }
            elif side_norm == "sell" and pct_change <= -anchorage_threshold:
                # [V110.132] ENHANCED Adaptive SL for Anchorage
                sl_buffer_pct = max(0.008, min(0.020, vol_ratio * 0.6)) if atr > 0 else 0.012
                anchor_sl = current_price * (1 + sl_buffer_pct)
                
                logger.info(f"⚓ [ANCORAGEM] {symbol} (SHORT) derreteu direto a {current_price:.6f} ({pct_change*100:.2f}%). SL Adaptativo: {anchor_sl:.6f} (+{sl_buffer_pct*100:.1f}%)")
                return {
                    "confirmed": True, 
                    "rejection_type": None, 
                    "adaptive_sl": anchor_sl, 
                    "final_price": current_price,
                    "max_drawdown_pct": 0
                }
                
            # =============== CENÁRIO A: PULLBACK HUNTER (Violino) ===============
            if not pullback_detected:
                if side_norm == "buy" and pct_change <= -pullback_threshold:
                    pullback_detected = True
                    logger.debug(f"📈 [PULLBACK] {symbol} armando violino contra LONG (caiu para {current_price:.6f}). Preparando bote.")
                elif side_norm == "sell" and pct_change >= pullback_threshold:
                    pullback_detected = True
                    logger.debug(f"📉 [PULLBACK] {symbol} armando violino contra SHORT (subiu para {current_price:.6f}). Preparando bote.")
            
            # Se já vimos a puxada contra (Pullback formou uma perna)
            # Agora esperamos perder força e virar de novo a nosso favor!
            if pullback_detected:
                if side_norm == "buy":
                    pivot_price = lowest_price  # Pior preço no fundo
                    recovery = (current_price - pivot_price) / pivot_price
                    if recovery >= pullback_reversal:
                        # [V34.0] Confirmação de Fluxo (Needle Check Light)
                        from services.redis_service import redis_service
                        current_cvd = await redis_service.get_cvd(symbol)
                        # Se o CVD está subindo/estável nos últimos segundos, confirma o bote
                        # [V110.132] Volatility-Aware SL Anchor (Increased resilience):
                        # Use a buffer that scales with ATR (min 0.8%, max 1.5%)
                        sl_buffer_pct = max(0.008, min(0.015, vol_ratio * 0.3)) if atr > 0 else 0.010
                        sl_price = pivot_price * (1 - sl_buffer_pct) 
                        
                        logger.info(f"🎯 [BOTE TOCAIA] {symbol} LONG! Pivô em {pivot_price:.6f}. Recovery: {recovery*100:.3f}%. SL: {sl_price:.6f} (-{sl_buffer_pct*100:.2f}% do pivô).")
                        
                        return {
                            "confirmed": True, 
                            "rejection_type": None, 
                            "adaptive_sl": sl_price,
                            "final_price": current_price,
                            "max_drawdown_pct": 0
                        }
                else: # SHORT
                    pivot_price = highest_price # Pior preço no topo
                    recovery = (pivot_price - current_price) / pivot_price
                    if recovery >= pullback_reversal:
                        # [V34.0] Confirmação de Fluxo (Needle Check Light)
                        from services.redis_service import redis_service
                        current_cvd = await redis_service.get_cvd(symbol)
                        # [V110.132] Volatility-Aware SL Anchor (Increased resilience):
                        sl_buffer_pct = max(0.008, min(0.015, vol_ratio * 0.3)) if atr > 0 else 0.010
                        sl_price = pivot_price * (1 + sl_buffer_pct)
                        
                        logger.info(f"🎯 [BOTE TOCAIA] {symbol} SHORT! Pivô em {pivot_price:.6f}. Recovery: {recovery*100:.3f}%. SL: {sl_price:.6f} (+{sl_buffer_pct*100:.2f}% do pivô).")
                        
                        return {
                            "confirmed": True, 
                            "rejection_type": None, 
                            "adaptive_sl": sl_price,
                            "final_price": current_price,
                            "max_drawdown_pct": 0
                        }
        
        # FIM DO TEMPO (Timeout de 240s)
        # [V40.0] ZERO TOLERANCE ANTI-FAKE: Acabou a mamata de entrar pior que o sinal por fim do tempo.
        final_price = bybit_ws_service.get_current_price(symbol)
        commit_tolerance = 0.0005  # [V41.1] Micro-tolerância de 0.05% (spread + noise)
        
        if side_norm == "buy":
            if final_price < signal_price * (1 - commit_tolerance):
                drawdown = ((final_price - signal_price) / signal_price) * 100
                logger.warning(f"❌ [ANTI-FAKE V40.0] {symbol} TOCAIA ABORTADA (LONG) | Preço não corrigiu em {(elapsed if 'elapsed' in locals() else time.time()-start_time):.0f}s! Sinal: {signal_price:.6f} → Atual: {final_price:.6f} ({drawdown:+.3f}%)")
                return {"confirmed": False, "rejection_type": "PRICE_REVERSED", "max_drawdown_pct": abs(drawdown)}
        else:
            if final_price > signal_price * (1 + commit_tolerance):
                drawdown = ((signal_price - final_price) / signal_price) * 100
                logger.warning(f"❌ [ANTI-FAKE V40.0] {symbol} TOCAIA ABORTADA (SHORT) | Preço não cedeu em {(elapsed if 'elapsed' in locals() else time.time()-start_time):.0f}s! Sinal: {signal_price:.6f} → Atual: {final_price:.6f} ({drawdown:+.3f}%)")
                return {"confirmed": False, "rejection_type": "PRICE_REVERSED", "max_drawdown_pct": abs(drawdown)}
        
        # Passou no relógio E o preço está RIGOROSAMENTE igual ou favorável ao radar
        logger.info(f"✅ [PULLBACK HUNTER V40.0] {symbol} {side} CONFIRMED por Fixação Estrita (Preço de Sinal mantido).")
        # Ensure pattern is set to TOCAIA even if stability was the reason
        if signal_data and "indicators" in signal_data:
            signal_data["indicators"]["pattern"] = "TOCAIA"
        return {
            "confirmed": True,
            "rejection_type": None,
            "adaptive_sl": 0,
            "max_drawdown_pct": 0,
            "final_price": final_price
        }

    # [V16.5] DECENTRALIZED to shadow_sentinel.py & fleet_audit.py:
    # - manage_positions, reconcile_orders, _execute_closure, _update_sl

    async def _provide_telemetry(self):
        try:
            active_slots = await firebase_service.get_active_slots()
            slots = [s for s in active_slots if s.get("symbol")]
            if not slots: return
            import random
            slot = random.choice(slots)
            
            pnl = slot.get('pnl_percent', 0)
            status = "LUCRO" if pnl > 0 else "RISCO" if pnl < 0 else "NEUTRO"
            telemetry = f"Alvo: {slot['symbol']} | Status: {status} | ROI Atual: {pnl:.2f}% | Aguentar Posição."
            
            if telemetry: logger.info(f"[{slot['symbol']}] TELEMETRIA: {telemetry}")
        except: pass

    async def _get_system_snapshot(self, mentioned_symbol: str = None):
        """
        AIOS V19.0 JARVIS: Enriched Pulse System.
        Now includes individual slot details for rich conversation context.
        """
        try:
            pulse = await kernel_tools.get_system_pulse()
            history = await firebase_service.get_chat_history(limit=12)
            macro = {"sentiment": "neutral", "headlines": []}  # [V27.2] Removed news_sensor
            
            # V19.0: Fetch individual slot details for JARVIS awareness
            slots = await firebase_service.get_active_slots()
            active_slots_info = []
            for slot_id, s in slots.items():
                if not s.get('symbol'): continue
                
                # Check health
                d_res = await self.signal_gen.detect_btc_decorrelation(s['symbol'])
                is_active = d_res.get('is_decorrelated', False)
                score = d_res.get('confidence', 0)
                
                pnl = s.get('pnl_percent', 0)
                side = 'LONG' if s.get('side', '').lower() == 'buy' else 'SHORT'
                pattern = s.get('pattern', '?')
                status = s.get('visual_status', s.get('status', 'ACTIVE'))
                active_slots_info.append(
                    f"{s['symbol'].replace('.P','').replace('USDT','')}({side}) PnL:{pnl:+.1f}% Pattern:{pattern} Status:{status}"
                )
            
            # Formata para o Prompt do Oráculo
            snapshot = {
                "banca": f"Saldo: ${pulse['equity']['balance']:.2f}, Risco: {pulse['equity']['risk_pct']*100:.2f}%",
                "radar_top": ", ".join(pulse['recent_radar']) or "Escaneando...",
                "active_mission": pulse['mission_status'],
                "macro_news": macro.get("pensamento", "Fluxo estável."),
                "vault_status": f"Ciclo: {pulse['vault_progress']['wins']}/{pulse['vault_progress']['total_goal']}, Cofre: ${pulse['vault_progress']['vault_balance']:.2f}",
                "api_health": pulse['system_health'],
                "active_slots_detail": " | ".join(active_slots_info) or "Nenhum slot ativo — escaneando radar",
                "history_str": "\n".join([f"{m['role'].upper()}: {m['text']}" for m in history]),
            }
            return snapshot
        except Exception as e:
            logger.error(f"Error gathering Oracle snapshot via Kernel: {e}")
            return None

    async def _execute_action_command(self, command: str, snapshot: dict) -> str:
        """
        [V12.0] Executes trade/system commands directly.
        """
        try:
            cmd_lower = command.lower()
            
            # [V20.1] Comando: Limpar Consciência (Deep Clean)
            if any(word in cmd_lower for word in ['limpar consciência', 'resetar memória', 'esquecer fatos']):
                logger.warning("🧹 [DEEP CLEAN] Resetting JARVIS Multi-Layer Consciousness")
                # 1. Clear Long-Term Life Facts (Firestore)
                await asyncio.to_thread(firebase_service.db.collection("admiral_consciousness").document("life_facts").delete)
                # 2. Clear Chat History (RTDB)
                await firebase_service.clear_chat_history()
                # 3. Clear Learned Facts in Profile (RTDB)
                await firebase_service.update_captain_profile({"facts_learned": []})
                
                return "🧹 Almirante, realizei uma limpeza profunda e total em todos os meus circuitos de memória. Meu histórico, fatos aprendidos e planos de longo prazo foram apagados. Meus sistemas neurais estão em modo 'vácuo'. O que deseja que eu aprenda primeiro?"
                
            # Comando: Status de Risco
            if any(word in cmd_lower for word in ['status de risco', 'risco', 'risk status']):
                slots = await firebase_service.get_active_slots()
                risk_free_count = sum(1 for s in slots if s.get("status_risco") and "RISK" in s.get("status_risco", "").upper() or "ZERO" in s.get("status_risco", "").upper())
                total_active = sum(1 for s in slots if s.get("symbol"))
                return f"Almirante, {risk_free_count}/{total_active} slots em Risco Zero. {snapshot.get('banca')}. API: {snapshot.get('api_health')}."
            
            # Comando: Modo Cautela
            if any(word in cmd_lower for word in ['modo cautela', 'cautious', 'cautela']):
                await vault_service.set_cautious_mode(True, min_score=85)
                return "Almirante, Modo Cautela ATIVADO. Threshold de Score elevado para 85. Apenas sinais de elite serão considerados."
            
            # Comando: Desativar Cautela
            if any(word in cmd_lower for word in ['desativar cautela', 'modo normal']):
                await vault_service.set_cautious_mode(False)
                return "Almirante, Modo Cautela DESATIVADO. Threshold de Score retornado para 75."
            
            # Comando: Abortar Missão (Kill Switch)
            if any(word in cmd_lower for word in ['abortar missão', 'abortar', 'abort', 'kill switch', 'panic']):
                await bankroll_manager.emergency_close_all()
                return "🚨 Almirante, ABORT EXECUTADO. Todas as posições foram fechadas. Sistema em standby."
            
            # Comando: Registrar Retirada
            if any(word in cmd_lower for word in ['retirada', 'withdraw', 'saque', 'cofre']):
                # Try to extract amount from command
                amount_match = re.search(r'(\d+(?:[.,]\d+)?)', command)
                if amount_match:
                    amount = float(amount_match.group(1).replace(',', '.'))
                    await vault_service.execute_withdrawal(amount)
                    calc = await vault_service.calculate_withdrawal_amount()
                    return f"Almirante, retirada de ${amount:.2f} registrada no Cofre. Total acumulado: ${calc['vault_total'] + amount:.2f}."
                else:
                    calc = await vault_service.calculate_withdrawal_amount()
                    return f"Almirante, recomendo retirada de ${calc['recommended_20pct']:.2f} (20% do lucro do ciclo). Diga o valor para confirmar."
            
            # Comando: Ativar Admiral's Rest
            if any(word in cmd_lower for word in ['descanso', 'rest', 'sleep', 'dormir']):
                await vault_service.activate_admiral_rest(hours=24)
                return "Almirante, Admiral's Rest ATIVADO. Sistema em standby por 24h. Bom descanso."
            
            # Comando: Desativar Admiral's Rest
            if any(word in cmd_lower for word in ['acordar', 'wake', 'despertar', 'ativar sistema']):
                await vault_service.deactivate_admiral_rest()
                return "Almirante, sistema REATIVADO. Pronto para operações."
            
            # [V20.5] COMANDOS DE AGENDA
            if any(word in cmd_lower for word in ['agende', 'marcar', 'agenda', 'lembrete', 'reuniao', 'compromisso']):
                # Extração simples de título e tempo (Pode ser melhorado com IA)
                # Ex: "Agende reunião amanhã às 14h"
                logger.info(f"📅 [JARVIS-AGENDA] Processando agendamento: {command}")
                
                # Para uma primeira versão, vamos usar a IA do ai_service para extrair o evento
                extraction_prompt = f"Extraia o título, data e hora (timestamp relativo a {datetime.now()}) do compromisso: {command}. Retorne JSON: {{'title': '...', 'ts': timestamp}}"
                extracted = await ai_service.generate_content(extraction_prompt, system_instruction="Você é um extrator de datas preciso.")
                
                try:
                    import json
                    # Clean markdown
                    extracted = extracted.replace('```json', '').replace('```', '').strip()
                    data = json.loads(extracted)
                    ts = data.get('ts')
                    title = data.get('title', 'Compromisso')
                    
                    if ts:
                        # Converte timestamp para datetime para a API da Google
                        dt = datetime.fromtimestamp(ts)
                        success = await google_calendar_service.add_event(title, command, dt)
                        if success:
                            return f"📅 Almirante, {title} agendado no Google Calendar para {dt.strftime('%d/%m às %H:%M')}. Sincronização em nuvem completa."
                except:
                    pass
                return "📅 Almirante, não consegui processar a data exata. Pode ser mais específico (ex: amanhã às 10h)?"

            return None  # Not an action command
            
        except Exception as e:
            logger.error(f"Error executing action command: {e}")
            import traceback
            traceback.print_exc()
            return f"⚠️ Almirante, falha ao executar comando tático: {e}"

    async def _generate_flash_report(self, snapshot: dict) -> str:
        """
        V4.2: Gera Flash Report quando Almirante retorna após ausência.
        """
        current_time = time.time()
        time_away = current_time - self.last_interaction_time
        
        # Only generate if away for more than 30 minutes
        if time_away < 1800:  # 30 min
            return None
        
        hours_away = time_away / 3600
        
        # Gather activity since last interaction
        vault_status = await vault_service.get_cycle_status()
        
        report = f"Bem-vindo de volta, Almirante. "
        if hours_away > 1:
            report += f"Ausência de {hours_away:.1f}h. "
        
        report += f"Ciclo {vault_status.get('cycle_number', 1)}: {vault_status.get('sniper_wins', 0)}/20 trades Sniper. "
        report += f"Progresso para próxima retirada: {(vault_status.get('sniper_wins', 0)/20)*100:.0f}%. "
        report += f"API: {snapshot.get('api_health')}."
        
        if snapshot.get('in_rest'):
            report += " ⚠️ Sistema em Admiral's Rest."
        
        return report

    async def process_chat(self, user_message: str, symbol: str = None):
        """
        V18.1 CAPTAIN ELITE: Synchronized Chat with real-time thinking state.
        """
        logger.info(f"Captain V18.1 processing: {user_message}")
        
        # 0. Immediate Sync: Log user message and set thinking state
        await firebase_service.add_chat_message("user", user_message)
        await firebase_service.set_thinking_state(True)
        
        try:
            # 1. Load Long-Term Memory & Profile
            profile = await firebase_service.get_captain_profile()
            user_name = profile.get("name", "Almirante")
            interests = profile.get("interests", [])
            facts = profile.get("facts_learned", [])
            mode = profile.get("communication_style", "normal") # Fix for undefined mode
            
            # 2. Gather Total Awareness (System State & Consciousness) [V15.0]
            snapshot = await self._get_system_snapshot(mentioned_symbol=symbol)
            if not snapshot:
                return "Sincronização neural interrompida. Reabrindo canais de telemetria."
                
            # 1.5 [V20.1] Check for Immediate Action Commands (with real snapshot)
            action_response = await self._execute_action_command(user_message, snapshot=snapshot)
            if action_response:
                await firebase_service.add_chat_message("captain", action_response)
                await firebase_service.set_thinking_state(False)
                return action_response
            
            # [V15.0] Fetch Admiral Consciousness Memory
            consciousness = await firebase_service.get_admiral_consciousness()
            life_facts = consciousness.get("outros", []) + consciousness.get("eventos", [])
            family_info = consciousness.get("familia", [])
            
            memory_context = f"[CONSCIÊNCIA_ALMIRANTE] Fatos: {', '.join(life_facts[-10:]) if life_facts else 'Nenhum fato novo.'} | Família: {', '.join(family_info)}"
            
            # [V20.0] New JARVIS Brain Dimensions
            active_dims = jarvis_brain.detect_dimensions(user_message)
            is_greeting = jarvis_brain.is_simple_greeting(user_message)
            synthesis_instr = jarvis_brain.get_synthesis_instruction(active_dims)
            
            # [V21.0 - JARVIS INTERNET PROTOCOL] Agentic DuckDuckGo Search
            web_context = ""
            msg_lower = user_message.lower()
            web_triggers = [
                "pesquise", "busque", "procure", "o que é", "quem é", "notícia", "google", 
                "basquete", "nba", "jordan", "kobe", "lebron", "curry", "estatistica",
                "neurociencia", "cerebro", "hormonio", "dopamina", "jesus", "biblia", 
                "contexto historico", "biografia", "quem foi", "como funciona"
            ]
            if DDGS and any(w in msg_lower for w in web_triggers):
                try:
                    logger.info("🌐 [JARVIS WEB] Iniciando Busca Externa...")
                    with DDGS() as ddgs:
                        # [V20.5] Enhanced search query: If it's about basketball/neuro/bible, focus on FACTS
                        search_results = list(ddgs.text(user_message, max_results=3))
                        if search_results:
                            web_context = "\n[WEB_SEARCH_RESULTS]\n" + "\n".join([f"- {r['title']}: {r['body']}" for r in search_results]) + "\n[/WEB_SEARCH_RESULTS]\nUse estes dados para responder ao Almirante com extrema precisão.\n"
                except Exception as e:
                    logger.error(f"Falha na Busca Web: {e}")
            
            # [V15.0] Actualizing Persona
            family_str = ", ".join(family_info) or "Fabiana, Pedro e Lívia"
            dynamic_system_prompt = JARVIS_V20_SYSTEM_PROMPT.format(
                familia=family_str,
                active_dimensions_instructions=synthesis_instr
            )

            # 4. Build Context-Enriched Prompt
            if is_greeting:
                prompt = f"""
                Saudação simples do Almirante: "{user_message}"
                Aja naturalmente, seja breve e não dê relatório do sistema ainda.
                """
            else:
                # Contexto "Blindado" para evitar recusa
                system_context_block = f"""
                [MEMORIA_INTERNA_DE_MISSÃO]
                Banca: {snapshot['banca']} | Vault: {snapshot['vault_status']}
                Slots: {snapshot.get('active_slots_detail', 'Nenhum')}
                Radar: {snapshot['radar_top']} | Macro: {snapshot.get('macro_news', 'Estável')}
                [FIM_MEMORIA]
                """
                
                # Se for CEO mode ou tiver triggers financeiros, adiciona o snapshot
                if "TRADER_ELITE" in active_dims or "FINANCE_LEGACY" in active_dims or mode == "CEO":
                    context_bridge = f"\nUse estes dados se necessário:\n{system_context_block}"
                else:
                    context_bridge = "\nFoque na conversa pessoal/filosófica, sem relatórios técnicos agora."

                prompt = f"""
                [CONSCIÊNCIA_ADICIONAL] {memory_context}
                {web_context}
                Mensagem do Almirante: "{user_message}"
                {context_bridge}
                """
            

            response = await ai_service.generate_content(prompt, system_instruction=dynamic_system_prompt)
            
            if not response:
                logger.warning(f"AI Service failed to provide a response for user: {user_name}")
                response = f"{user_name}, interferência nos canais neurais. A clareza retornará em breve."
            
            # 7. Memory & Logging
            sanitized_response = await self._sanitize_response(response)
            
            await firebase_service.add_chat_message("captain", sanitized_response)
            await firebase_service.set_thinking_state(False)
            
            # [V15.0] LEARNING LOOP (DISABLING TO SAVE TOKENS)
            async def _learning_loop():
                try:
                    pass
                except Exception as e:
                    logger.error(f"Error in consciousness learning loop: {e}")
            
            asyncio.create_task(_learning_loop())
            
            await firebase_service.log_event("USER", user_message, "INFO")
            await firebase_service.log_event("ORACLE", sanitized_response, "INFO")
            
            return sanitized_response
            
        except Exception as e:
            import traceback
            logger.error(f"Chat Fatal Error: {e}\n{traceback.format_exc()}")
            await firebase_service.set_thinking_state(False)
            return "Almirante, falha temporária nos sistemas neurais. Reiniciando protocolos de comunicação."

    async def _wait_for_ambush_trap(self, symbol: str, side: str, signal_data: dict) -> bool:
        """
        [V110.118] EMBOSCADA SNIPER (TOCAIA REFINADA):
        Delega a Tocaia ao AmbushAgent que usa Fibonacci (0.382 ou 0.5)
        aliado ao CVD/RSI em tempo real para um Sniper Entry real.
        """
        try:
            from services.agents.ambush import ambush_agent
            
            logger.info(f"🥷 [AMBUSH-DELEGATION] {symbol} entregue ao Espião para rastreio tático...")
            await firebase_service.update_signal_outcome(signal_data["id"], "WAITING_AMBUSH", {"ambush_status": "Observando Fibo..."})
            
            result = await ambush_agent.execute_ambush(symbol, side, signal_data)
            
            action = result.get("action")
            if action == "TRIGGER":
                logger.info(f"🔥 [AMBUSH-AUTHORIZED] O Espião deu o sinal verde para {symbol}! Engatando.")
                return True
            elif action == "ABORT":
                logger.warning(f"🛑 [AMBUSH-DENIED] O Espião detectou perigo ({result.get('reason')}) e abortou {symbol}.")
                await firebase_service.update_signal_outcome(signal_data["id"], "AMBUSH_DENIED")
                return False
            elif action == "TIMEOUT":
                logger.warning(f"⏳ [AMBUSH-TIMEOUT] {symbol} não recuou dentro de 30m. Abortando.")
                await firebase_service.update_signal_outcome(signal_data["id"], "AMBUSH_TIMEOUT")
                return False
                
            return False
        except Exception as e:
            logger.error(f"❌ [AMBUSH-DELEGATE-ERROR] {symbol}: {e}")
            return False

    async def _sanitize_response(self, text: str) -> str:
        """
        Remove ruídos de pensamentos internos (Thinking... ou blocos <thought>).
        """
        # Geralmente modelos DeepSeek usam Thinking... \n\n
        text = re.sub(r'(Thinking|Pensando)\.\.\.[\s\S]*?\n\n', '', text, flags=re.IGNORECASE)
        text = re.sub(r'(Thinking|Pensando)\.\.\.', '', text, flags=re.IGNORECASE)
        
        return text.strip()



captain_agent = CaptainAgent()
