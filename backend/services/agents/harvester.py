import logging
import time
import asyncio
from typing import Dict, Any, Optional
from services.okx_ws_public import okx_ws_public_service
from config import settings

logger = logging.getLogger("HarvesterAgent")

# [V110.125] MOONBAG TRAILING STOP LEVELS
# Após emancipação, o SL sobe progressivamente conforme ROI aumenta
MOONBAG_TRAILING_LEVELS = [
    {"roi_threshold": 1200, "sl_roi": 1000, "icon": "APX", "label": "APEX"},
    {"roi_threshold": 1000, "sl_roi": 800, "icon": "HYP", "label": "HYPER"},
    {"roi_threshold": 800, "sl_roi": 650, "icon": "CHK", "label": "CHOKE"},
    {"roi_threshold": 750, "sl_roi": 600, "icon": "CP", "label": "CHOKE_PREP"},
    {"roi_threshold": 700, "sl_roi": 500, "icon": "🔱", "label": "GOD_MODE"},
    {"roi_threshold": 600, "sl_roi": 420, "icon": "💫", "label": "SUPERNOVA"},
    {"roi_threshold": 500, "sl_roi": 350, "icon": "👑", "label": "CROWN"},
    {"roi_threshold": 400, "sl_roi": 280, "icon": "⭐", "label": "STAR"},
    {"roi_threshold": 300, "sl_roi": 220, "icon": "🚀", "label": "ROCKET"}, # Subiu de 200 para 220
    {"roi_threshold": 200, "sl_roi": 150, "icon": "🌊", "label": "WAVE"},   # Subiu de 130 para 150 (Almirante Request)
]

# [V110.118] HARVEST EXTENSION PHASES — baseado em níveis Fibo de EXTENSÃO
# Cada nível representa onde a pernada TIPICAMENTE termina (resistência, não retração)
# Proxy de ROI calculado para uma pernada típica de 5% (250% ROI):
HARVEST_EXTENSION_PHASES = [
    {
        "ext_label":   "1.0_ext",       # Measured Move: 100% da pernada anterior
        "proportion":  0.65,            # Fechar 65%, manter 35% surfando
        "label":       "PRIMEIRA_COLHEITA",
        "description": "Pernada típica 5-6% (Measured Move)",
        "roi_proxy":   250,             # ROI esperado para uma pernada de 5%
    },
    {
        "ext_label":   "1.272_ext",     # Extensão forte: 127.2%
        "proportion":  0.72,            # Fechar 72%, manter 28%
        "label":       "SEGUNDA_COLHEITA",
        "description": "Pernada forte 7-8%",
        "roi_proxy":   350,
    },
    {
        "ext_label":   "1.414_ext",     # Extensão semi-dourada
        "proportion":  0.78,            # Fechar 78%, manter 22%
        "label":       "TERCEIRA_COLHEITA",
        "description": "Pernada forte 8-9%",
        "roi_proxy":   450,
    },
    {
        "ext_label":   "1.618_ext",     # Golden Extension: onde moves extremos terminam
        "proportion":  0.85,            # Fechar 85%, manter 15% (residual livre)
        "label":       "GOLDEN_COLHEITA",
        "description": "Golden Extension 10%+ - correção quase certa",
        "roi_proxy":   600,
    },
]

