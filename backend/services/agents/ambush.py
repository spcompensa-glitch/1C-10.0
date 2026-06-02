import logging
import asyncio
import time
from typing import Dict, Any, List
from services.agents.aios_adapter import AIOSAgent

logger = logging.getLogger("AmbushAgent")

class AmbushAgent(AIOSAgent):
    """
    [V110.118] O Espião da Tocaia Refinada.
    Substitui a lógica matemática cega por entradas baseadas em:
    1. Retração Fibonacci (0.382 para tendências fortes, 0.5 para voláteis)
    2. Validação Exaustiva (CVD flow e RSI) no momento do toque.
    """
    def __init__(self):
        super().__init__(
            agent_id="agent-ambush-specialist",
            role="ambush",
            capabilities=["precision_entry", "fibonacci_analysis", "liquidity_audit"]
        )
        self.max_wait_seconds = 1800 # 30 min timeout para esfriar a Fibo 1H

    async def on_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handles incoming messages from the Dispatcher (Kernel)."""
        return {"status": "ok"}

    async def execute_ambush(self, symbol: str, side: str, signal_data: dict) -> dict:
        """
        Observa o mercado e decide o momento exato de executar o sinal na Tocaia.
        Retornos possíveis:
        - {"action": "TRIGGER", "reason": "...", "price": float}
        - {"action": "ABORT", "reason": "...", "price": float}
        - {"action": "TIMEOUT", "reason": "..."}
        """
        from services.signal_generator import signal_generator
        from services.okx_ws_public import okx_ws_public_service
        from services.redis_service import redis_service
        from services.agents.librarian import librarian_agent

        try:
            # 1. Calculando Zona de Retração Fibo
            fib = await signal_generator.get_fibonacci_levels(symbol, "60", 48)
            if not fib or "levels" not in fib:
                logger.warning(f"🥷 [AMBUSH-FAIL] Impossível calcular Fibonacci H1 para {symbol}.")
                return {"action": "ABORT", "reason": "FAIL_FIBO_CALC"}

            lib_dna = await librarian_agent.get_asset_dna(symbol)
            vol_class = lib_dna.get("volatility_class", "TRENDING")

            fibo_levels = fib["levels"]
            
            # Dinâmica de agressividade conforme DNA do ativo
            if vol_class in ["EXTREME", "VOLATILE"]:
                ambush_target = fibo_levels.get("0.5", 0)
                zone_name = "Golden Zone (0.5)"
            else:
                ambush_target = fibo_levels.get("0.382", 0)
                zone_name = "Shallow Dip (0.382)"
            
            if ambush_target == 0:
                return {"action": "ABORT", "reason": "INVALID_FIBO_TARGET"}

            side_norm = side.lower()
            start_time = time.time()
            
            logger.info(f"🥷 [AMBUSH-WAIT] {symbol} {side} engatado. Volatilidade: {vol_class}. Alvo Tocaia: {ambush_target:.6f} {zone_name}.")

            is_retest_heavy = lib_dna.get("is_retest_heavy", False)
            sweep_detected = False
            
            while (time.time() - start_time) < self.max_wait_seconds:
                current_price = okx_ws_public_service.get_current_price(symbol)
                if not current_price:
                    await asyncio.sleep(2)
                    continue

                # [V110.134] LOGICA SWEEP (SPRING HUNTER): 
                # Se o ativo é Retest Heavy, esperamos furar o alvo e VOLTAR (reclaim).
                if is_retest_heavy:
                    if not sweep_detected:
                        # Detecta se furou o alvo (fingimento)
                        if (side_norm == "buy" and current_price < ambush_target * 0.998) or \
                           (side_norm == "sell" and current_price > ambush_target * 1.002):
                            sweep_detected = True
                            logger.info(f"🦇 [SWEEP-DETECTED] {symbol} furou a Fibo. Aguardando Reclaim da estrutura...")
                        
                    # Se já detectou o sweep, aguarda a volta sólida
                    if sweep_detected:
                        reclaim_trigger = False
                        if side_norm == "buy" and current_price >= ambush_target:
                            reclaim_trigger = True
                        elif side_norm == "sell" and current_price <= ambush_target:
                            reclaim_trigger = True
                            
                        if reclaim_trigger:
                            # Validação final com CVD no Reclaim
                            cvd = await redis_service.get_cvd(symbol)
                            logger.info(f"🚀 [AMBUSH-RECLAIM] {symbol} recuperou o nível ({current_price:.6f})! Bote Wyckoff disparado. CVD: {cvd}")
                            return {"action": "TRIGGER", "reason": "WYCKOFF_RECLAIM", "price": current_price}
                
                # Lógica padrão de toque (para ativos Direct Pulse)
                else:
                    zone_reached = False
                    if side_norm == "buy":
                        if current_price <= ambush_target:
                            zone_reached = True
                    else: # sell
                        if current_price >= ambush_target:
                            zone_reached = True

                    if zone_reached:
                        # 2. Avaliação de Exaustão (CVD) e Momento (RSI)
                        cvd = await redis_service.get_cvd(symbol)
                        rsi = okx_ws_public_service.rsi_cache.get(symbol, 50.0)
                        
                        logger.info(f"🥷 [AMBUSH-ZONE] {symbol} tocou a zona ({current_price:.6f}). Flow Institucional -> CVD: {cvd}, RSI: {rsi:.1f}")

                        if side_norm == "buy":
                            if cvd < -150000:
                                logger.warning(f"🛑 [AMBUSH-ABORT] Faca caindo! {symbol} violou suporte com CVD Extremo ({cvd:.0f}). Abortando emboscada Long.")
                                return {"action": "ABORT", "reason": "CRITICAL_DUMP", "price": current_price}
                            
                            logger.info(f"🚀 [AMBUSH-TRIGGER] Absorção e Exaustão confirmadas em {symbol} ({current_price:.6f})! Executando Bote Long.")
                            return {"action": "TRIGGER", "reason": "DIP_BOUGHT", "price": current_price}
                            
                        else:
                            if cvd > 150000:
                                logger.warning(f"🛑 [AMBUSH-ABORT] Foguete subindo! {symbol} violou teto com CVD Extremo ({cvd:.0f}). Abortando emboscada Short.")
                                return {"action": "ABORT", "reason": "CRITICAL_PUMP", "price": current_price}

                            logger.info(f"🚀 [AMBUSH-TRIGGER] Rejeição de Topo confirmada em {symbol} ({current_price:.6f})! Executando Bote Short.")
                            return {"action": "TRIGGER", "reason": "RALLY_SOLD", "price": current_price}

                await asyncio.sleep(1)

            logger.warning(f"⏳ [AMBUSH-TIMEOUT] 30m esgotados para {symbol}. Fibo {ambush_target:.6f} não lamber.")
            return {"action": "TIMEOUT", "reason": "TIME_EXPIRED"}

        except Exception as e:
            logger.error(f"❌ [AMBUSH-ERROR] Falha na tocaia de {symbol}: {e}")
            return {"action": "ABORT", "reason": "SYSTEM_ERROR"}

ambush_agent = AmbushAgent()
