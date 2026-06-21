import asyncio
import logging
import time
import uuid
from typing import List, Dict, Any
from services.database_service import database_service, SandboxTrade
from services.okx_ws_public import okx_ws_public_service
from services.order_projection_service import OrderProjectionService

logger = logging.getLogger("SandboxService")
proj_service = OrderProjectionService()

class SandboxService:
    def __init__(self):
        self.is_running = False
        self._loop_task = None

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._loop_task = asyncio.create_task(self._price_update_loop())
        # 🧪 Carga inicial de sinais existentes
        asyncio.create_task(self._load_existing_radar_signals())
        logger.info("🧪 Sandbox Service iniciado com sucesso.")

    async def _load_existing_radar_signals(self):
        try:
            await asyncio.sleep(2.0) # Espera DB conectar
            pulse_data = await database_service.get_radar_pulse()
            if pulse_data and "signals" in pulse_data:
                logger.info(f"🧪 [SANDBOX] Carregando {len(pulse_data['signals'])} sinais pré-existentes do Radar no Sandbox.")
                await self.on_radar_pulse(pulse_data["signals"])
        except Exception as e:
            logger.error(f"Erro ao carregar sinais existentes no Sandbox: {e}")

    def stop(self):
        self.is_running = False
        if self._loop_task:
            self._loop_task.cancel()
        logger.info("🧪 Sandbox Service parado.")

    async def on_radar_pulse(self, signals: List[Dict[str, Any]]):
        """Hook chamado sempre que novos sinais do radar são gerados."""
        if not signals:
            return

        for sig in signals:
            symbol = sig.get("symbol")
            if not symbol:
                continue

            # Identificar direção: Buy/LONG, Sell/SHORT
            side = sig.get("side", "Buy")
            direction = "LONG" if side.lower() in ("buy", "long", "b") else "SHORT"
            raw_strat = sig.get("strategy") or sig.get("strategy_class") or sig.get("strategy_type") or "RADAR"
            
            # Mapeamento robusto para os 3 Pilares do Sniper
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
                
            # Sandbox deve aceitar todos os sinais para fins de simulação/estatística

            entry_price = float(sig.get("price") or sig.get("currentPrice") or 0.0)

            if entry_price <= 0.0:
                # Fallback para preço atual do WebSocket
                entry_price = okx_ws_public_service.get_current_price(symbol)
                if entry_price <= 0.0:
                    continue

            # Verificar se já existe trade ATIVO para este símbolo + estratégia para evitar duplicidade
            active_trades = await database_service.get_sandbox_trades(active_only=True)
            already_active = any(t.symbol == symbol and t.strategy == strategy for t in active_trades)
            if already_active:
                continue

            # Criar novo trade simulado
            trade_id = f"sb_{symbol.replace('.P', '')}_{strategy}_{int(time.time())}"
            
            # Setup inicial do stop loss
            # [V112.6] Stop inicial dinâmico por regime: -20% ROI em mercado lateral, -30% ROI em tendência.
            adx_val = 30.0
            try:
                val = getattr(okx_ws_public_service, "btc_adx", 0.0)
                if val > 0.1:
                    adx_val = val
            except Exception:
                pass
            is_ranging = (adx_val < 25)
            
            initial_stop_roi = -20.0 if is_ranging else -30.0
            stop_price = proj_service.raw_price_from_roi(entry_price, initial_stop_roi, side, 50.0)

            trade_data = {
                "id": trade_id,
                "symbol": symbol,
                "strategy": strategy,
                "direction": direction,
                "entry_price": entry_price,
                "current_price": entry_price,
                "stop_loss": stop_price,
                "target": entry_price * 1.5, # Ponto inicial de Emancipação
                "max_roi": 0.0,
                "current_roi": 0.0,
                "pnl_pct": 0.0,
                "status": "ACTIVE",
                "opened_at": time.time(),
                "flash_state": {
                    "phase": "ESCADINHA",
                    "active_level": "INICIAL",
                    "stop_roi": initial_stop_roi,
                    "history": [f"Abertura em {entry_price} com SL inicial em {stop_price} ({initial_stop_roi}% ROI)"]
                },
                "contract_meta": sig.get("contract_info") or {}
            }

            # Registrar no banco Postgres
            await database_service.save_sandbox_trade(trade_data)

            # Assinar o canal público de WebSocket da OKX para atualizações de preço em tempo real
            asyncio.create_task(okx_ws_public_service.sync_topics([symbol]))

    async def _price_update_loop(self):
        """Loop de alta frequência que atualiza preços das posições virtuais e aplica regras do Flash."""
        from services.okx_ws_public import okx_ws_public_service
        while self.is_running:
            try:
                active_trades = await database_service.get_sandbox_trades(active_only=True)
                if not active_trades:
                    await asyncio.sleep(1.0)
                    continue

                for trade in active_trades:
                    symbol = trade.symbol
                    current_price = okx_ws_public_service.get_current_price(symbol)
                    
                    if current_price <= 0.0:
                        continue

                    # Calcular ROI e PnL simulados
                    leverage = float(trade.contract_meta.get("maxLeverage", 50.0) if trade.contract_meta else 50.0)
                    side = "Buy" if trade.direction == "LONG" else "Sell"
                    
                    current_roi = proj_service.calculate_roi(trade.entry_price, current_price, side, leverage)
                    max_roi = max(trade.max_roi, current_roi)
                    pnl_pct = current_roi

                    # Carregar estado do Flash
                    flash_state = dict(trade.flash_state or {})
                    history = list(flash_state.get("history", []))
                    active_level_name = flash_state.get("active_level", "INICIAL")
                    current_stop_roi = float(flash_state.get("stop_roi", -100.0))

                    # Lógica da Escadinha (Trailing Stop progressivo) baseado no ADX
                    adx_val = 30.0
                    try:
                        val = getattr(okx_ws_public_service, "btc_adx", 0.0)
                        if val > 0.1:
                            adx_val = val
                    except Exception:
                        pass
                    is_ranging = (adx_val < 25)
                    
                    ladder = proj_service.get_stop_ladder(max_roi, is_ranging=is_ranging)
                    active_level = proj_service.get_active_level(max_roi, ladder, is_ranging=is_ranging)

                    updated_stop_roi = current_stop_roi
                    updated_level_name = active_level_name
                    updated_phase = flash_state.get("phase", "ESCADINHA")

                    if active_level:
                        new_stop_roi = active_level.stop_roi
                        
                        if new_stop_roi > current_stop_roi:
                            updated_stop_roi = new_stop_roi
                            updated_level_name = active_level.name
                            updated_phase = active_level.phase
                            history.append(f"Subiu degrau para {active_level.name} (Stop: {new_stop_roi}% ROI) no preço {current_price}")
                            logger.info(f"🧪 [SANDBOX-FLASH] {trade.symbol} subiu para {active_level.name} (SL {new_stop_roi}% ROI)")

                    # Verificar gatilho de Stop Loss
                    is_closed = False
                    status = "ACTIVE"
                    closed_at = None
                    exit_price = 0.0

                    # O stop loss de preço é calculado com base no updated_stop_roi
                    stop_price = proj_service.raw_price_from_roi(trade.entry_price, updated_stop_roi, side, leverage)
                    
                    # Checar violação do stop loss
                    if trade.direction == "LONG" and current_price <= stop_price:
                        is_closed = True
                        status = "CLOSED_SL"
                        exit_price = stop_price
                        closed_at = time.time()
                        history.append(f"Violou Stop Loss em {current_price} (SL configurado em {stop_price})")
                    elif trade.direction == "SHORT" and current_price >= stop_price:
                        is_closed = True
                        status = "CLOSED_SL"
                        exit_price = stop_price
                        closed_at = time.time()
                        history.append(f"Violou Stop Loss em {current_price} (SL configurado em {stop_price})")

                    # Atualizar flash state
                    flash_state.update({
                        "phase": updated_phase,
                        "active_level": updated_level_name,
                        "stop_roi": updated_stop_roi,
                        "history": history
                    })

                    # Dados de atualização
                    update_payload = {
                        "current_price": current_price,
                        "current_roi": current_roi,
                        "max_roi": max_roi,
                        "pnl_pct": pnl_pct,
                        "stop_loss": stop_price,
                        "status": status,
                        "flash_state": flash_state
                    }

                    if is_closed:
                        update_payload["closed_at"] = closed_at
                        update_payload["current_price"] = exit_price
                        # Recalcular ROI usando o preço de saída real do stop (evita saltos absurdos de liquidação simulados por spikes)
                        actual_exit_roi = proj_service.calculate_roi(trade.entry_price, exit_price, side, leverage)
                        update_payload["current_roi"] = actual_exit_roi
                        update_payload["pnl_pct"] = actual_exit_roi

                    await database_service.update_sandbox_trade(trade.id, update_payload)

            except Exception as e:
                logger.error(f"Erro no loop de preços do Sandbox: {e}", exc_info=True)

            await asyncio.sleep(1.0)

sandbox_service = SandboxService()
