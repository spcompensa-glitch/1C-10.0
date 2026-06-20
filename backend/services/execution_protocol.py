# -*- coding: utf-8 -*-
"""
\U0001f6e1\ufe0f Protocolo de Execução Elite V15.0 - Consciousness Edition
==========================================================
Módulo responsável por executar lógica de fechamento independente por slot.
Implementa Smart SL com 4 fases: SAFE → RISK_ZERO → PROFIT_LOCK → MEGA_PULSE.

Author: Antigravity AI
Version: 15.0 (Consciousness Edition)

V15.0 Changes:
- MAX_RISK_PCT: 1% (máximo risco por trade)
- TARGET_PCT: 2% (alvo mínimo para R:R 1:2)
- Structural Stop: 0.5% além do swing high/low
- Trade cancelado se Risk:Reward < 1:2
"""

import logging
import time
from typing import Tuple, Optional, Dict, Any

logger = logging.getLogger("ExecutionProtocol")


# V14.1 Stabilization Protocol Phases
# [V110.23.3] DEEP CLEAN: SAFE phase removed to allow maximum breathing room until 70% ROI.
SMART_SL_PHASES = {
    "PHASE_SAFE":         {"trigger_roi": 0.0,   "stop_roi": -30.0,  "icon": "🔴", "color": "red",     "label": "INICIAL"},
    "PHASE_RISK_ZERO":    {"trigger_roi": 50.0,  "stop_roi": 25.0,   "icon": "🛡️", "color": "green",   "label": "RISK_ZERO"},
    "PHASE_LUCRO_80":     {"trigger_roi": 80.0,  "stop_roi": 50.0,   "icon": "⚖️", "color": "cyan",    "label": "LUCRO_80"},
    "PHASE_PROFIT_LOCK":  {"trigger_roi": 100.0, "stop_roi": 75.0,   "icon": "🔒", "color": "blue",    "label": "PROFIT_LOCK"},
    "PHASE_MEGA_PULSE":   {"trigger_roi": 130.0, "stop_roi": 110.0,  "icon": "💎", "color": "diamond", "label": "MEGA_PULSE"}
}

# V12.0 Risk Management Constants
V12_MAX_RISK_PCT = 1.0      # [V24.0] 10D Strict: Max 1.0% Risk per trade
V12_TARGET_PCT = 2.0        # [V24.0] 10D Strict: Target 2.0% (100% ROI)
V12_STRUCTURAL_BUFFER = 2.5 # [V110.22.0] Restored to 2.5% for correct breathing (User Request)

# [V36.0] Rescue Mode Constants
RESCUE_ACTIVATION_ROI = -999.0   # [V110.12.11] DESATIVADO: Evita ordens zumbis
HARD_STOP_ROI = -50.0          # [V110.24.0] Hard Stop atômico fixo em -50% conforme especificado pelo usuário

# [V88.0] MAESTRIA SIMPLIFIED - DESATIVADO PARA UNIFICAÇÃO SNIPER
# MAESTRIA_FEE_GUARD_TRIGGER = 60.0 
# MAESTRIA_FEE_GUARD_EXIT = 25.0

