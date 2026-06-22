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
from services.okx_rest import okx_rest_service as okx_rest_service
from services.okx_ws_public import okx_ws_public_service
from services.database_service import database_service
from services.execution_protocol import execution_protocol
from services.google_calendar_service import google_calendar_service
from config import settings
from services.agents.librarian import librarian_agent # [V2.0] Librarian DNA Profile Engine
from services.agents.quartermaster import quartermaster_agent # [V110.135]
from services.redis_service import redis_service
from services.signal_generator import signal_generator
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
        self.slot_vacancy_tracker = {i: boot_time for i in range(1, 41)}
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
        self.last_btc_rug_pull_check = 0 # [DECOR_HUNTER 2.0]
        self.librarian_rankings = {} # [LIBRARIAN]
        self.last_librarian_sync = 0
        self.last_lateral_at = 0 # [V110.30.2] Cooldown pós-Lateral
        self.prev_btc_adx = 0 # [V110.128] ADX Slope Tracking
        self.btc_market_regime = {"direction": "NEUTRAL", "macro": "BULLISH"}

    def reset_runtime_state(self) -> Dict[str, Any]:
        """Limpa travas em memória que não vivem no banco de dados."""
        snapshot = {
            "active_tocaias": len(self.active_tocaias),
            "processing_lock": len(self.processing_lock),
            "cooldown_registry": len(self.cooldown_registry),
            "daily_symbol_trades": len(self.daily_symbol_trades),
        }
        self.active_tocaias.clear()
        self.processing_lock.clear()
        self.cooldown_registry.clear()
        self.daily_symbol_trades.clear()
        self.slot_vacancy_tracker = {i: time.time() for i in range(1, 41)}
        return snapshot
        
    async def on_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """AIOS Message Handler for Captain."""
        msg_type = message.get("type")
        data = message.get("data", {})
        
        if msg_type == "SYSTEM_STATUS":
            return {"status": "success", "mode": "SCANNING" if self.is_running else "PAUSED"}
            
        return {"status": "error", "message": f"Unknown command: {msg_type}"}
        
        # V9.0 Cycle Diversification: Gerenciado pelo VaultService (não mais local)

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value is None or value == "":
                return default
            return float(value)
        except Exception:
            return default

    async def _evaluate_contract_quality(self, signal: Dict[str, Any], symbol: str) -> Dict[str, Any]:
        """
        Avalia se o contrato OKX é adequado para banca pequena e stops rápidos.
        A saída alimenta o quality gate do Capitão e o relatório do Radar.
        """
        contract_info = signal.get("contract_info") or signal.get("contract") or {}

        if not contract_info:
            try:
                contract_info = await asyncio.wait_for(
                    okx_rest_service.get_detailed_contract_info(symbol),
                    timeout=2.5
                )
                details = contract_info.get("contract_details", {})
                risk = contract_info.get("risk_analysis", {})
                contract_info = {
                    "ctVal": details.get("ctVal", 1.0),
                    "lotSize": details.get("lotSize", details.get("qtyStep", 1.0)),
                    "minQty": details.get("minQty", 1.0),
                    "tickSize": details.get("tickSize", 0.01),
                    "maxLeverage": details.get("maxLeverage", signal.get("leverage", settings.LEVERAGE)),
                    "notionalUsd": details.get("notionalUsd", 0),
                    "riskImpactPerContract": risk.get("price_impact_per_contract", 0),
                    "minMarginRequired": risk.get("min_margin_required", 0),
                    "symbol": contract_info.get("symbol", symbol),
                    "currentPrice": contract_info.get("current_price", signal.get("entry_price_signal", 0)),
                }
                signal["contract_info"] = contract_info
            except Exception as e:
                logger.warning(f"⚠️ [CONTRACT-GATE] Falha ao obter contrato OKX de {symbol}: {e}")
                contract_info = {}

        current_price = self._safe_float(
            contract_info.get("currentPrice") or contract_info.get("current_price") or signal.get("entry_price_signal"),
            0.0
        )
        ct_val = self._safe_float(contract_info.get("ctVal") or contract_info.get("ct_val"), 1.0)
        lot_size = self._safe_float(contract_info.get("lotSize") or contract_info.get("qtyStep") or contract_info.get("qty_step"), 1.0)
        min_qty = self._safe_float(contract_info.get("minQty") or contract_info.get("min_qty"), lot_size or 1.0)
        tick_size = self._safe_float(contract_info.get("tickSize") or contract_info.get("tick_size"), 0.01)
        max_leverage = self._safe_float(contract_info.get("maxLeverage") or contract_info.get("max_leverage"), settings.LEVERAGE)
        target_leverage = self._safe_float(signal.get("leverage"), settings.LEVERAGE)

        tick_roi = (tick_size / current_price) * target_leverage * 100 if current_price > 0 else 0.0
        min_order_margin = (current_price * ct_val * max(min_qty, lot_size, 1e-12)) / max(max_leverage, 1.0) if current_price > 0 else 0.0
        balance = self._safe_float(getattr(settings, "OKX_SIMULATED_BALANCE", 100.0), 100.0)
        margin_ratio = (min_order_margin / balance) if balance > 0 else 0.0

        penalty = 0.0
        block = False
        reasons = []

        if max_leverage < target_leverage:
            penalty += 20.0
            reasons.append(f"maxLeverage {max_leverage:.0f}x < alvo {target_leverage:.0f}x")

        if tick_roi >= 15.0:
            block = True
            penalty += 25.0
            reasons.append(f"tick grosso ({tick_roi:.2f}% ROI por tick)")
        elif tick_roi >= 8.0:
            penalty += 8.0
            reasons.append(f"tick sensível ({tick_roi:.2f}% ROI por tick)")

        if min_order_margin >= balance * 0.30:
            block = True
            penalty += 25.0
            reasons.append(f"margem mínima ${min_order_margin:.2f} pesa {margin_ratio*100:.1f}% da banca")
        elif min_order_margin >= balance * 0.15:
            penalty += 8.0
            reasons.append(f"margem mínima ${min_order_margin:.2f} pesa {margin_ratio*100:.1f}% da banca")

        score = max(0.0, 100.0 - penalty)
        if not reasons:
            reasons.append("Contrato OKX compatível com banca, tick e stops")

        return {
            "score": round(score, 1),
            "penalty": round(penalty, 1),
            "block": block,
            "reasons": reasons,
            "contract_info": contract_info,
            "metrics": {
                "current_price": current_price,
                "ctVal": ct_val,
                "lotSize": lot_size,
                "minQty": min_qty,
                "tickSize": tick_size,
                "maxLeverage": max_leverage,
                "targetLeverage": target_leverage,
                "tickRoi": round(tick_roi, 4),
                "minOrderMargin": round(min_order_margin, 6),
                "balance": balance,
                "marginRatio": round(margin_ratio, 4),
            }
        }

    async def _evaluate_cost_gate(self, signal: Dict[str, Any], symbol: str) -> Dict[str, Any]:
        """
        [ECC cost-tracking] Avalia se as taxas operacionais (Funding Rate + taxas taker)
        comprometem mais de 15% do lucro projetado até o Alvo Principal.
        Bloqueia a entrada preventivamente caso o custo seja abusivo.
        """
        COST_BLOCK_THRESHOLD = 0.15  # 15% do lucro projetado
        TAKER_FEE = 0.00050          # Taxa taker OKX: 0.05% por lado (entrada + saída = 0.10%)

        side = (signal.get("side") or "Buy").lower()
        leverage = float(signal.get("leverage") or 50)
        entry_price = float(signal.get("entry_price_signal") or 0)
        target_price = float(signal.get("tp_price") or signal.get("target_price") or 0)

        result = {
            "block": False,
            "reason": "CUSTO_OK",
            "funding_rate": 0.0,
            "taker_cost_pct": round(TAKER_FEE * 2 * leverage * 100, 4),
            "funding_cost_pct": 0.0,
            "total_cost_pct": 0.0,
            "projected_profit_pct": 0.0,
            "cost_ratio": 0.0,
        }

        if entry_price > 0 and target_price > 0:
            if side in ("buy", "long"):
                profit_pct = (target_price - entry_price) / entry_price * leverage * 100
            else:
                profit_pct = (entry_price - target_price) / entry_price * leverage * 100
        else:
            result["reason"] = "SEM_ALVO_DEFINIDO"
            return result

        result["projected_profit_pct"] = round(profit_pct, 2)

        if profit_pct <= 0:
            result["reason"] = "LUCRO_NAO_CALCULAVEL"
            return result

        try:
            from services.okx_rest import okx_rest_service
            funding_rate = await asyncio.wait_for(
                okx_rest_service.get_funding_rate(symbol),
                timeout=2.0
            )
        except Exception as e:
            logger.warning(f"⚠️ [COST-GATE] Falha ao obter Funding Rate de {symbol}: {e}")
            funding_rate = 0.0

        result["funding_rate"] = round(funding_rate * 100, 6)

        funding_penalizes_us = (
            (side in ("buy", "long") and funding_rate > 0) or
            (side in ("sell", "short") and funding_rate < 0)
        )
        if funding_penalizes_us:
            funding_cost_pct = abs(funding_rate) * 3 * leverage * 100
        else:
            funding_cost_pct = 0.0

        result["funding_cost_pct"] = round(funding_cost_pct, 4)

        taker_cost_pct = TAKER_FEE * 2 * leverage * 100
        total_cost_pct = taker_cost_pct + funding_cost_pct
        result["taker_cost_pct"] = round(taker_cost_pct, 4)
        result["total_cost_pct"] = round(total_cost_pct, 4)

        cost_ratio = total_cost_pct / profit_pct if profit_pct > 0 else 0.0
        result["cost_ratio"] = round(cost_ratio, 4)

        if cost_ratio > COST_BLOCK_THRESHOLD:
            result["block"] = True
            result["reason"] = (
                f"CUSTO_ABUSIVO: custo={total_cost_pct:.2f}% vs lucro={profit_pct:.2f}% "
                f"(ratio={cost_ratio*100:.1f}% > limite {COST_BLOCK_THRESHOLD*100:.0f}%) | "
                f"FR={funding_rate*100:.4f}%"
            )
            logger.warning(
                f"💸 [COST-GATE] {symbol} {side.upper()} BLOQUEADO por custo abusivo: "
                f"total={total_cost_pct:.2f}% | lucro={profit_pct:.2f}% | ratio={cost_ratio*100:.1f}%"
            )
        else:
            result["reason"] = (
                f"CUSTO_OK: total={total_cost_pct:.2f}% vs lucro={profit_pct:.2f}% "
                f"(ratio={cost_ratio*100:.1f}%)"
            )

        return result

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

            # [ECC ito-market-intelligence] 1b. PANIC FILTER (Correlação de Pearson BTC/Altcoin)
            panic_response = await kernel.dispatch({
                "sender": self.agent_id,
                "receiver": "macro_analyst",
                "type": "GET_PANIC_FILTER",
                "data": {"symbol": symbol}
            })
            panic_data = (panic_response or {}).get("data", {})
            panic_mode = panic_data.get("panic_mode", False)
            panic_reason = panic_data.get("reason", "")
            
            # 2. Sentiment [V43.0 Rigorous]
            # Injects is_ranging context for the specialist
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

            # [ECC ito-market-intelligence] PANIC FILTER: Bloqueia LONG em colapso de mercado correlacionado
            if panic_mode and side.lower() in ("buy", "long"):
                approved = False
                reasons.append(f"🚨🚫 PANIC_FILTER: {panic_reason}")
                logger.warning(f"🚨 [PANIC-BLOCK] {symbol} LONG BLOQUEADO por modo pânico: {panic_reason}")

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
                # [V110.999] Calibragem de Divergência H4 para Sinais Elite/Néctar
                if smc_score >= 95 or (smc_score >= 90 and ("NECTAR" in nectar_seal or "ELITE" in nectar_seal)):
                    penalty = 5
                    unified_score -= penalty
                    logger.info(f"⚡ [TREND-DIVERGENCE-ELITE] {symbol} {side} contra tendência H4 {lib_trend_4h}. Penalidade atenuada para -{penalty} pts (Score={smc_score} | Selo={nectar_seal}).")
                else:
                    penalty = 15
                    unified_score -= penalty
                    logger.warning(f"⚠️ [TREND-DIVERGENCE] {symbol} {side} contra tendência H4 {lib_trend_4h}. Penalidade total de -{penalty} pts aplicada.")

            if "TRAP" in nectar_seal:
                # [V110.999] Permite bypass do Trap Shield em modo PAPER ou para Sinais de Elite (SMC Score >= 95)
                from config import settings
                is_paper = settings.OKX_EXECUTION_MODE == "PAPER"
                if is_paper or smc_score >= 95:
                    logger.info(f"⚡ [LIBRARIAN-TRAP-BYPASS] {symbol} (SMC={smc_score}) ignorou Trap Shield (Paper={is_paper} | Elite={smc_score>=95}).")
                else:
                    approved = False
                    reasons.append("⚠️🚫 LIBRARIAN TRAP SHIELD: Bloqueio absoluto por zona de armadilha.")
                    unified_score = 0 
                    logger.warning(f"⚠️ [LIBRARIAN-TRAP] {symbol} sinalizado como zona de armadilha. ORDEM ABORTADA.")
            
            # [V120] ANTI-TRAP RELAXADO — Ordem direta, sem bloqueio por trap
            if trap_risk:
                logger.info(f"🔓 [V120 TRAP-PASS] {symbol} {side} | trap_risk={trap_risk} — Ordem direta autorizada.")

            # [V120] RELAXED RISK & SENTIMENT — Ordem direta, sem bloqueio
            if risk_score > 8:
                logger.info(f"🔓 [V120 RISK-PASS] {symbol} risk_score={risk_score} — Ordem direta autorizada.")
            
            if sent_score < 30:
                logger.info(f"🔓 [V120 SENTIMENT-PASS] {symbol} sent_score={sent_score} — Ordem direta autorizada.")
            
            # [V120] WHALE DIVERGENCE RELAXADO — Ordem direta, sem bloqueio por whale bias
            wb_upper = whale_bias.upper()
            if side.lower() == "buy" and "DISTRIBUTION" in wb_upper:
                logger.info(f"🔓 [V120 WHALE-PASS] {symbol} LONG | Whale {whale_bias} — Ordem direta autorizada.")
            elif side.lower() == "sell" and "ACCUMULATION" in wb_upper:
                logger.info(f"🔓 [V120 WHALE-PASS] {symbol} SHORT | Whale {whale_bias} — Ordem direta autorizada.")

            contract_quality = await self._evaluate_contract_quality(signal, symbol)
            contract_penalty = float(contract_quality.get("penalty") or 0.0)
            if contract_quality.get("block"):
                approved = False
                reasons.append("📐🚫 CONTRACT_GATE: " + "; ".join(contract_quality.get("reasons", [])))
                logger.warning(f"📐 [CONTRACT-GATE] {symbol} {side} bloqueado: {contract_quality.get('reasons')}")
            elif contract_penalty > 0:
                unified_score -= contract_penalty
                logger.warning(
                    f"📐 [CONTRACT-PENALTY] {symbol} {side} -{contract_penalty:.1f} pts | "
                    + "; ".join(contract_quality.get("reasons", []))
                )

            # [ECC cost-tracking] Bloqueio preventivo por taxa de funding + taker abusivos
            cost_gate = await self._evaluate_cost_gate(signal, symbol)
            if cost_gate.get("block"):
                approved = False
                reasons.append(f"💸🚫 COST_GATE: {cost_gate.get('reason')}")
                logger.warning(f"💸 [COST-GATE-BLOCK] {symbol} {side} bloqueado: {cost_gate.get('reason')}")

            # [V110.27.0] ABSOLUTE CONVERGENCE SHIELD: Minimum Confidence
            # Quality gate: keep PAPER and live signal selection aligned so weak radar
            # candidates do not occupy slots just because the simulator is permissive.
            try:
                slots = await database_service.get_active_slots()
            except Exception as e:
                logger.warning(f"⚠️ [CAPTAIN] Não foi possível obter slots: {e}")
                slots = []
            occupied_count = sum(
                1 for s in slots
                if s.get("symbol") and float(s.get("entry_price") or 0) > 0 and float(s.get("qty") or 0) > 0
            )
            # Detecta regime de mercado dinamicamente para calibrar slots livres
            is_ranging_mode = True
            try:
                from services.okx_ws_public import okx_ws_public_service
                adx = getattr(okx_ws_public_service, 'btc_adx', 0)
                is_ranging_mode = (adx < 25)
            except Exception:
                pass
            from services.okx_rest import okx_rest_service
            if okx_rest_service.execution_mode == "PAPER":
                if not approved:
                    return {
                        "approved": False,
                        "reason": ", ".join(reasons) if reasons else "Blocked by Fleet",
                        "unified_confidence": round(unified_score, 1),
                        "intel": {
                            "macro_score": macro_score,
                            "micro_score": micro_score,
                            "smc_score": smc_score,
                            "onchain_score": on_chain_score,
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
                            "nectar_seal": nectar_seal,
                            "dna": lib_dna,
                            "contract_info": contract_quality.get("contract_info", {}),
                            "contract_quality": contract_quality,
                            "pain_points": sentiment.get("data", {}).get("pain_points", {}) if sentiment else {}
                        }
                    }
                unified_score = max(unified_score, required_confidence)
                logger.info(f"[PAPER-QUALITY] {symbol} aprovado em simulacao sem bypass de qualidade.")
                
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
                    "contract_info": contract_quality.get("contract_info", {}),
                    "contract_quality": contract_quality,
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
        
        # [DECOR_HUNTER 3.0] Lança o loop paralelo de pares desgrudados do BTC
        asyncio.create_task(self._decor_hunter_loop())
        logger.info("🎯 [DECOR-HUNTER 3.0] Loop paralelo de varredura iniciado.")
        
        while self.is_running:
            try:
                # 0. Global Authorization Check
                from services.vault_service import vault_service
                from services.okx_rest import okx_rest_service
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
                balance = await bankroll_manager.get_live_operating_equity()
                is_paper = okx_rest_service.execution_mode == "PAPER"
                if balance < 2.0 and not (is_paper or settings.OKX_API_KEY_MASTER):
                    if not hasattr(self, "_last_zero_equity_log") or (time.time() - self._last_zero_equity_log) > 60:
                        msg = f"🛑 [ZERO EQUITY] Capitão em standby. LiveEquity (${balance:.2f}) insuficiente."
                        logger.error(msg)
                        await firebase_service.log_event("SNIPER", msg, "CRITICAL")
                        self._last_zero_equity_log = time.time()
                    await asyncio.sleep(10)
                    continue

                occupied_count = sum(1 for s in slots if s.get("symbol"))

                # [DECOR_HUNTER 3.0] DECOR_HUNTER roda em loop paralelo próprio (_decor_hunter_loop).
                # O monitor_signals processa todos os sinais da fila normalmente.
                # ELITE signals são bloqueados por _run_user_execution_logic quando LATERAL.
                # DECOR_HUNTER signals são imunes ao regime de mercado.
                if balance < 10.0 and okx_rest_service.execution_mode != "PAPER":
                    max_total_slots = 2
                else:
                    max_total_slots = 20  # Hard limit: ELITE (tendência) + DECOR_HUNTER (paralelo)

                # [V110.116] Heartbeat Log
                if not hasattr(self, "_last_heartbeat") or (time.time() - self._last_heartbeat) > 300:
                    balance = await bankroll_manager.get_live_operating_equity()
                    vault_ok, vault_reason = await vault_service.is_trading_allowed()
                    logger.info(f"⚓ [HEARTBEAT] Captain Scanning... Mode: {okx_rest_service.execution_mode} | Slots: {occupied_count}/{max_total_slots} | LiveEquity: ${balance:.2f} | Vault: {'✅' if vault_ok else '❌'} ({vault_reason})")
                    self._last_heartbeat = time.time()
                
                free_slots = max_total_slots - occupied_count
                
                # [V92.0] MASS SNIPER: Monitorar até 24 tocaias simultâneas (o limite real é de slots).
                monitoring_limit = max(24, free_slots * 6)
                
                # [V110.13.0] Preemption Logic: Elite Shadows can bump stagnant trades
                is_full = free_slots <= 0
                busy_tocaias = len(self.active_tocaias) >= monitoring_limit

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
                if okx_rest_service.execution_mode == "PAPER":
                    if any(p.get("symbol") == symbol for p in okx_rest_service.paper_positions):
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
        from services.okx_rest import okx_rest_service
        from config import settings

        BLITZ_SCAN_INTERVAL = 300  # 5 minutos entre ciclos de scan

        logger.info("⚡ [BLITZ-LOOP] BlitzSniper M30 monitor iniciado.")

        while self.is_running:
            try:
                # [V110.136] Executa o scan imediatamente e depois aguarda o intervalo
                # Check available slots
                slots = await firebase_service.get_active_slots()
                occupied_count = sum(1 for s in slots if s.get("symbol"))

                # [V111.3 TREND_FOCUS] Em LATERAL pausa tudo. Em TENDENCIA, max 20 slots.
                is_ranging_mode = True
                try:
                    from services.okx_ws_public import okx_ws_public_service
                    adx = getattr(okx_ws_public_service, 'btc_adx', 0)
                    is_ranging_mode = (adx < 25)
                except Exception:
                    pass

                # [V111.3] Se mercado LATERAL, bloqueia scan
                if is_ranging_mode:
                    logger.debug("[BLITZ-LOOP] Mercado LATERAL. Scan pausado.")
                    await asyncio.sleep(BLITZ_SCAN_INTERVAL)
                    continue

                balance = await bankroll_manager.get_live_operating_equity()
                if balance < 10.0 and okx_rest_service.execution_mode != "PAPER":
                    max_total_slots = 2
                else:
                    max_total_slots = 20  # [V111.3] Hard limit de 20 slots em tendencia

                if occupied_count < max_total_slots:
                    logger.info("⚡ [BLITZ-SCAN] Iniciando varredura estratégica M30...")
                    await blitz_sniper_agent.scan_and_inject(signal_generator.signal_queue)
                else:
                    logger.debug("⚡ [BLITZ-SCAN] Todos os slots ocupados. Pulando ciclo de varredura.")

                await asyncio.sleep(BLITZ_SCAN_INTERVAL)

                if not self.is_running:
                    break

                if occupied_count >= max_total_slots:
                    logger.debug("[BLITZ-LOOP] Slots ocupados. Aguardando liberação para novo scan M30.")
                    continue

                # 2. Obtém direção do BTC para filtro de tendência
                deep_macro = await self.get_deep_macro_status()
                btc_direction = deep_macro.get("direction", "LATERAL")
                btc_adx = deep_macro.get("adx", 0.0)

                # 3. Obtém a watchlist (pares ativos do radar)
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

    # =========================================================================
    # ████  DECOR_HUNTER 3.0 — Loop Paralelo de Pares Descolados do BTC  ████
    # =========================================================================

    async def _decor_hunter_loop(self):
        """
        [DECOR_HUNTER 3.0] Loop paralelo e independente que varre os 100 pares
        da DECOR_WATCHLIST a cada 30 segundos, buscando pares descolados do BTC.

        Roda em QUALQUER regime de mercado (LATERAL, TRENDING, ROARING).
        Limite próprio: DECOR_HUNTER_MAX_SLOTS = 8 slots simultâneos.

        Fluxo por par:
          1. Filtro de variação: |var_15m| >= 1.5% (par com gás próprio)
          2. Filtro de correlação: Pearson < 0.5 (descolado do BTC)
          3. Análise técnica: BLITZ M30 (score >= 65) ou var >= 2%
          4. Gera sinal com radar_mode="DECOR_HUNTER" e timestamp para TTL
          5. Injeta na fila com prioridade (-score)
        """
        from config import settings
        from services.agents.blitz_sniper import blitz_sniper_agent
        from services.agents.oracle_agent import oracle_agent as oracle_ref
        from services.okx_rest import okx_rest_service

        SCAN_INTERVAL = settings.DECOR_HUNTER_SCAN_INTERVAL  # 30s
        logger.info("[DECOR-HUNTER 3.0] Loop de varredura de 100 pares iniciado.")

        while self.is_running:
            try:
                # Verifica capacidade de slots DECOR_HUNTER
                from services.database_service import database_service
                slots = await database_service.get_active_slots()
                decor_count = sum(1 for s in slots if s.get("slot_type") == "DECOR_HUNTER")

                if decor_count >= settings.DECOR_HUNTER_MAX_SLOTS:
                    logger.debug(f"[DECOR-HUNTER 3.0] Limite de {settings.DECOR_HUNTER_MAX_SLOTS} slots atingido. Aguardando.")
                    await asyncio.sleep(SCAN_INTERVAL)
                    continue

                # Obtém contexto do BTC para análise técnica
                ctx = oracle_ref.get_validated_context()
                btc_dir = ctx.get("btc_direction", "LATERAL")
                btc_adx = ctx.get("btc_adx", 0.0)

                # Busca candles do BTC para cálculo de correlação (1 chamada para todos os pares)
                btc_klines_raw = await okx_rest_service.get_klines(symbol="BTCUSDT", interval="1", limit=17)
                if not btc_klines_raw or len(btc_klines_raw) < 15:
                    logger.debug("[DECOR-HUNTER 3.0] Dados do BTC indisponíveis. Aguardando.")
                    await asyncio.sleep(SCAN_INTERVAL)
                    continue

                btc_closes = [float(c[4]) for c in list(reversed(btc_klines_raw))[:15]]

                # Varredura da DECOR_WATCHLIST em batches de 25
                watchlist = getattr(settings, "DECOR_WATCHLIST", [])
                decor_signals = []

                for symbol in watchlist:
                    try:
                        if symbol in self.active_tocaias:
                            continue
                        # Checa cooldown
                        in_cd, _ = await self.is_symbol_in_cooldown(symbol)
                        if in_cd:
                            continue

                        result = await self._analyze_decor_pair(
                            symbol, btc_closes, btc_dir, btc_adx, blitz_sniper_agent
                        )
                        if result:
                            decor_signals.append(result)

                    except Exception as ex:
                        logger.debug(f"[DECOR-HUNTER 3.0] Erro em {symbol}: {ex}")
                        continue

                # Ordena por score e injeta os melhores na fila
                decor_signals.sort(key=lambda s: s.get("score", 0), reverse=True)

                slots_avail = settings.DECOR_HUNTER_MAX_SLOTS - decor_count
                for sig in decor_signals[:slots_avail]:
                    sym = sig["symbol"]
                    # Verifica duplicidade antes de injetar
                    if any(s.get("symbol") == sym for s in slots if s.get("symbol")):
                        continue

                    self._signal_counter = getattr(self, "_signal_counter", 0) + 1
                    await signal_generator.signal_queue.put(
                        (-sig["score"], self._signal_counter, sig)
                    )
                    logger.info(
                        f"🎯 [DECOR-HUNTER 3.0] {sym} {sig['side']} injetado | "
                        f"Score={sig['score']} | Corr={sig.get('btc_correlation', 0):.2f} "
                        f"| VarPar={sig.get('own_variation', 0):.2f}%"
                    )

                if decor_signals:
                    logger.info(f"[DECOR-HUNTER 3.0] Ciclo: {len(decor_signals)} par(es) qualificado(s) de {len(watchlist)} varridos.")
                else:
                    logger.debug(f"[DECOR-HUNTER 3.0] Ciclo: nenhum par descolado encontrado em {len(watchlist)} varridos.")

                await asyncio.sleep(SCAN_INTERVAL)

            except Exception as e:
                logger.error(f"❌ [DECOR-HUNTER 3.0] Erro no loop: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(30)

    async def _analyze_decor_pair(
        self,
        symbol: str,
        btc_closes: List[float],
        btc_dir: str,
        btc_adx: float,
        blitz_agent,
    ) -> Optional[Dict[str, Any]]:
        """
        [DECOR_HUNTER 3.0] Analisa um par para verificar:
          1. Variação própria >= 1.5% nos últimos 15m
          2. Correlação de Pearson com BTC < 0.5 (descolado)
          3. Setup técnico válido (BLITZ M30 score >= 65, ou var >= 2.0%)

        Retorna o sinal pronto para injeção, ou None se não qualificado.
        """
        try:
            from services.okx_rest import okx_rest_service

            # ── 1. Candles 1m do par (15 candles = 15 minutos)
            pair_klines_raw = await asyncio.wait_for(
                okx_rest_service.get_klines(symbol=symbol, interval="1", limit=17),
                timeout=3.0
            )
            if not pair_klines_raw or len(pair_klines_raw) < 15:
                return None

            pair_closes = [float(c[4]) for c in list(reversed(pair_klines_raw))[:15]]

            # ── 2. Variação própria nos últimos 15 candles
            own_variation = ((pair_closes[-1] - pair_closes[0]) / pair_closes[0]) * 100 if pair_closes[0] > 0 else 0.0

            if abs(own_variation) < 0.8:
                return None  # Par sem gás próprio suficiente (relaxado de 1.5% para 0.8%)

            # ── 3. Correlação de Pearson com BTC
            correlation = self._pearson_correlation(btc_closes, pair_closes)

            if abs(correlation) >= 0.65:
                return None  # Par ainda correlacionado com BTC (relaxado de 0.5 para 0.65)

            # ── 4. Determinar lado com base na variação
            direction_from_var = "Buy" if own_variation > 0 else "Sell"

            # ── 5. Confirmar com análise técnica (BLITZ M30)
            try:
                blitz_signal = await asyncio.wait_for(
                    blitz_agent.scan_for_blitz_signal(symbol, btc_dir, btc_adx),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                blitz_signal = None

            if blitz_signal and blitz_signal.get("score", 0) >= 65:
                side = blitz_signal["side"]
                tech_score = blitz_signal["score"]
                tech_reasons = blitz_signal.get("reasons", [])
            elif abs(own_variation) >= 1.0:
                # Fallback: variação forte compensa ausência de setup técnico
                side = direction_from_var
                tech_score = min(75, int(abs(own_variation) * 30))
                tech_reasons = [f"Variação própria forte: {own_variation:.2f}%"]
            else:
                return None  # Variação menor que 1.0% sem setup técnico confirmado

            return {
                "id":              f"decor_{symbol.replace('.P','')}_{int(time.time())}",
                "symbol":          symbol,
                "side":            side,
                "score":           tech_score,
                "layer":           "DECOR_HUNTER",
                "slot_type":       "DECOR_HUNTER",
                "radar_mode":      "DECOR_HUNTER",
                "strategy":        "DECOR_HUNTER",
                "timeframe":       "30",
                "btc_correlation": round(correlation, 3),
                "own_variation":   round(own_variation, 2),
                "timestamp":       time.time(),  # TTL gate usa este campo
                "reasons":         [
                    f"Descolado BTC (corr={correlation:.2f})",
                    f"Var própria: {own_variation:.2f}%",
                ] + tech_reasons,
            }

        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.debug(f"[DECOR-HUNTER 3.0] _analyze_decor_pair {symbol}: {e}")
            return None

    def _pearson_correlation(self, x: List[float], y: List[float]) -> float:
        """
        [DECOR_HUNTER 3.0] Correlação de Pearson entre dois arrays de preços.
        Retorna valor entre -1.0 (correlação inversa) e 1.0 (correlação direta).
        """
        if len(x) != len(y) or len(x) < 2:
            return 0.0
        n = len(x)
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        den_x = sum((xi - mean_x) ** 2 for xi in x) ** 0.5
        den_y = sum((yi - mean_y) ** 2 for yi in y) ** 0.5
        if den_x == 0 or den_y == 0:
            return 0.0
        return num / (den_x * den_y)

    async def _check_decor_momentum(self, symbol: str, side: str) -> bool:
        """
        [DECOR_HUNTER 3.0] Verifica se o momentum do par ainda está ativo
        antes de abrir a ordem (confirma que o movimento não esgotou).

        Critérios de descarte (momentum esgotado):
          - RSI > 80 para LONG (sobrecomprado)
          - RSI < 20 para SHORT (sobrevendido)
          - Variação dos últimos 5 candles de 1m vai contra a posição (> 0.5% inverso)

        Retorna True se o momentum está ok, False se esgotado.
        """
        try:
            from services.okx_rest import okx_rest_service

            # Busca últimos 20 candles de 1m para RSI
            klines_1m = await asyncio.wait_for(
                okx_rest_service.get_klines(symbol=symbol, interval="1", limit=22),
                timeout=3.0
            )
            if not klines_1m or len(klines_1m) < 15:
                return True  # Sem dados = não bloqueia

            closes = [float(c[4]) for c in list(reversed(klines_1m))]

            # ── RSI check
            rsi = self._calculate_rsi(closes, period=14)
            side_lower = side.lower()
            if side_lower in ("buy", "long") and rsi > 80:
                logger.info(f"[DECOR-HUNTER 3.0] {symbol} RSI={rsi:.1f} sobrecomprado. Momentum esgotado.")
                return False
            if side_lower in ("sell", "short") and rsi < 20:
                logger.info(f"[DECOR-HUNTER 3.0] {symbol} RSI={rsi:.1f} sobrevendido. Momentum esgotado.")
                return False

            # ── Variação dos últimos 5 candles (checando reversão imediata)
            if len(closes) >= 5:
                var_5c = ((closes[-1] - closes[-5]) / closes[-5]) * 100 if closes[-5] > 0 else 0.0
                if side_lower in ("buy", "long") and var_5c < -0.5:
                    logger.info(f"[DECOR-HUNTER 3.0] {symbol} var 5m={var_5c:.2f}% negativa. Reversão em curso.")
                    return False
                if side_lower in ("sell", "short") and var_5c > 0.5:
                    logger.info(f"[DECOR-HUNTER 3.0] {symbol} var 5m={var_5c:.2f}% positiva. Reversão em curso.")
                    return False

            return True

        except (asyncio.TimeoutError, Exception) as e:
            logger.debug(f"[DECOR-HUNTER 3.0] momentum check {symbol}: {e}")
            return True  # Em caso de erro, não bloqueia

    def _calculate_rsi(self, closes: List[float], period: int = 14) -> float:
        """[DECOR_HUNTER 3.0] Calcula RSI simples a partir de lista de closes."""
        if len(closes) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0.0))
            losses.append(max(-diff, 0.0))
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100.0 - (100.0 / (1.0 + rs)), 1)

    async def get_deep_macro_status(self):
        """[V110.36.8] Guilhotina Reforçada com SSOT M-ADX (Sem falsos laterais)."""

        adx = getattr(okx_ws_public_service, 'btc_adx', 0)
        
        if adx >= 30: regime = "ROARING"
        elif adx >= 25: regime = "TRENDING"
        else: regime = "RANGING"

        variation_1h = okx_ws_public_service.btc_variation_1h
        variation_15m = okx_ws_public_service.btc_variation_15m
        
        # [V110.116] DYNAMIC ADX THRESHOLD: 25 for Elite Transitions (was 30)
        if adx >= 25:
            # [V111.3 ORACLE-FIX] ADX >= 25: 1h é sempre o árbitro final
            btc_direction = "UP" if variation_1h > 0 else "DOWN"
            logger.info(f"🔥 [MARKET-REGIME] ADX {adx:.1f} detectado. Direção BTC: {btc_direction} via 1h ({variation_1h:.2f}%) | 15m={variation_15m:.2f}%")
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
            "cvd_total": okx_ws_public_service.get_cvd_score("BTCUSDT"),
            "cvd_5m": okx_ws_public_service.get_cvd_score_time("BTCUSDT", 300),
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
                
                if not symbol or slot_id not in range(1, 41):
                    continue
                
                # Rule 1: Stagnant ROI (-5% to +5%)
                is_stagnant_roi = abs(pnl_pct) <= 5.0
                
                # Rule 2: Minimum Time (45 minutes = 2700 seconds)
                is_old_enough = (now - opened_at) > 2700
                
                # Rule 3: Low Gas (institutional volume)
                cvd_score = okx_ws_public_service.get_cvd_score(symbol)
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
        strategy_class = best_signal.get("strategy_class", "VELOCITY FLOW")
        
        # [REGIME GATING & MACRO FILTER] Garantia Absoluta no Nível do Capitão
        is_ranging_mode = True
        try:
            from services.okx_ws_public import okx_ws_public_service
            adx = getattr(okx_ws_public_service, 'btc_adx', 0)
            is_ranging_mode = (adx < 25)
        except Exception:
            pass

        current_regime = "LATERAL" if is_ranging_mode else "TRENDING"

        # Get BTC Macro Trend (EMA 200 / SMA 200 base)
        macro_trend = "BULLISH"
        try:
            btc_macro = await signal_generator.get_daily_macro_filter("BTCUSDT")
            macro_trend = "BULLISH" if btc_macro.get("above_200sma", True) else "BEARISH"
        except Exception as e:
            logger.error(f"Error checking BTC macro trend: {e}")

        # Update dynamic state
        self.btc_market_regime = {
            "direction": current_regime,
            "macro": macro_trend
        }

        # 1. Filtro por regime de volatilidade (LATERAL vs TRENDING)
        if current_regime == "LATERAL":
            if strategy_class in ("VELOCITY FLOW", "ALPHA SHIELD"):
                logger.warning(f"🚫 [CAPTAIN-REGIME-BLOCK] {symbol} {strategy_class} rejeitado em mercado LATERAL.")
                return
        else:
            if strategy_class == "DECOR SHADOW":
                logger.warning(f"🚫 [CAPTAIN-REGIME-BLOCK] {symbol} DECOR SHADOW rejeitado em mercado em TENDÊNCIA.")
                return

        # 2. Filtro de Direção Macro (Trend Bias Filter)
        # Isenções:
        # - Estratégia DECOR SHADOW é imune à direção macro do BTC em qualquer regime.
        # - Se o mercado for LATERAL (ADX < 25), todos os bloqueios direcionais de tendência do BTC são ignorados.
        is_decor_shadow = strategy_class == "DECOR SHADOW"
        if not is_decor_shadow and current_regime != "LATERAL":
            if macro_trend == "BEARISH" and side.lower() in ("buy", "long", "b"):
                logger.warning(f"🚫 [CAPTAIN-MACRO-BLOCK] {symbol} {strategy_class} LONG rejeitado. Tendência Macro do BTC é BEARISH.")
                return
            elif macro_trend == "BULLISH" and side.lower() in ("sell", "short", "s"):
                logger.warning(f"🚫 [CAPTAIN-MACRO-BLOCK] {symbol} {strategy_class} SHORT rejeitado. Tendência Macro do BTC é BULLISH.")
                return
        else:
            logger.info(f"🔓 [CAPTAIN-MACRO-PASS] {symbol} {strategy_class} {side} liberado (D.S={is_decor_shadow}, Regime={current_regime}).")
        
        # [MASTER BYPASS] - Se existir OKX Master, executa diretamente na conta global.
        from config import settings
        if settings.OKX_API_KEY_MASTER or settings.OKX_EXECUTION_MODE == "PAPER":
            mode = "REAL" if settings.OKX_API_KEY_MASTER and settings.OKX_EXECUTION_MODE != "PAPER" else "PAPER"
            logger.info(f"🚀 [BYPASS] Sinal de {symbol} roteado para OKX ({mode}).")
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

            vault_blob = user_data.get("okx_vault", {})
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
        
        # Obter e normalizar a estratégia do sinal
        raw_strat = best_signal.get("strategy") or best_signal.get("strategy_class") or best_signal.get("strategy_type") or "RADAR"
        raw_strat_upper = str(raw_strat).upper()
        if raw_strat_upper in ("ALPHA SHIELD", "VELOCITY FLOW", "DECOR SHADOW"):
            strategy = raw_strat_upper
        elif raw_strat_upper in ("DVAP", "MOLA", "FAS"):
            strategy = "ALPHA SHIELD"
        elif raw_strat_upper in ("DECOR", "DECOR_HUNTER"):
            strategy = "DECOR SHADOW"
        elif raw_strat_upper in ("LRT", "TREND", "ABCD", "1-2-3", "SWING", "BLITZ_30M"):
            strategy = "VELOCITY FLOW"
        else:
            strategy = raw_strat
            
        try:
            # [V120] Verificação de Slots por Usuário
            # O sistema agora busca slots privados do usuário no Firestore
            slots = await firebase_service.get_active_slots(username=username)
            occupied_count = sum(1 for s in slots if s.get("symbol"))
            
            # [DECOR_HUNTER 2.0] Sinais de descorrelação (DECOR_HUNTER / DECOR SHADOW) são isentos do filtro LATERAL
            radar_mode = best_signal.get("radar_mode", "")
            strategy_class = best_signal.get("strategy_class", "")
            is_decor_hunter = "DECOR" in str(radar_mode).upper() or "DECOR" in str(strategy).upper() or "DECOR" in str(strategy_class).upper()
            if is_decor_hunter:
                logger.info(
                    f"[DECOR-HUNTER 3.0] {symbol} sinal recebido. "
                    f"Score={score} Side={side} | Correlação={best_signal.get('btc_correlation', 'N/A')} "
                    f"| VarPar={best_signal.get('own_variation', 'N/A')}%"
                )

                # [DECOR-HUNTER 3.0] Freshness Gate: TTL de 10 minutos
                signal_age = time.time() - best_signal.get("timestamp", 0)
                if signal_age > 600:
                    msg = f"[DECOR-HUNTER 3.0] {symbol} sinal expirado ({signal_age:.0f}s > 600s). Descartado."
                    logger.info(msg)
                    self.active_tocaias.discard(symbol)
                    return

                # [DECOR-HUNTER 3.0] Momentum check: verifica se o movimento ainda é válido
                momentum_ok = await self._check_decor_momentum(symbol, side)
                if not momentum_ok:
                    msg = f"[DECOR-HUNTER 3.0] {symbol} momentum esgotado. Descartado."
                    logger.info(msg)
                    self.active_tocaias.discard(symbol)
                    return
            if not is_decor_hunter:
                # [V111.3 TREND_FOCUS] Gating inteligente por regime
                is_ranging_mode = True
                try:
                    from services.okx_ws_public import okx_ws_public_service
                    adx = getattr(okx_ws_public_service, 'btc_adx', 0)
                    is_ranging_mode = (adx < 25)
                except Exception:
                    pass

                if is_ranging_mode:
                    # Em mercado LATERAL, apenas DECOR SHADOW é permitida
                    if strategy not in ("DECOR SHADOW", "DECOR_HUNTER"):
                        msg = f"[TREND_FOCUS] {symbol} ({strategy}) bloqueado em mercado LATERAL (ADX < 25)."
                        logger.info(msg)
                        await firebase_service.update_signal_outcome(best_signal.get("id"), "TREND_FOCUS_LATERAL_BLOCK")
                        self.active_tocaias.discard(symbol)
                        return
                else:
                    # Em mercado em TENDÊNCIA, apenas VELOCITY FLOW e ALPHA SHIELD são permitidas
                    if strategy in ("DECOR SHADOW", "DECOR_HUNTER"):
                        msg = f"[TREND_FOCUS] {symbol} ({strategy}) bloqueado em mercado em TENDÊNCIA (ADX >= 25)."
                        logger.info(msg)
                        await firebase_service.update_signal_outcome(best_signal.get("id"), "TREND_FOCUS_TRENDING_BLOCK")
                        self.active_tocaias.discard(symbol)
                        return

            max_allowed_slots = 20  # [V111.3] Hard limit de 20 slots em tendencia
            
            if occupied_count >= max_allowed_slots:
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

            strategy = best_signal.get("strategy_class") if best_signal and best_signal.get("strategy_class") else "SWING"

            
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

            # --- [V120] SENTINEL LATERAL BLOCK REMOVIDO — Ordem direta, sem filtro lateral ---
            if btc_dir == "LATERAL":
                adx_slope = current_btc_adx - self.prev_btc_adx
                self.prev_btc_adx = current_btc_adx
                logger.info(f"🔓 [V120 LATERAL-PASS] {symbol} ({side}) | BTC LATERAL — Ordem direta autorizada. ADX={current_btc_adx:.1f} Slope={adx_slope:+.2f}")

            # --- [V120] ADX<18 BLOCK REMOVIDO — Ordem direta, sem filtro lateral ---
            if current_btc_adx < 18:
                logger.info(f"🔓 [V120 ADX-PASS] {symbol} ({side}) | M-ADX={current_btc_adx:.1f}<18 — Ordem direta autorizada.")

            # --- [V120] MACRO BEAR SHIELD REMOVIDO — Ordem direta, sem filtro lateral ---
            if side.lower() in ("buy", "long", "b"):
                try:
                    from services.agents.macro_analyst import macro_analyst
                    btc_dominance_now = getattr(macro_analyst, '_dom_cache', 0.0)
                    if btc_dominance_now <= 0:
                        btc_dominance_now = 58.0
                except Exception:
                    btc_dominance_now = 58.0

                is_bear_lateral = btc_dominance_now > 57.0 and current_btc_adx < 25.0
                if is_bear_lateral:
                    logger.info(f"🔓 [V120 BEAR-PASS] {symbol} LONG | Bear lateral detectado mas ordem direta autorizada. Dom={btc_dominance_now:.1f}% ADX={current_btc_adx:.1f}.")

            # [LIBRARIAN-EARLY-SYNC] V2.1 - Busca DNA do ativo precocemente para travar o Elite Bypass
            lib_dna = await librarian_agent.get_asset_dna(symbol)
            nectar_seal = lib_dna.get("nectar_seal", "🛡️ VANGUARD")

            # [V120] VANGUARD QUALITY FILTER RELAXADO — Ordem direta, score mínimo reduzido
            if "VANGUARD" in nectar_seal and score < 60 and not is_blitz and okx_rest_service.execution_mode != "PAPER":
                msg = f"🛡️ [VANGUARD-QUALITY-BLOCK] {symbol} Score {score} < 60. Ativos Vanguard exigem confiança mínima. Abortando."
                logger.warning(msg)
                await firebase_service.log_event("CAPTAIN", msg, "INFO")
                if best_signal.get("id"):
                    await firebase_service.update_signal_outcome(best_signal.get("id"), "VANGUARD_LOW_SCORE")
                self.active_tocaias.discard(symbol)
                return
            elif is_blitz and "VANGUARD" in nectar_seal:
                logger.info(f"⚡ [BLITZ-VANGUARD-BYPASS] {symbol} ({score}) permitido apesar de ser Vanguard (Blitz Sniper prioritário).")

            # [V120] ABSOLUTE TRAP SHIELD RELAXADO — Ordem direta, score mínimo reduzido
            if "TRAP" in nectar_seal:
                if okx_rest_service.execution_mode == "PAPER" or score >= 70:
                    logger.info(f"🔓 [V120 TRAP-PASS] {symbol} ({score}) — TRAP classificado mas ordem direta autorizada.")
                else:
                    msg = f"🛡️ [LIBRARIAN-TRAP-BLOCK] {symbol} ({side}) negado: Zona de armadilha pelo Bibliotecário (Score {score} < 70). Abortando caçada."
                    logger.warning(msg)
                    await firebase_service.log_event("CAPTAIN", msg, "WARNING")
                    if best_signal.get("id"):
                        await firebase_service.update_signal_outcome(best_signal.get("id"), "LIBRARIAN_TRAP_BLOCKED")
                    self.active_tocaias.discard(symbol)
                    return

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
                await firebase_service.update_signal_outcome(best_signal.get("id"), "QUARTERMASTER_BLOCK")
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
                
            # [V120] ABSOLUTE DIRECTION SHIELD REMOVIDO — Ordem direta, sem filtro de tendência ---
            if is_counter_trend:
                can_bypass = True
                logger.info(f"🔓 [V120 COUNTER-PASS] {symbol} {side} contra-tendência BTC {btc_dir} — Ordem direta autorizada.")
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
                    if okx_rest_service.execution_mode == "PAPER":
                        if any(p.get("symbol") == symbol for p in okx_rest_service.paper_positions):
                            logger.error(f"🛑 [CRITICAL-DUP-SHIELD] {symbol} detectado em PaperPositions durante processamento. Abortando execuçao tardia.")
                            self.active_tocaias.discard(symbol)
                            return

                    allow_momentum = False
                    if market_regime == "RANGING":
                        # [V120] RANGING MOMENTUM LIBERADO — Ordem direta, sem filtro de score
                        allow_momentum = True
                        logger.info(f"🔓 [V120 RANGING-PASS] {symbol} Score={score} — Momentum em RANGING autorizado (ordem direta).")
                    else:
                        allow_momentum = True # Se não for RANGING, Momentum é liberado
                        
                    from config import settings
                    if settings.OKX_EXECUTION_MODE == "PAPER" and score >= 80:
                        allow_momentum = True
                    if not allow_momentum:
                        msg = f"⏭️ {symbol} rejeitado: SCORE={score} em LAYER={signal_layer} | Regime: {market_regime} | ADX: {current_btc_adx:.1f}"
                        logger.info(msg)
                        await firebase_service.update_signal_outcome(best_signal.get("id"), "MOMENTUM_BLOCKED")
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
                if score >= 90:
                    logger.info(f"⚡ V12.5 ELITE BYPASS: {symbol} score {score} furando cooldown!")
                    # Elite signal bypasses cooldown - continues execution
                else:
                    logger.info(f"⏱️ {symbol} no cooldown (score {score} < 90 | Restante: {remaining:.0f}s). Abortando.")
                    await firebase_service.update_signal_outcome(best_signal.get("id"), "COOLDOWN_SKIP")
                    self.active_tocaias.discard(symbol)
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
            
            # [SANDBOX] Whitelist Global & Filtro de Regime Lateral
            from config import settings as temp_settings
            clean_sym = symbol.replace(".P", "").upper()
            
            # Se for estratégia de descolamento, a whitelist correta é a DECOR_WATCHLIST (94 pares)
            is_decor_strategy = strategy in ("DECOR_HUNTER", "DECOR SHADOW")
            if is_decor_strategy:
                whitelist = getattr(temp_settings, 'DECOR_WATCHLIST', [])
            else:
                whitelist = getattr(temp_settings, 'RADAR_WATCHLIST', [])
                
            if not whitelist:
                whitelist = [
                    "SOLUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "NEARUSDT",
                    "INJUSDT", "APTUSDT", "ARBUSDT", "ATOMUSDT", "LTCUSDT",
                    "ETCUSDT", "AAVEUSDT", "UNIUSDT", "SANDUSDT", "CHZUSDT",
                    "XLMUSDT", "XRPUSDT", "TRXUSDT", "FILUSDT", "SUIUSDT"
                ]
            
            if clean_sym not in whitelist:
                consensus["approved"] = False
                consensus["reason"] = "WATCHLIST_RESTRICTED"
                logger.info(f"🚫 [FLEET-GUARD] {symbol} rejeitado. Ativo nao homologado na Watchlist correspondente.")
            elif is_market_ranging:
                if strategy not in ("DECOR SHADOW", "DECOR_HUNTER"):
                    consensus["approved"] = False
                    consensus["reason"] = "MERCADO_LATERAL_PAUSADO"
                    logger.info(f"[TREND_FOCUS] {symbol} ({strategy}) rejeitado. Mercado LATERAL ativo apenas para DECOR SHADOW.")
                else:
                    consensus["approved"] = True
            else:
                if strategy in ("DECOR SHADOW", "DECOR_HUNTER"):
                    consensus["approved"] = False
                    consensus["reason"] = "DECOR_SHADOW_BLOQUEADO_EM_TENDENCIA"
                    logger.info(f"[TREND_FOCUS] {symbol} ({strategy}) rejeitado. Estratégia de lateralidade desativada em tendência.")
                else:
                    consensus["approved"] = True
            
            if not consensus["approved"]:
                reason = consensus["reason"]
                logger.info(f"🚫 [FLEET] {symbol} REJEITADO: {reason}")
                # [V110.27.0] Log critical rejection to events for user visibility
                await firebase_service.log_event("SENTINELA", f"Caçada abortada para {symbol}: {reason}", "WARNING")
                await firebase_service.update_signal_outcome(best_signal.get("id"), f"FLEET_REJECTED: {reason}")
                self.active_tocaias.discard(symbol)
                return
            
            # Proceed with Whale-Bonus and Space Checks [V110.12.9]
            # Redundant Lateral Block removed to allow trending market entries.
            
            fleet_intel = consensus["intel"]
            
            # [V68.0] ENGINE SPACE CHECK (POTENTIAL AUDIT)
            # Only proceed if there is enough "room to move" until next resistance/liquidity zone.
            # [V110.16.0] MODO ASSALTO REMOVIDO: Todos os sinais (mesmo Score 95+) devem passar pela auditoria de espaço.
            current_p_audit = okx_ws_public_service.get_current_price(symbol)
            if current_p_audit > 0:
                space_audit = await self._check_engine_space(symbol, side, current_p_audit)
                if not space_audit.get("valid", True):
                    msg = f"🚫 [V68.0 ENGINE SPACE] Rejeitado: Espaço de manobra insuficiente."
                    logger.warning(msg)
                    await firebase_service.update_signal_outcome(best_signal.get("id"), "ENGINE_SPACE_REJECTED")
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
                best_signal.get("id"), 
                "HUNTING", 
                {"indicators.pattern": "TOCAIA"}
            )

            # [V110.141] Injetar no RTDB para visibilidade instantânea no Cockpit
            try:
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
            
            should_bypass_ambush = score >= 90 or local_cvd > 50000 or current_btc_adx >= 50

            
            if should_bypass_ambush:
                msg = (
                    f"⚡ [V110.113 DIRECT-ENTRY] {symbol} ({side}) | "
                    f"Score {score} + CVD {local_cvd:.0f} + ADX {current_btc_adx:.1f} | "
                    f"Entrada direta — bypassando Tocaia!"
                )
                logger.info(msg)
                await firebase_service.log_event("CAPTAIN", msg, "SUCCESS")
                await firebase_service.update_signal_outcome(best_signal.get("id"), "DIRECT_ENTRY")
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
                    await firebase_service.update_signal_outcome(best_signal.get("id"), "AMBUSH_TIMEOUT")
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
                await firebase_service.update_signal_outcome(best_signal.get("id"), "STRONG_TREND_ACELERATOR")
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
                    logger.info(f"🚫 [PULLBACK HUNTER] {symbol} rejeitado: {rejection}")
                    await firebase_service.update_signal_outcome(best_signal.get("id"), f"{rejection}")
                    self.active_tocaias.discard(symbol)
                    return

                await firebase_service.update_signal_outcome(
                    best_signal.get("id"),
                    "PRICE_STRUCTURE_OK",
                    {"indicators.pattern": best_signal["indicators"]["pattern"]}
                )
                best_signal["adaptive_sl"] = price_check.get("adaptive_sl", 0)

                # [V41.5] Needle Flip: Confirmação de fluxo CVD + MSS.
                flip_confirmed = await self._wait_for_needle_flip(symbol, side, max_wait=10, signal_data=best_signal)

                if not flip_confirmed:
                    logger.info(f"⏭️ [NEEDLE FLIP] {symbol} não confirmou exaustão CVD+Volume.")
                    await firebase_service.update_signal_outcome(best_signal.get("id"), "NEEDLE_FLIP_FAIL")
                    return
                
            await firebase_service.update_signal_outcome(best_signal.get("id"), "NEEDLE_FLIP_OK")
            logger.info(f"🎯 V36.4 PULLBACK ALVO PRONTO: {symbol}")
            await firebase_service.update_signal_outcome(best_signal.get("id"), "PICKED")
            
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
                if getattr(settings, "OKX_EXECUTION_MODE", "").upper() == "PAPER":
                    logger.info(f"💎 [PAPER-BYPASS] Ignorando ANTI-CONCENTRATION (3 trades/dia) para {symbol} em modo simulado.")
                else:
                    logger.info(f"🚫 [ANTI-CONCENTRATION] {symbol} bloqueado (limite 3 trades/dia).")
                    await firebase_service.update_signal_outcome(best_signal.get("id"), "CONCENTRATION_BLOCK")
                    return
                
            # [V110.810] GUARDIAO DA BANCA: gate preventivo acima do Capitao.
            # Protege lucro acumulado, suspende pares perdedores e limita exposicao.
            try:
                from services.agents.bankroll_guardian import bankroll_guardian
                guardian_decision = await bankroll_guardian.authorize_new_trade(best_signal)
                best_signal["bankroll_guardian"] = {
                    "approved": guardian_decision.get("approved"),
                    "mode": guardian_decision.get("mode"),
                    "health_score": guardian_decision.get("health_score"),
                    "score": guardian_decision.get("score"),
                    "radar_score": guardian_decision.get("radar_score"),
                    "unified_confidence": guardian_decision.get("unified_confidence"),
                    "reasons": guardian_decision.get("reasons", []),
                }
                if not guardian_decision.get("approved", False):
                    reason = " | ".join(guardian_decision.get("reasons", []))
                    logger.warning(f"[GUARDIAO-BANCA] {symbol} bloqueado: {reason}")
                    await firebase_service.log_event(
                        "GUARDIAO_BANCA",
                        f"Entrada bloqueada em {symbol}: {reason}",
                        "WARNING"
                    )
                    await firebase_service.update_signal_outcome(
                        best_signal.get("id"),
                        f"BANKROLL_GUARDIAN_BLOCK: {reason}"
                    )
                    self.active_tocaias.discard(symbol)
                    return
            except Exception as e:
                logger.error(f"[GUARDIAO-BANCA] Falha ao avaliar {symbol}; seguindo com protecoes existentes: {e}")

            # [V110.12.10] ATOMIC SLOT RE-VERIFICATION (Anti-Slot Overwrite)
            # Antes de enviar o sinal para o Bankroll, verificamos se o slot ainda está LIVRE no Firebase.
            # Isso evita que o sinal 'atropelado' substitua uma ordem que acabou de entrar.
            slot_type = best_signal.get("slot_type", strategy)
            slot_id = await bankroll_manager.can_open_new_slot(symbol=symbol, slot_type=slot_type)
            if not slot_id:
                logger.warning(f"🚨 [V110.12.10 ATOMIC LOCK] {symbol} finalizou Tocaia, mas slot ocupado ou indisponível. Abortando.")
                await firebase_service.update_signal_outcome(best_signal.get("id"), "ATOMIC_SLOT_LOCK_REJECT")
                return
            
            # Verificação Redundante de Segurança: Símbolo Único Global
            active_slots = await firebase_service.get_active_slots(force_refresh=True)
            if any(s.get("symbol") == symbol for s in active_slots):
                logger.warning(f"🚨 [V110.12.10 SYMBOL LOCK] {symbol} já está em um slot. Abortando duplicata tardia.")
                await firebase_service.update_signal_outcome(best_signal.get("id"), "SYMBOL_ALREADY_ACTIVE")
                return
                
            # [V110.62] CORRELATION SHIELD: Proteção contra Risco Espelhado
            # Não permitimos abrir ordens em ativos que se movem de forma idêntica aos que já temos em aberto.
            # Isso impede que um único movimento do mercado (ex: crash de ALTs) liquide múltiplos slots simultaneamente.
            for slot in active_slots:
                active_sym = slot.get("symbol")
                if active_sym and active_sym != symbol:
                    correlation = okx_ws_public_service.get_correlation(active_sym, symbol)
                    if abs(correlation) >= 0.85:
                        logger.warning(f"🛡️ [V110.62 CORRELATION-SHIELD] Bloqueando entrada em {symbol}. Correlação de {correlation:.2f} com {active_sym} (Limite: 0.85).")
                        await firebase_service.update_signal_outcome(best_signal.get("id"), f"CORRELATION_BLOCK_{active_sym}")
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
                target_slot_id=slot_id,
                username=username,
                credentials=credentials
            )
            
            if order:
                self.last_traded_symbol = symbol
                sym_trades['count'] += 1
                if sym_trades['first_trade_at'] == 0:
                    sym_trades['first_trade_at'] = time.time()
                self.daily_symbol_trades[norm_symbol_ac] = sym_trades
                if is_decor_hunter:
                    logger.info(
                        f"[DECOR-HUNTER 2.0] Posicao aberta: {symbol} Slot {slot_id} "
                        f"Score={score}"
                    )
                    await firebase_service.log_event(
                        "DECOR_HUNTER",
                        f"Posicao aberta {symbol} Slot {slot_id} Score={score}",
                        "INFO"
                    )
                logger.info(f"✅ SNIPER SHOT DEPLOYED: {symbol} (Slot {slot_id})")
                
                # [HERMES TELEGRAM] Alerta de Nova Ordem
                try:
                    from services.telegram_service import telegram_service
                    await telegram_service.send_message(f"🎯 <b>NOVA ORDEM ABERTA</b>\nPar: {symbol}\nEstratégia: {strategy}")
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
                
                # [DECOR_HUNTER 2.0] BTC Rug Pull Protection (every 2 min)
                if (time.time() - self.last_btc_rug_pull_check) > 120:
                    await self._btc_rug_pull_check()
                    self.last_btc_rug_pull_check = time.time()
                
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
            close_ok = await okx_rest_service.close_position(
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

    async def _btc_rug_pull_check(self):
        """
        [DECOR_HUNTER 2.0] BTC Rug Pull Protection.
        Se BTC mover >1% em 15min, aperta stops de todas posicoes DECOR_HUNTER
        para evitar arraste sistemico em pânico de mercado.
        """
        try:
            from services.okx_ws_public import okx_ws_public_service
            btc_var_15m = getattr(okx_ws_public_service, 'btc_variation_15m', 0.0)
            if abs(btc_var_15m) <= 1.0:
                return

            from services.firebase_service import firebase_service
            slots = await firebase_service.get_active_slots()
            decor_slots = [
                s for s in slots
                if s.get("symbol") and s.get("slot_type") == "DECOR_HUNTER"
            ]
            if not decor_slots:
                return

            logger.warning(
                f"[DECOR-HUNTER 2.0] BTC rug pull detectado ({btc_var_15m:+.2f}% em 15m). "
                f"Apertando stops de {len(decor_slots)} posicoes DECOR_HUNTER."
            )
            await firebase_service.log_event(
                "DECOR_HUNTER",
                f"BTC rug pull ({btc_var_15m:+.2f}%): apertando stops de {len(decor_slots)} posicoes",
                "WARNING"
            )

            from services.database_service import database_service
            for s in decor_slots:
                slot_id = s.get("id")
                symbol = s["symbol"]
                side = (s.get("side") or "buy").lower()
                entry_price = float(s.get("entry_price", 0))
                current_price = okx_ws_public_service.get_current_price(symbol)
                if current_price <= 0:
                    continue

                current_stop = float(s.get("current_stop", 0))
                tight_margin = 0.02  # 2% de margem em vez de 5%
                if side == "buy":
                    tight_stop = current_price * (1 - tight_margin)
                else:
                    tight_stop = current_price * (1 + tight_margin)

                # So atualiza se melhorar o stop atual
                if current_stop > 0:
                    if side == "buy" and tight_stop <= current_stop:
                        continue
                    if side == "sell" and tight_stop >= current_stop:
                        continue

                await database_service.update_slot(slot_id, {"current_stop": tight_stop})
                logger.info(
                    f"[DECOR-HUNTER 2.0] {symbol} stop apertado de "
                    f"${current_stop:.4f} → ${tight_stop:.4f} (rug pull {btc_var_15m:+.2f}%)"
                )
        except Exception:
            pass

    async def _wait_for_needle_flip(self, symbol: str, side: str, max_wait: int = 15, signal_data: dict = None) -> bool:
        """
        [V7.0] THE PERFECT ENTRY: Wait Sniper Protocol.
        Monitors for confluence (Fibonacci/Walls) and Signal Maturity.
        """
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

            # Type D: [V110.24.0 REFINED] Score >= 70 libera entrada sem MSS obrigatório
            score_val = signal_data.get("score", 0) if signal_data else 0
            if score_val >= 70 and confidence >= 30:
                logger.info(f"🚀 [ELITE BYPASS V110.24] Score {score_val} + Conf {confidence:.1f}%. Disparo direto!")
                return True

            # Type D2: Score >= 90 entra direto mesmo com confiança baixa
            if score_val >= 90 and confidence >= 10:
                logger.info(f"🚀 [ELITE BYPASS V111.4] Score {score_val} + Conf {confidence:.1f}%. Disparo direto!")
                return True

            # Type E: [V110.24.0 TIME PRESSURE] Após 15s, entrada forçada (Elite >= 10%, Normal >= 20%)
            elapsed = time.time() - start_time
            score_val = signal_data.get("score", 0) if signal_data else 0
            min_conf_bypass = 10 if score_val >= 90 else 20
            if elapsed >= 15 and confidence >= min_conf_bypass:
                logger.info(f"🚀 [TIME PRESSURE V111.4] Entrada forçada para {symbol} após {elapsed:.0f}s (Conf: {confidence:.1f}% >= {min_conf_bypass}%).")
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
        
        signal_price = okx_ws_public_service.get_current_price(symbol)
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
            current_price = okx_ws_public_service.get_current_price(symbol)
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
        final_price = okx_ws_public_service.get_current_price(symbol)
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