class HarvesterAgent:
    """
    [V110.113] HARVESTER AGENT ("CEIFEIRO") - UPGRADED
    Especialista em colheita de lucros em Moonbags (posições emancipadas).
    
    RESPONSABILIDADES DUPLAS:
    1. Colheita parcial em resistências Fibonacci H4 com exaustão CVD
    2. Trailing Stop progressivo para proteger lucros de Moonbags
    
    ESTRATÉGIA DE COLHEITA EM FASES:
    - 1ª Colheita (250%+): Colhe 40%, deixa 60% surfando
    - 2ª Colheita (500%+): Colhe 30%, deixa 30% surfando  
    - 3ª Colheita (700%+): Colhe 25%, deixa 5-10% surfando
    """
    def __init__(self):
        self.leverage = 50.0
        self.fibo_threshold = 0.005  # [V110.118] Proximidade de 0.5% do alvo (era 0.3%)
        self.min_roi_for_harvest = 100.0  # Guard mínimo: 2% de move (100% ROI) antes de verificar
        self.harvest_cooldown = 1800  # 30 minutos entre colheitas do mesmo ativo
        self._harvest_history = {}  # {symbol: last_harvest_timestamp}
        # [V110.118] Cache de Extensão Fibonacci H4 (TTL 30 min)
        # Chave: f"{symbol}_{entry_price:.4f}" para suportar entradas diferentes
        self._ext_cache: dict = {}  # {cache_key: {ext_data, "updated_at": float}}
        # Cache legado (retração) — mantido para compatibilidade
        self._fib_cache: dict = {}
        self._fib_cache_ttl = 1800  # 30 minutos

    async def start(self):
        """Inicializa o agente (Stub method for startup resilience)."""
        logger.info("🌾 Ceifeiro pronto.")

    async def check_harvest_opportunity(self, symbol: str, side: str, entry_price: float, current_price: float) -> Dict[str, Any]:
        """
        [V110.118] CEIFEIRO - Identifica Resistências de Extensão Fibo H4 para Colheitar

        ESTRATÉGIA:
        O Ceifeiro observa ONDE a pernada atual tende a TERMINAR usando
        Fibonacci de Extensão (ao contrário da retração que é suporte de dip).

        Fluxo de decisão:
        1. ROI mínimo de 2% (100%) para começar a monitorar
        2. Calcula extensões H4 a partir do entry_price (Measured Move)
        3. Quando preço chega perto de um nível de extensão:
            a. Verifica MOMENTUM: CVD forte → aguarda próximo nível
            b. Verifica EXAUSTÃO: CVD negativo ou RSI overbought → COLHE
        4. Proporção dinâmica por nível:
            - 1.0x ext  (pernada típica 5-6%)  → fechar 65%, manter 35%
            - 1.272x ext (forte 7-8%)           → fechar 72%, manter 28%
            - 1.414x ext (semi-dourado 8-9%)    → fechar 78%, manter 22%
            - 1.618x ext (golden 10%+)          → fechar 85%, manter 15%
        5. Safety net: ROI > 700% colhe 80% incondicionalmente
        """
        try:
            from services.signal_generator import signal_generator

            # === 1. Calcular ROI Atual ===
            price_diff_pct = (current_price - entry_price) / entry_price
            if side.upper() == "SELL":
                price_diff_pct = -price_diff_pct
            current_roi = price_diff_pct * self.leverage * 100

            if current_roi < self.min_roi_for_harvest:
                return {"action": "HOLD", "reason": f"ROI {current_roi:.1f}% abaixo do guard mínimo (100%)"}

            # === 2. Verificar Cooldown ===
            now = time.time()
            last_harvest = self._harvest_history.get(symbol, 0)
            if now - last_harvest < self.harvest_cooldown:
                remaining_min = int((self.harvest_cooldown - (now - last_harvest)) / 60)
                return {"action": "HOLD", "reason": f"Harvest cooldown ({remaining_min}min restantes)"}

            # === 3. God-Candle Climax (Parabolic Hunter V110.138) ===
            # Substitui a velha "Safety Net" engessada de 700% que limitava grandes pernadas.
            if current_roi >= 1000.0:
                rsi_1m = getattr(okx_ws_public_service, "rsi_cache", {}).get(symbol, 50)
                # Verifica exaustão: RSI bombando comprando o topo (Long) ou derretendo (Short)
                if (side.upper() == "BUY" and rsi_1m >= 85) or (side.upper() == "SELL" and rsi_1m <= 15):
                    proportion = 0.90
                    self._harvest_history[symbol] = now
                    logger.warning(
                        f"🌋 [CEIFEIRO-HYPER] {symbol} ROI={current_roi:.1f}% CLIMAX EXTREMO! "
                        f"RSI={rsi_1m:.0f} engatilhou desmonte parabólico. Colhendo {proportion*100:.0f}% a mercado!"
                    )
                    return {
                        "action": "PARTIAL_HARVEST",
                        "proportion": proportion,
                        "target_level": "PARABOLIC_CLIMAX",
                        "current_roi": current_roi,
                        "phase": "GOD_CANDLE_HARVEST",
                        "reason": f"Explosão Parabólica c/ Exaustão (RSI {rsi_1m:.0f})"
                    }
                    
            # Preserva Safety Net secundário caso atinja 700% mas falte Momentum exausto
            elif current_roi >= 700.0:
                proportion = 0.80
                self._harvest_history[symbol] = now
                logger.warning(
                    f"⚡ [CEIFEIRO-SAFETY] {symbol} ROI={current_roi:.1f}% EXTREMO! "
                    f"Colhendo {proportion*100:.0f}% por segurança secundária."
                )
                return {
                    "action": "PARTIAL_HARVEST",
                    "proportion": proportion,
                    "target_level": "EXTREME_ROI",
                    "current_roi": current_roi,
                    "phase": "GOLDEN_COLHEITA",
                    "reason": f"Safety net intermediário: ROI {current_roi:.1f}%"
                }

            # === 4. Buscar Extensões Fibonacci H4 e H1 com cache ===
            cache_key_h4 = f"{symbol}_{entry_price:.6f}_H4"
            cache_key_h1 = f"{symbol}_{entry_price:.6f}_H1"
            
            ext_data_h4 = self._ext_cache.get(cache_key_h4)
            ext_data_h1 = self._ext_cache.get(cache_key_h1)
            
            # Atualizar H4 se necessário
            if not ext_data_h4 or (now - ext_data_h4.get("updated_at", 0)) > self._fib_cache_ttl:
                ext_data_h4 = await signal_generator.get_fib_extension_levels(
                    symbol=symbol, entry_price=entry_price, side=side, interval="240", limit=60
                )
                if ext_data_h4:
                    self._ext_cache[cache_key_h4] = {**ext_data_h4, "updated_at": now}
            
            # Atualizar H1 se necessário (Nova Confirmação V110.125)
            if not ext_data_h1 or (now - ext_data_h1.get("updated_at", 0)) > self._fib_cache_ttl:
                ext_data_h1 = await signal_generator.get_fib_extension_levels(
                    symbol=symbol, entry_price=entry_price, side=side, interval="60", limit=60
                )
                if ext_data_h1:
                    self._ext_cache[cache_key_h1] = {**ext_data_h1, "updated_at": now}

            # Prioriza H4, mas usa H1 como confirmação de exaustão local
            ext_data = ext_data_h4 or ext_data_h1
            
            if not ext_data or not ext_data.get("extensions"):
                # Sem dados de Fibo, usar segurança por ROI bruto
                if current_roi >= 400.0:
                    proportion = 0.65
                    self._harvest_history[symbol] = now
                    return {
                        "action": "PARTIAL_HARVEST",
                        "proportion": proportion,
                        "target_level": "ROI_FALLBACK",
                        "current_roi": current_roi,
                        "phase": "PRIMEIRA_COLHEITA",
                        "reason": f"Sem dados Fibo, ROI={current_roi:.1f}% acima de 400%"
                    }
                return {"action": "HOLD", "reason": "Aguardando dados Fibo H4"}

            # === 5. Verificar proximidade com níveis de extensão ===
            extensions = ext_data["extensions"]
            hit_phase = None
            hit_price = None

            # Varremos do nível MAIS ALTO para o mais baixo (prioriza Golden)
            for phase in reversed(HARVEST_EXTENSION_PHASES):
                ext_price = extensions.get(phase["ext_label"])
                if not ext_price or ext_price <= 0:
                    continue
                # Checar se o preço atual está dentro do threshold do nível
                dist = abs(current_price - ext_price) / ext_price
                if dist < self.fibo_threshold:  # Dentro de 0.5%
                    hit_phase = phase
                    hit_price = ext_price
                    logger.info(
                        f"🎯 [CEIFEIRO] {symbol} PRÓXIMO de extensão {phase['ext_label']} "
                        f"(${ext_price:.6f}) | Distância: {dist*100:.2f}% | "
                        f"ROI esperado: {ext_data.get('extensions_roi', {}).get(phase['ext_label'], '?')}%"
                    )
                    break  # Primeiro match (mais alto) vence

            if not hit_phase:
                return {
                    "action": "HOLD",
                    "reason": f"ROI {current_roi:.1f}% | Próximo alvo: {self._next_target_info(extensions, current_price, side)}"
                }

            # === 6. Análise de Momentum (CVD + RSI) ===
            cvd_5m = okx_ws_public_service.get_cvd_score_time(symbol, 300)
            rsi_1m = getattr(okx_ws_public_service, "rsi_cache", {}).get(symbol, 50)

            side_upper = side.upper()
            is_exhausted = False    # Sinal de topo: hora de colher
            strong_momentum = False # Sinal de continuação: aguardar próximo nível

            if side_upper == "BUY":
                # LONG: exaustão = dinheiro saindo no topo (CVD negativo, RSI overbought)
                is_exhausted    = (cvd_5m < -15000) or (rsi_1m > 75)
                strong_momentum = (cvd_5m > 30000)  and (rsi_1m < 78)
            else:
                # SHORT: exaustão = pressão compradora no fundo (CVD positivo, RSI oversold)
                is_exhausted    = (cvd_5m > 15000) or (rsi_1m < 25)
                strong_momentum = (cvd_5m < -30000) and (rsi_1m > 22)

            # === 7. Decisão Final ===

            # CASO A: Momentum ainda forte → adiar colheita para próximo nível
            if strong_momentum and hit_phase["ext_label"] in ["1.0_ext", "1.272_ext"]:
                return {
                    "action": "HOLD",
                    "reason": (
                        f"Momentum FORTE em {hit_phase['ext_label']} (CVD={cvd_5m:.0f}, RSI={rsi_1m:.0f}). "
                        f"Aguardando {hit_phase['ext_label'].replace('_ext', '.272_ext') if '1.0' in hit_phase['ext_label'] else '1.272_ext'}."
                    )
                }

            # CASO B: Exaustão ou overshot (preço ultrapassou o nível >2%) → COLHER
            overshot = (abs(current_price - hit_price) / hit_price) > 0.02  # 2% acima do nível
            should_harvest = is_exhausted or overshot

            # CASO C: Preço na Golden Extension → sempre colhe (move extremo)
            if hit_phase["ext_label"] == "1.618_ext":
                should_harvest = True

            if not should_harvest:
                return {
                    "action": "HOLD",
                    "reason": (
                        f"Próximo de {hit_phase['ext_label']} mas sem exaustão confirmada. "
                        f"CVD={cvd_5m:.0f} | RSI={rsi_1m:.0f}. Aguardando confirmação."
                    )
                }

            # === 8. Calcular Proporção Final ===
            proportion = hit_phase["proportion"]
            
            # Boost de proporção se RSI extremamente overbought (>80) → mais agressivo
            if side_upper == "BUY" and rsi_1m > 80:
                proportion = min(proportion + 0.08, 0.90)
                logger.info(f"🔥 [CEIFEIRO] RSI={rsi_1m:.0f} extremo — proporção ajustada para {proportion*100:.0f}%")

            self._harvest_history[symbol] = now

            logger.warning(
                f"🌾 [CEIFEIRO] ⚔️ {hit_phase['label']} em {symbol}! "
                f"Colhendo {proportion*100:.0f}%, mantendo {(1-proportion)*100:.0f}% surfando. "
                f"Nível: {hit_phase['ext_label']} (${hit_price:.6f}) | ROI: {current_roi:.1f}% | "
                f"CVD: {cvd_5m:.0f} | RSI: {rsi_1m:.0f}"
            )

            return {
                "action": "PARTIAL_HARVEST",
                "proportion": proportion,
                "target_level": hit_phase["ext_label"],
                "current_roi": current_roi,
                "phase": hit_phase["label"],
                "description": hit_phase["description"],
                "ext_price": hit_price,
                "cvd_5m": cvd_5m,
                "rsi_1m": rsi_1m,
                "reason": f"Extensão Fibo {hit_phase['ext_label']} + {'exaustão CVD/RSI' if is_exhausted else 'overshot'}"
            }

        except Exception as e:
            logger.error(f"Error in HarvesterAgent.check_harvest_opportunity: {e}")
            return {"action": "HOLD", "reason": f"Error: {e}"}

    def _next_target_info(self, extensions: dict, current_price: float, side: str) -> str:
        """Retorna info sobre o próximo nível de extensão ainda não atingido."""
        try:
            side_upper = side.upper()
            candidates = []
            for phase in HARVEST_EXTENSION_PHASES:
                price = extensions.get(phase["ext_label"])
                if not price:
                    continue
                if side_upper == "BUY" and price > current_price:
                    candidates.append((price, phase["ext_label"]))
                elif side_upper == "SELL" and price < current_price:
                    candidates.append((price, phase["ext_label"]))
            if candidates:
                nearest = min(candidates, key=lambda x: abs(x[0] - current_price))
                dist_pct = abs(nearest[0] - current_price) / current_price * 100
                return f"{nearest[1]} em ${nearest[0]:.6f} ({dist_pct:.1f}% de distância)"
        except Exception:
            pass
        return "Calculando..."

    def calculate_trailing_stop(self, symbol: str, side: str, entry_price: float, current_price: float, current_sl: float) -> Dict[str, Any]:
        """
        [V110.113] Calcula o Trailing Stop para Moonbags.
        
        Após emancipação (150% ROI), o SL sobe progressivamente:
        - 200% ROI → SL em +130%
        - 300% ROI → SL em +200%
        - 400% ROI → SL em +280%
        - 500% ROI → SL em +350%
        - 600% ROI → SL em +420%
        - 700%+ ROI → SL em +500%
        
        Returns:
            Dict com novo SL se houver melhoria, senão mantém atual
        """
        try:
            # Calcular ROI atual
            price_diff_pct = (current_price - entry_price) / entry_price
            if side.upper() == "SELL":
                price_diff_pct = -price_diff_pct
            current_roi = price_diff_pct * self.leverage * 100

            # [V110.136.2 F4] Trailing start reduzido 200% -> 160%
            # Fecha o gap de 50% ROI sem protecao progressiva entre emancipacao (150%) e trailing (antes 200%).
            if current_roi < 160:
                return {"action": "HOLD", "reason": f"ROI {current_roi:.1f}% abaixo do trailing start (160%)"}

            # [V110.138] PARABOLIC HUNTER: Dynamic Choke-Hold pós-800% ROI
            if current_roi >= 800.0:
                sl_roi = current_roi - 150.0  # SL corre exatos 150% de distância do topo atual
                active_level = {"icon": "🔥", "label": "CHOKE_HOLD"}
            else:
                # Encontrar nível de trailing ativo normal
                active_level = None
                for level in MOONBAG_TRAILING_LEVELS:
                    if current_roi >= level["roi_threshold"]:
                        active_level = level
                        break

                if not active_level:
                    # Fallback: usa o nível mais baixo
                    active_level = MOONBAG_TRAILING_LEVELS[-1]

                # Calcular novo SL baseado no ROI do nível fixo
                sl_roi = active_level["sl_roi"]
            price_offset_pct = sl_roi / (self.leverage * 100)
            
            if side.upper() == "BUY":
                new_sl = entry_price * (1 + price_offset_pct)
            else:
                new_sl = entry_price * (1 - price_offset_pct)

            # Só atualiza se for MELHORIA (SL mais favorável)
            should_update = False
            if current_sl <= 0:
                should_update = True
            elif side.upper() == "BUY" and new_sl > current_sl:
                should_update = True
            elif side.upper() == "SELL" and new_sl < current_sl:
                should_update = True

            if should_update:
                logger.info(
                    f"🛡️ [MOONBAG-TRAIL] {symbol} ROI={current_roi:.1f}% | "
                    f"SL subindo para +{sl_roi}% ROI (${new_sl:.4f}) [{active_level['icon']} {active_level['label']}]"
                )
                return {
                    "action": "UPDATE_SL",
                    "new_stop": new_sl,
                    "sl_roi": sl_roi,
                    "icon": active_level["icon"],
                    "label": active_level["label"],
                    "current_roi": current_roi
                }
            else:
                return {
                    "action": "HOLD",
                    "reason": f"SL atual melhor ou igual ({current_sl:.4f} vs {new_sl:.4f})"
                }

        except Exception as e:
            logger.error(f"Error in trailing stop calculation: {e}")
            return {"action": "HOLD", "reason": f"Error: {e}"}

harvester_agent = HarvesterAgent()