class ExecutionProtocol:
    """
    Executa a lógica de fechamento para cada slot de forma independente.
    Cada ordem tem seu próprio 'contrato de execução'.
    
    V15.0 Consciousness Edition:
    - Risk validation: Trade só abre se risco <= 1%
    - Structural Stop: 0.5% além do swing high/low
    - Cancel trade se R:R desfavorável (< 1:2)
    """
    
    def __init__(self):
        self.leverage = 50
        
        # ROI Thresholds (Default/Trend)
        self.mega_pulse_roi = 150.0  # 150% ROI (3.0% price @ 50x)
        
        # [V110.22.0] Fibonacci 4H Cache (Moonbags)
        self._fib_cache = {} # {symbol: {"updated_at": float, "levels": dict}}
        
        # [V110.12.11] MONITORING THROTTLE
        self.last_check_times = {} # {symbol: timestamp}
        
        # [V33.1] SCALP Thresholds (Slots 1 e 2 - Batalhão Rápido com Fôlego)
        # Protege entrada cedo (Breakeven), depois respira até 80% ROI
        self.scalp_risk_zero_roi = 100.0    # [V87.0] Fôlego Macro
        self.scalp_profit_lock_roi = 150.0  # [V87.0] Trava lucro mais tarde
        self.scalp_target_roi = 200.0      # [V87.0] Mega Pulse em 200%
        
        self.sniper_target_roi = 100.0 # Alvo secundário para força extrema
        
        # [V28.1] Dynamic Trailing Gaps
        self.mega_pulse_trailing_gap = 15.0 # [V42.3] Gap Aperto (era 20)
        self.trend_mega_pulse_trailing_gap = 45.0 # Batalhão Pesado (SWING gap: 0.9% price) for 72h survivability
        
        # V12.0: Risk Validation
        self.max_risk_pct = V12_MAX_RISK_PCT
        self.target_pct = V12_TARGET_PCT
        self.structural_buffer = V12_STRUCTURAL_BUFFER
        
        # === VISUAL STATUS CODES ===
        self.STATUS_SCANNING = "SCANNING"       # Azul - slot livre
        self.STATUS_IN_TRADE = "IN_TRADE"       # Dourado - posição aberta
        self.STATUS_RISK_ZERO = "RISK_ZERO"     # Verde - stop na entrada ou acima
        self.STATUS_STABILIZE = "STABILIZE"     # Azul Marinho - SL em +20%
        self.STATUS_FLASH_SECURE = "FLASH_SECURE" # Roxo - SL em +60%
        self.STATUS_MEGA_PULSE = "MEGA_PULSE"   # \U0001f48e V11.0: Trailing Profit (ROI > 100%)
        self.STATUS_PROFIT_LOCK = "PROFIT_LOCK" # \U0001f7e1 V11.0: Lucro travado
    
    def validate_risk_reward(self, entry_price: float, stop_loss: float, side: str) -> Tuple[bool, str]:
        """
        V12.0: Valida se o trade atende aos critérios de risco.
        
        Args:
            entry_price: Preço de entrada
            stop_loss: Preço do stop loss
            side: 'Buy' ou 'Sell'
            
        Returns:
            (is_valid, reason)
        """
        if entry_price <= 0 or stop_loss <= 0:
            return False, "Preços inválidos"
        
        side_norm = side.lower()
        
        # Calcula risco em %
        if side_norm == "buy":
            risk_pct = abs(entry_price - stop_loss) / entry_price * 100
        else:
            risk_pct = abs(stop_loss - entry_price) / entry_price * 100
        
        # Valida risco máximo
        if risk_pct > self.max_risk_pct:
            return False, f"Risco {risk_pct:.2f}% > Máximo {self.max_risk_pct}%"
        
        # Calcula R:R
        potential_gain = self.target_pct
        risk_reward = potential_gain / risk_pct if risk_pct > 0 else 0
        
        if risk_reward < 2.0:
            return False, f"R:R {risk_reward:.1f}:1 < Mínimo 2:1"
        
        return True, f"OK: Risk {risk_pct:.2f}% | R:R {risk_reward:.1f}:1"
    
    def calculate_structural_stop(self, entry_price: float, swing_price: float, side: str) -> float:
        """
        V12.0: Calcula stop estrutural 0.5% além do swing high/low.
        
        Args:
            entry_price: Preço de entrada
            swing_price: Swing high/low recente
            side: 'Buy' ou 'Sell'
            
        Returns:
            Preço do stop loss estrutural
        """
        buffer = self.structural_buffer / 100  # 0.5%
        
        if side.lower() == "buy":
            # Stop abaixo do swing low
            return swing_price * (1 - buffer)
        else:
            # Stop acima do swing high
            return swing_price * (1 + buffer)
        
    def calculate_ambush_price(self, entry_price: float, stop_loss: float, side: str, **kwargs) -> float:
        """
        [V110.22.0] CALCULA A ZONA DE LAMBIDA (AMBUSH ZONE):
        Define o preço ideal de entrada para o modo Tocaia.
        A lambida ocorre em 70% do caminho entre a entrada sugerida e o stop loss.
        """
        if entry_price <= 0 or stop_loss <= 0:
            return entry_price
        
        diff = abs(entry_price - stop_loss)
        # [V2.0] Suporte a multiplicador customizado (Librarian DNA)
        multiplier = kwargs.get("multiplier", 0.70)
        lambida_offset = diff * multiplier  # Recuo em direção ao stop
        
        if side.lower() == "buy":
            # Para Long, a lambida é ABAIXO da entrada (mais perto do stop técnico)
            return entry_price - lambida_offset
        else:
            # Para Short, a lambida é ACIMA da entrada
            return entry_price + lambida_offset
        
    def get_visual_status(self, slot_data: Dict[str, Any], roi: float) -> str:
        """
        Determina o status visual do slot baseado no estado atual.
        
        Returns:
            Status code para coloração do slot no frontend
        """
        symbol = slot_data.get("symbol")
        slot_id = slot_data.get("id", 0)
        from services.bankroll import get_slot_type
        slot_type = slot_data.get("slot_type") or get_slot_type(slot_id)
        current_stop = slot_data.get("current_stop", 0)
        entry_price = slot_data.get("entry_price", 0)
        
        # Slot vazio
        if not symbol or entry_price <= 0:
            return self.STATUS_SCANNING
        
        # SNIPER: Mega Pulse (ROI >= 100%), Flash Zone (80%+), Risk Zero, ou In Trade
        if roi >= 100.0:
            return self.STATUS_MEGA_PULSE
            
        if slot_type == "SNIPER":
            if roi >= self.phase_flash_secure_trigger if hasattr(self, "phase_flash_secure_trigger") else 80.0:
                return self.STATUS_FLASH_SECURE
            
            if roi >= self.phase_stabilize_trigger if hasattr(self, "phase_stabilize_trigger") else 60.0:
                return self.STATUS_STABILIZE

            # V14.1: Detecta se SL foi movido para lucro (Risk Zero) ou estabilizado
            side = slot_data.get("side", "Buy")
            side_norm = (side or "").lower()
            if current_stop > 0 and entry_price > 0:
                # Se o stop está além da entrada, é pelo menos RISK_ZERO
                is_beyond_entry = False
                if side_norm == "buy":
                    is_beyond_entry = current_stop >= entry_price
                elif side_norm == "sell":
                    is_beyond_entry = current_stop <= entry_price
                
                if is_beyond_entry:
                    return self.STATUS_RISK_ZERO
            
            return self.STATUS_IN_TRADE
        
        return self.STATUS_IN_TRADE


    def calculate_roi(self, entry_price: float, current_price: float, side: str, leverage: float = 50.0) -> float:
        """
        Calcula o ROI real considerando a alavancagem utilizada (V110.135 Adaptive).
        """
        if entry_price <= 0:
            return 0.0
            
        side_norm = (side or "").lower()
        
        if side_norm == "buy":
            price_diff = (current_price - entry_price) / entry_price
        else:  # Sell/Short
            price_diff = (entry_price - current_price) / entry_price
            
        roi = price_diff * leverage * 100
        
        # [V110.12.9] ANTI-MASSACRE: No Paper Mode, não permitimos ROI < -50% (Liquidação total da margem)
        # Ajustado para limitar o ROI visual e estatístico de perda ao stop atômico fixo em -50%.
        from config import settings
        if getattr(settings, "EXECUTION_MODE", "PAPER") == "PAPER":
            if roi <= -50.0:
                roi = -50.0
                logger.warning(f"💥 [LIQUIDATION PROTECT] {side} ROI capped at -50% (Atomic Stop Loss Protection).")
        
        # V6.0: ROI Sanity Guard - Cap extreme values to prevent UI breakage
        if roi > 5000: roi = 5000
        if roi < -5000: roi = -5000
        
        return roi
    
    async def _check_sentiment_weakness(self, symbol: str, side: str) -> bool:
        """
        V5.4.5: Checks if sentiment (CVD) is contradicting the trade.
        Returns True if 'weakness' is detected.
        """
        from services.redis_service import redis_service
        cvd = await redis_service.get_cvd(symbol)
        side_norm = side.lower()
        
        # Weakness threshold: 10k USD delta in opposite direction
        if side_norm == "buy" and cvd < -10000:
            logger.info(f"🛡️ [SENTI WEAKNESS] {symbol} | Long trade with Negative CVD: {cvd:.2f}")
            return True
        elif side_norm == "sell" and cvd > 10000:
            logger.info(f"🛡️ [SENTI WEAKNESS] {symbol} | Short trade with Positive CVD: {cvd:.2f}")
            return True
            
        return False

    async def process_sniper_logic(self, slot_data: Dict[str, Any], current_price: float, roi: float, atr: Optional[float] = None) -> Tuple[bool, Optional[str], Optional[float]]:
        """
        [V110.12.14] Sniper protection logic — Fixed Variable Scope.
        6 fases de proteção progressiva baseado em ROI e Gás (CVD).
        """
        # 0. Define variables at the very TOP to avoid UnboundLocalError
        symbol = slot_data.get("symbol", "UNKNOWN")
        side = slot_data.get("side", "Buy")
        entry = slot_data.get("entry_price", 0)
        current_sl = slot_data.get("current_stop", 0)
        side_norm = side.lower()
        is_emancipated = slot_data.get("status") == "EMANCIPATED"
        leverage = float(slot_data.get("leverage", 50.0)) # [V110.135]

        # [V110.12.11] MONITORING THROTTLE & FAILOVER
        now = time.time()
        last_check = self.last_check_times.get(symbol, 0)
        if now - last_check < 2.0:
             return False, "THROTTLED", None
        self.last_check_times[symbol] = now

        # [V110.12.11] PRICE FAILOVER (Redundância REST)
        if not current_price or current_price <= 0:
            from services.okx_rest import okx_rest_service
            ticker_data = await okx_rest_service.get_tickers(symbol)
            if ticker_data and ticker_data.get("result", {}).get("list"):
                current_price = float(ticker_data["result"]["list"][0].get("lastPrice", 0))
                logger.info(f"🛡️ [FAILOVER-REST] Price recovered for {symbol}: ${current_price}")
            
        if not current_price or current_price <= 0:
            return False, "PRICE_UNAVAILABLE", None
        
        # V15.4: PROGRESSIVE TRAILING — Triggers proporcionais ao espaço restante
        structural_target = slot_data.get("structural_target", 0)
        
        # Calcular expected_roi: quanto ROI o target estrutural representa
        if structural_target > 0 and entry > 0:
            if side_norm == "buy":
                expected_move_pct = (structural_target - entry) / entry * 100
            else:
                expected_move_pct = (entry - structural_target) / entry * 100
            expected_roi = expected_move_pct * leverage
        else:
            expected_roi = 100.0  # Fallback: assume 2% target (100% ROI @ 50x)
        
        # Escalar triggers proporcionalmente (mínimo 40% ROI para garantir espaço)
        expected_roi = max(40.0, expected_roi)
        scale = expected_roi / 100.0  # 1.0 = 100% ROI, 0.8 = 80% ROI, 3.0 = 300% ROI
        
        # [V15.4] scale_trigger: Garante que alvos curtos não "esganem" o trade cedo demais
        scale_trigger = max(1.0, scale)

        # [V28.5] slot_type must be resolved BEFORE the SL check block uses it
        slot_type = slot_data.get("slot_type", "TREND")
        slot_id = slot_data.get("id", 0)

        # 🛑 [V62.0 MAESTRIA] HARD STOP LOSS — Rede de Segurança Máxima
        # Se Bybit falhou em pegar o SL estrutural, matamos aqui em -60%.
        if roi <= HARD_STOP_ROI:
            logger.warning(f"🛑 [V62.0 MAESTRIA] HARD STOP FINAL: {symbol} ROI={roi:.1f}% (threshold={HARD_STOP_ROI}%)")
            return True, f"SNIPER_SL_HARD_STOP ({roi:.1f}%)", None
        
        # 🛡️ [V84.1] DIPLOMATIC IMMUNITY — Proteção contra fechamento prematuro (60s)
        # O Fee Guard só pode agir se a ordem tiver pelo menos 60 segundos de vida.
        opened_at = slot_data.get("opened_at", 0)
        # Se opened_at for 0, pula a imunidade garantindo 61s
        life_seconds = (time.time() - opened_at) if opened_at > 0 else 61
        
        # [V110.65] Saída por Inércia (Zumbis) - Relaxada para 8 horas:
        # Muitas moedas ACUMULAM por horas antes de explodir. 4h era pouco.
        # PROTEÇÃO: Se ADX > 25, não mata por inércia (tendência pode estar se armando).
        if life_seconds > 28800 and abs(roi) < 5.0 and not is_emancipated:
            from services.okx_ws_public import okx_ws_public_service
            current_adx = getattr(okx_ws_public_service, 'btc_adx', 0)
            if current_adx < 25:
                logger.warning(f"🧟 [SHADOW-PREEMPTION] Inertia Detected: {symbol} estagnado por {int(life_seconds/3600)}h (ROI={roi:.1f}%) e ADX {current_adx:.1f} baixo. Liberando slot.")
                return True, "INERTIA_EXIT_FOR_PREEMPTION", None
            else:
                logger.info(f"🛡️ [INERTIA-SHIELD] {symbol} estagnado mas mantido por ADX {current_adx:.1f} saudável.")

        if life_seconds < 60:
            if life_seconds % 10 == 0: # Log intervalado para visibilidade
                logger.info(f"🛡️ [V84.1 IMMUNITY] {symbol} Shield Active ({int(life_seconds)}s/60s). Blocking Fee Guard apenas.")
            # NÃO bloqueamos o fluxo total aqui, pois isso mataria o Trailing Stop e a Emancipação em pumps rápidos!


        # \U0001f6e1\ufe0f 1. Universal Stop Loss Check
        if current_sl > 0:
            if (side_norm == "buy" and current_price <= current_sl) or \
               (side_norm == "sell" and current_price >= current_sl):
                
                phase = self.get_sl_phase(roi, scale=scale)
                
                # --- [SENTINEL 3.0: MUROS INTELIGENTES] ---
                # Se o preço atingiu o Stop, verificamos se o Gás (CVD+ADX) é favorável.
                # Se for favorável, concedemos um respiro adaptativo baseado no ATR.
                
                # [V110.60] UNIVERSAL SENTINEL:
                # Liberado respiro diplomático para Moonbags se o Gás estiver a favor.
                # A soberania do Profit-Lock agora é protegida pelo respiro tático.
                if is_emancipated:
                    logger.info(f"🛡️ [MOONBAG-SENTINEL-V110.60] {symbol} atingiu SL de lucro. Ativando respiro dinâmico.")

                # [V110.28.1] ADAPTIVE SENTINEL: Respiro baseado na volatilidade (ATR)
                # Volatilidade alta = Respiro curto (30s). Volatilidade baixa = Respiro longo (90s).
                base_respir = 60
                if atr and entry > 0:
                    volatility_pct = (atr / entry) * 100
                    # Se volatilidade > 0.5% (muito nervoso), reduz para 30s. Se < 0.1%, sobe para 90s.
                    if volatility_pct > 0.5: base_respir = 30
                    elif volatility_pct < 0.1: base_respir = 90
                    else: base_respir = 60
                
                sentinel_hit = slot_data.get("sentinel_first_hit_at", 0)
                now = time.time()
                
                if sentinel_hit == 0:
                    # Primeira vez que toca o SL: Checamos o Gás
                    is_gas_favorable = await self._check_gas_favorable(symbol, side)
                    if is_gas_favorable:
                        logger.info(f"🛡️ [SENTINEL-HOLD] {symbol} SL atingido mas Gás favorável. Iniciando paciência diplomática ({base_respir}s).")
                        # Retornamos False (não fechar) e sinalizamos para salvar o timestamp
                        return False, "SENTINEL_ACTIVATE", now
                    else:
                        logger.info(f"🛑 [SENTINEL-DENIED] {symbol} SL atingido e Gás desfavorável. Fechando imediatamente.")
                else:
                    # Já estamos sob proteção do Sentinel: Verificamos o tempo e o Gás atual
                    elapsed = now - sentinel_hit
                    if elapsed > base_respir:
                        logger.warning(f"🛑 [SENTINEL-TIMEOUT] {symbol} Paciência diplomática esgotada ({elapsed:.1f}s/{base_respir}s). Fechando ordem.")
                    else:
                        # Ainda dentro do prazo, re-checa o gás para ver se a força continua
                        still_favorable = await self._check_gas_favorable(symbol, side)
                        if still_favorable:
                            if int(elapsed) % 10 == 0: # Log a cada 10s
                                logger.info(f"🛡️ [SENTINEL-WAITING] {symbol} mantido por Gás favorável ({elapsed:.1f}s/{base_respir}s).")
                            return False, "SENTINEL_WAITING", None
                        else:
                            logger.warning(f"🛑 [SENTINEL-GAS-FLIP] {symbol} Gás virou contra a posição durante carência. Fechando agora.")

                # Se chegou aqui, é fechamento real
                logger.info(f"🛑 SNIPER SL HIT: {symbol} Price={current_price} | SL={current_sl} | Phase={phase}")
                return True, f"SNIPER_SL_{phase} ({roi:.1f}%)", None



        # Trailing stop and exit for emancipated positions/moonbags are handled by FlashAgent.
        pass


        # ⚡ [V110.137 BLITZ DOUTRINA DAS 10] — Slots 1 e 2 Exclusivos
        # Step-Lock por Unidade (meta diaria = 10 unidades x 100% ROI)
        # UNIT 1: >= 100% ROI -> SL em +95%  (buffer 5% para taxas Bybit)
        # UNIT 2: >= 200% ROI -> SL em +180% (buffer 20%)
        # UNIT 3: >= 300% ROI -> SL em +270% + Moonbag Condicional via Ceifeiro
        # Breakeven Adaptativo: RETEST_HEAVY/EXTREME wick -> mais folego antes do BE
        if slot_type == "BLITZ_30M":
            # Wick-Adaptive Breakeven via Librarian DNA
            try:
                from services.agents.librarian import librarian_agent
                blitz_dna = await librarian_agent.get_asset_dna(symbol)
                wick_mult = float(blitz_dna.get("wick_multiplier", 1.0))
                is_retest_heavy = blitz_dna.get("is_retest_heavy", False)
            except Exception:
                wick_mult = 1.0
                is_retest_heavy = False

            if wick_mult >= 3.0 or is_retest_heavy:
                breakeven_blitz = 60.0  # Pavio extremo ou retest: folego maximo
            elif wick_mult >= 2.0:
                breakeven_blitz = 50.0  # Ativo instavel: folego moderado
            else:
                breakeven_blitz = 30.0  # Ativo limpo: breakeven padrao

            target_stop_blitz = 0

            if roi >= 150.0 and not is_emancipated:
                # [V124] EMANCIPAÇÃO BLITZ: ROI >= 150% -> Liberar slot tático e mover para Moonbag
                # SL fixado em +110% para garantir lucro mesmo que o preço recue
                target_stop_blitz = 110.0
                logger.info(f"[V124 BLITZ-EMANCIPAÇÃO] {symbol} ROI={roi:.0f}% >= 150% -> Emancipando para Moonbag! SL: +110%")
                from services.okx_rest import okx_rest_service
                price_offset_pct = target_stop_blitz / (leverage * 100)
                new_stop = entry * (1 + price_offset_pct) if side_norm == "buy" else entry * (1 - price_offset_pct)
                new_stop = await okx_rest_service.round_price(symbol, new_stop)
                return False, "EMANCIPATE_SLOT", new_stop

            elif roi >= 300.0:
                target_stop_blitz = 270.0
                logger.info(f"[V110.137 BLITZ-UNIT3] {symbol} ROI={roi:.0f}% -> SL +270% (UNIDADE 3 GARANTIDA)")

            elif roi >= 200.0:
                target_stop_blitz = 180.0
                logger.info(f"[V110.137 BLITZ-UNIT2] {symbol} ROI={roi:.0f}% -> SL +180% (UNIDADE 2 GARANTIDA)")

            elif roi >= 150.0:
                # Já emancipada, o stop continua sendo o da escadinha avançada de moonbags/harvester
                target_stop_blitz = 110.0

            elif roi >= 100.0:
                target_stop_blitz = 95.0
                logger.info(f"[V110.137 BLITZ-UNIT1] {symbol} ROI={roi:.0f}% -> SL +95% (UNIDADE 1 GARANTIDA)")

            elif roi >= 70.0:
                target_stop_blitz = 50.0

            elif roi >= breakeven_blitz:
                target_stop_blitz = 5.0  # Break-Even Adaptativo (cobre taxas)

            if target_stop_blitz > 0:
                from services.okx_rest import okx_rest_service
                price_offset_pct = target_stop_blitz / (leverage * 100)
                new_stop = entry * (1 + price_offset_pct) if side_norm == "buy" else entry * (1 - price_offset_pct)
                new_stop = await okx_rest_service.round_price(symbol, new_stop)

                # Paciencia Absoluta: so move SL para direcao favoravel
                if (side_norm == "buy" and new_stop > current_sl) or \
                   (side_norm == "sell" and (current_sl == 0 or new_stop < current_sl)):
                    return False, None, new_stop

            return False, None, None

        # 🌟 V15.0 ESCADINHA DE ELITE: Fôlego Macro com Apenas 2 Degraus
        # [V110.28.2 FIX] SHADOW incluído para garantir emancipação de slots do tipo Shadow
        if slot_type in ["TREND", "SWING", "SNIPER", "SCALP", "SHADOW"]:
            target_stop_roi_trend = 0
            
            # [V111.4] ESCADINHA DE TENDÊNCIA UNIFICADA (Ordem Única até o infinito):
            # 1. 50% ROI  -> Move SL para +25% ROI (Risco Zero / Lucro Inicial)
            # 2. 80% ROI  -> Move SL para +50% ROI (Lucro Garantido)
            # 3. 100% ROI -> Move SL para +75% ROI (Lucro Travado)
            # 4. 130% ROI -> Move SL para +110% ROI (Sucesso Total)
            if roi >= 130.0:
                target_stop_roi_trend = 110.0
            elif roi >= 100.0:
                target_stop_roi_trend = 75.0
            elif roi >= 80.0:
                target_stop_roi_trend = 50.0
            elif roi >= 50.0:
                target_stop_roi_trend = 25.0
                
            if target_stop_roi_trend > 0:
                # [V110.135] Use current trade leverage for correct price offset calculation
                price_offset_pct = target_stop_roi_trend / (leverage * 100)
                new_stop = entry * (1 + price_offset_pct) if side_norm == "buy" else entry * (1 - price_offset_pct)

                # Fallback de segurança se o preço de entrada for corrompido
                if new_stop <= 0 and current_price > 0:
                    new_stop = current_price * (1 + price_offset_pct) if side_norm == "buy" else current_price * (1 - price_offset_pct)

                from services.okx_rest import okx_rest_service
                new_stop = await okx_rest_service.round_price(symbol, new_stop)

                # Atualiza se melhor (Paciência Absoluta: só move o stop para a direção favorável)
                if (side_norm == "buy" and new_stop > current_sl) or (side_norm == "sell" and (current_sl == 0 or new_stop < current_sl)):
                    logger.info(f"🛡️ [ESCADINHA MACRO] {symbol} ROI={roi:.0f}%. Novo SL garantido em +{target_stop_roi_trend}% ROI.")
                    return False, None, new_stop


        # [V110.10 PILOTO AUTOMÁTICO] A antiga 'Estratégia do Almirante' (Saídas Subjetivas por Gás >100% ROI) 
        # foi EXTIRPADA para garantir a Supremacia da Escadinha (Trailing Stop Mecânico).
        # A partir de 100% ROI, a IA não fecha a ordem por "secagem de volume" abrupta.
        if roi >= 100.0 and not is_emancipated:
            return False, None, None

        # [V27.6] EXPANSÃO DE FÔLEGO (Buffer de RSI e Regra SURF)
        # Buscar RSI do cache local via WebSocket (atualiza a cada 60s)
        from services.okx_ws_public import okx_ws_public_service
        try:
            rsi_1m = okx_ws_public_service.rsi_cache.get(symbol, 50.0)
        except Exception:
            rsi_1m = 50.0

        score = slot_data.get("score", 0)

        # [V28.0] Regime-Aware Buffer: Previne buffer se o mercado estiver RANGING
        # Trazendo o regime (pode ser cacheado ou checado rapidamente)
        try:
            from services.signal_generator import signal_generator
            # Calling synchronously since detecting market regime is async but we are in async context? Wait, process_sniper_logic is async.
            regime_data = await signal_generator.detect_market_regime(symbol)
            market_regime = regime_data.get('regime', 'TRANSITION')
        except Exception:
            market_regime = 'TRANSITION'

        # Buffer: Adiciona -20% de ROI (0.4% de preço ao SL) se o RSI estiver a nosso favor E o mercado NÃO for RANGING
        buffer_roi = 0.0
        if market_regime != 'RANGING':
            if (side_norm == "buy" and rsi_1m > 60) or (side_norm == "sell" and rsi_1m < 40):
                buffer_roi = 20.0  # -20% de ROI de buffer na linha do SL
                logger.debug(f"🌤️ [V27.6/V28.0 BUFFER] RSI favorável ({rsi_1m:.1f}) & Regime={market_regime}. Adicionando {buffer_roi}% de respiro no SL de {symbol}.")
        else:
             logger.debug(f"🛑 [V28.0 RESTRICTION] RANGING Market detectado para {symbol}. Buffer elástico de SL NEGADO. Stop fixado rígido.")


        # 🔴 PHASE_SAFE: SL inicial — sem ação necessária, SL definido na abertura

        # [V41.3] TARGET EXPANSION CHECK: Se abriu RANGING e agora é TRENDING, sinaliza expansão
        is_market_ranging = slot_data.get("is_market_ranging", False)
        if is_market_ranging and market_regime != 'RANGING' and market_regime != 'TRANSITION':
            # Se já subiu um pouco (ex: ROI > 10%), sinaliza que pode expandir o TP
            if roi >= 10.0:
                 logger.info(f"🚀 [V41.3 EXPAND] {symbol} detectou mudança para {market_regime}! Sugerindo expansão de alvo.")
                 return False, "EXPAND_TARGET", None

        return False, None, None
    
    def get_sl_phase(self, roi: float, scale: float = 1.0, slot_data: Dict[str, Any] = None) -> str:
        """
        V110.65: Retorna a fase atual do Smart SL baseado no ROI e no Stop Loss travado.
        """
        scale_trigger = max(1.0, scale)
        current_phase = "SAFE"

        # 1. Fase baseada no ROI atual (Trending/Decor Shadow)
        if roi >= 130.0 * scale_trigger:
            current_phase = "MEGA_PULSE"
        elif roi >= 100.0 * scale_trigger:
            current_phase = "PROFIT_LOCK"
        elif roi >= 80.0 * scale_trigger:
            current_phase = "LUCRO_80"
        elif roi >= 50.0 * scale_trigger:
            current_phase = "RISK_ZERO"

        # 2. Persistência baseada no SL (Caso o mercado recue mas o SL continue travado)
        if slot_data:
            entry = float(slot_data.get("entry_price", 0))
            current_sl = float(slot_data.get("current_stop", 0))
            side = slot_data.get("side", "Buy")
            
            if entry > 0 and current_sl > 0:
                # Se o SL já está no entry ou lucro, não volta para "SAFE" no dashboard
                is_buy = side == "Buy"
                if (is_buy and current_sl >= entry) or (not is_buy and current_sl <= entry):
                    # Se o ROI baixou do gatilho mas o SL tá no entry, garante o ícone de BREAKEVEN
                    if current_phase == "SAFE":
                        current_phase = "BREAKEVEN"
        
        return current_phase
    
    def get_sl_phase_info(self, roi: float, scale: float = 1.0, slot_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        V11.0: Retorna informações completas da fase atual para o frontend.
        """
        phase = self.get_sl_phase(roi, scale=scale, slot_data=slot_data)
        phase_key = f"PHASE_{phase}"
        info = SMART_SL_PHASES.get(phase_key, SMART_SL_PHASES["PHASE_SAFE"])
        return {
            "phase": phase,
            "label": phase,
            "icon": info.get("icon", "🔴"),
            "color": info.get("color", "red"),
            "stop_roi": info.get("stop_roi", -50.0)
        }

    async def process_surf_logic(self, slot_data: Dict[str, Any], current_price: float, roi: float) -> Tuple[bool, Optional[str], Optional[float]]:
        """
        [V15.3.1] SURF LOGIC STUB: Previne erro no CaptainAgent.
        Modo SURF segue lógica adaptativa de tendência (em desenvolvimento).
        """
        return await self.process_sniper_logic(slot_data, current_price, roi)
    
    async def _check_gas_favorable(self, symbol: str, side: str) -> bool:
        """
        [V46.0] Refined Gas Check (CVD 5m + ADX Momentum).
        Verifica se o fluxo monetário (CVD) ainda sustenta a impulsão.
        """
        try:
            from services.okx_ws_public import okx_ws_public_service
            from services.signal_generator import signal_generator
            
            # 1. CVD de curto prazo (5m)
            cvd_5m = okx_ws_public_service.get_cvd_score_time(symbol, window_seconds=300)
            side_norm = side.lower()
            
            # 2. ADX Slope (Aceleração da Tendência)
            regime_data = signal_generator.market_regime_cache.get(symbol, {})
            adx_val = regime_data.get('adx', 20)
            adx_prev = regime_data.get('adx_prev', adx_val)
            adx_slope = adx_val - adx_prev
            
            # Threshold adaptativo baseado no turnover
            turnover = okx_ws_public_service.turnover_24h_cache.get(symbol, 50_000_000)
            threshold = max(5000, turnover * 0.00005)
            
            # Condição de Gás: CVD a favor + (ADX não está morrendo ou CVD é muito forte)
            if side_norm == "buy":
                # Para Long: CVD positivo e (ADX subindo ou CVD explosivo)
                favorable = cvd_5m > threshold and (adx_slope > -0.1 or cvd_5m > threshold * 3)
            else:
                # Para Short: CVD negativo e (ADX subindo ou CVD explosivo)
                favorable = cvd_5m < -threshold and (adx_slope > -0.1 or cvd_5m < -threshold * 3)
            
            logger.info(f"⛽ [GAS-AUDIT V46.0] {symbol} | ROI 100% | CVD 5m={cvd_5m:.0f} | ADX={adx_val:.1f}({adx_slope:+.2f}) | Fav={favorable}")
            return favorable
        except Exception as e:
            logger.warning(f"Gas check failed: {e}")
            return False  # Conservador: realiza lucro

    async def _get_candle_anatomy(self, symbol: str, side: str) -> str:
        """
        [V6.2] Analisa a vela de 1m atual para detectar Rejeição (Pavio) ou Força (Corpo).
        Retorna: 'WICK_REJECTION', 'SOLID_EXPANSION' ou 'NEUTRAL'
        """
        try:
            from services.okx_rest import okx_rest_service
            klines = await okx_rest_service.get_klines(symbol=symbol, interval="1", limit=2)
            if not klines or len(klines) < 1:
                return "NEUTRAL"
            
            # Vela atual (mais recente)
            c = klines[0]
            open_p = float(c[1])
            high_p = float(c[2])
            low_p = float(c[3])
            close_p = float(c[4])
            
            candle_range = high_p - low_p
            if candle_range <= 0:
                return "NEUTRAL"
            
            side_norm = side.lower()
            if side_norm == "buy":
                # Para LONG: Pavio superior grande = Rejeição
                upper_wick = high_p - max(open_p, close_p)
                wick_pct = upper_wick / candle_range
                
                # Corpo fechando perto da máxima = Expansão
                body_close_gap = (high_p - close_p) / candle_range
                
                if wick_pct > 0.30: # Pavio > 30% da vela
                    return "WICK_REJECTION"
                if body_close_gap < 0.10 and close_p > open_p: # Fecha a 10% do topo e é verde
                    return "SOLID_EXPANSION"
            else:
                # Para SHORT: Pavio inferior grande = Rejeição
                lower_wick = min(open_p, close_p) - low_p
                wick_pct = lower_wick / candle_range
                
                # Corpo fechando perto da mínima = Expansão
                body_close_gap = (close_p - low_p) / candle_range
                
                if wick_pct > 0.30: # Pavio > 30% da vela
                    return "WICK_REJECTION"
                if body_close_gap < 0.10 and close_p < open_p: # Fecha a 10% do fundo e é vermelha
                    return "SOLID_EXPANSION"
                    
            return "NEUTRAL"
        except Exception as e:
            logger.error(f"Error analyzing candle anatomy for {symbol}: {e}")
            return "NEUTRAL"

    async def check_shadow_sentinel_retest(self, slot_data: Dict[str, Any], current_price: float) -> bool:
        """
        V15.1: Shadow Sentinel Hybrid - Macro Retest Validation (Pair + BTC).
        Decides if a trade should survive a touch of the Break-Even SL.
        
        Logic:
        - Verifica estrutura do Par (SMA20 + Pivôs em 2H).
        - Verifica saúde do BTC (2H Trend). Se BTC estiver contra a posição, proteção desabilitada.
        """
        try:
            symbol = slot_data.get("symbol")
            side = slot_data.get("side", "Buy").lower()
            
            # 1. Recover Indicators from Signal Generator Cache
            from services.signal_generator import signal_generator
            macro = await signal_generator.get_2h_macro_analysis(symbol)
            sma20_2h = macro.get("sma20", 0)
            pivot_2h = macro.get("pivot_low" if side == "buy" else "pivot_high", 0)
            
            # [V15.1] BTC Hybrid Check: Se o BTC quebrar a tendência macro, desativa proteção SENTINEL
            btc_macro = await signal_generator.get_2h_macro_analysis("BTCUSDT")
            btc_trend = btc_macro.get("trend", "sideways")
            
            if side == "buy" and btc_trend == "bearish":
                logger.warning(f"\U0001f6e1\ufe0f [SENTINEL] Protection ABORTED for {symbol}: BTC Macro is BEARISH.")
                return False
            if side == "sell" and btc_trend == "bullish":
                logger.warning(f"\U0001f6e1\ufe0f [SENTINEL] Protection ABORTED for {symbol}: BTC Macro is BULLISH.")
                return False

            # CVD Momentum check (Session CVD)
            from services.redis_service import redis_service
            cvd_session = await redis_service.get_cvd(symbol)
            
            # [V15.5] DECORRELATION ANALYSIS (Shadow Sentinel 2.0)
            # Se a moeda está mostrando força independente do BTC (Decorrelação), permitimos o reteste.
            from services.signal_generator import signal_generator
            decor = await signal_generator.get_decorrelation_state(symbol)
            is_decorrelated = decor.get("is_decorrelated", False)
            pearson = decor.get("pearson", 1.0)
            
            if side == "buy":
                # Estrutura de Alta: Preço acima das médias/pivôs e sem exaustão de venda (<-25k)
                # OU se estiver decorrelacionada (Pearson < 0.4) com tendência oposta ao dump do BTC
                if current_price >= sma20_2h or current_price >= pivot_2h or (is_decorrelated and pearson < 0.4):
                    if cvd_session > -25000:
                        if is_decorrelated:
                             logger.info(f"🛡️ [V15.5 DECOR] {symbol} decorrelated from BTC (Pearson={pearson:.2f}). Sentinel Protection ACTIVE.")
                        return True
            else: # sell
                # Estrutura de Baixa: Preço abaixo das médias/pivôs e sem exaustão de compra (>25k)
                if current_price <= sma20_2h or current_price <= pivot_2h or (is_decorrelated and pearson < 0.4):
                    if cvd_session < 25000:
                        if is_decorrelated:
                             logger.info(f"🛡️ [V15.5 DECOR] {symbol} decorrelated from BTC (Pearson={pearson:.2f}). Sentinel Protection ACTIVE.")
                        return True
                        
            return False
        except Exception as e:
            logger.error(f"Sentinel retest check failed: {e}")
            return False
    
    async def process_order_logic(self, slot_data: Dict[str, Any], current_price: float) -> Tuple[bool, Optional[str], Optional[float]]:
        """
        Executa a lógica exclusiva por tipo de ordem.
        
        Args:
            slot_data: Dados do slot (symbol, side, entry_price, slot_type, current_stop, etc.)
            current_price: Preço atual do mercado
            
        Returns:
            (should_close, reason, new_stop_price)
            - should_close: True se a ordem deve ser encerrada
            - reason: Motivo do encerramento
            - new_stop_price: Novo SL para atualizar (apenas SURF)
        """
        entry = slot_data.get("entry_price", 0)
        side = slot_data.get("side", "Buy")
        slot_type = slot_data.get("slot_type", "SNIPER")
        symbol = slot_data.get("symbol", "UNKNOWN")
        
        if entry <= 0 or current_price <= 0:
            return False, None, None
        
        # 1. Calcular ROI Real (Adaptive Leverage V110.135)
        leverage = float(slot_data.get("leverage", 50.0))
        roi = self.calculate_roi(entry, current_price, side, leverage=leverage)
        
        # 2. Get ATR for volatility-based decisions
        from services.okx_ws_public import okx_ws_public_service
        atr = okx_ws_public_service.atr_cache.get(symbol)

        # 3. Executar lógica Sniper
        return await self.process_sniper_logic(slot_data, current_price, roi, atr=atr)

    def calculate_pnl(self, entry_price: float, exit_price: float, qty: float, side: str, ct_val: float = 1.0) -> float:
        """
        Calcula o PnL realizado em USD considerando taxas de corretagem (taker) e ctVal do contrato.
        
        Args:
            entry_price: Preço de entrada
            exit_price: Preço de saída  
            qty: Quantidade de contratos
            side: 'buy' ou 'sell'
            ct_val: Valor do contrato (ex: 0.01 para BTC, 1000 para DOGE)
        """
        if entry_price <= 0 or qty <= 0 or ct_val <= 0:
            return 0.0
            
        side_norm = (side or "").lower()
        if side_norm == "buy":
            raw_pnl = qty * (exit_price - entry_price) * ct_val
        else: # Sell/Short
            raw_pnl = qty * (entry_price - exit_price) * ct_val
            
        # [V20.4 FIX] Correct round-trip fee: OKX taker = 0.055% per side
        # Entry fee on entry notional + Exit fee on exit notional, multiplicados por ct_val
        entry_fee = (qty * entry_price * ct_val) * 0.00055
        exit_fee = (qty * exit_price * ct_val) * 0.00055
        total_fee = entry_fee + exit_fee
        final_pnl = raw_pnl - total_fee
        
        # [V110.12.9.1] ATOMIC PNL CAP: No modo simulado (PAPER), limitamos a perda do saldo real de banca
        # para refletir rigorosamente o limite atômico de -50% da margem real colocada na ordem.
        from config import settings
        if getattr(settings, "EXECUTION_MODE", "PAPER") == "PAPER":
            # Posição aproximada da margem: notional / leverage = (qty * entry_price * ct_val) / 50.0
            approx_margin = (qty * entry_price * ct_val) / 50.0
            max_pnl_loss = -0.50 * approx_margin
            if final_pnl < max_pnl_loss:
                final_pnl = max_pnl_loss
                logger.info(f"🛡️ [ATOMIC PNL CAP] PnL ajustado para o limite do stop de -50% da margem: ${final_pnl:.2f}")
                
        return final_pnl


# Instância global
execution_protocol = ExecutionProtocol()
