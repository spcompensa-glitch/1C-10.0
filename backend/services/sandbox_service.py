import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
from typing import List, Dict, Any, Optional, Set
from services.database_service import database_service, SandboxTrade
from services.okx_ws_public import okx_ws_public_service
from services.order_projection_service import OrderProjectionService

logger = logging.getLogger("SandboxService")
proj_service = OrderProjectionService()


class SandboxService:
    def __init__(self):
        self.is_running = False
        self._loop_task = None
        self._process_lock = asyncio.Lock()
        self._processed_signals = set()

        # Cache de preco (fallback quando WS falha) — espelha FlashAgent
        self._last_price_cache: Dict[str, float] = {}
        self._last_price_cache_ts: Dict[str, float] = {}

        # Cache de peak ROI por trade (para decisao de escadinha)
        self._peak_roi_cache: Dict[str, float] = {}

        # [V113] Auto-blacklist runtime (pares bloqueados automaticamente)
        self._auto_blocklist: Set[str] = set()

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._loop_task = asyncio.create_task(self._price_update_loop())
        asyncio.create_task(self._load_existing_radar_signals())
        asyncio.create_task(self._initial_auto_blocklist_check())
        logger.info("🧪 Sandbox Service iniciado com sucesso.")

    async def _load_existing_radar_signals(self):
        try:
            await asyncio.sleep(2.0)
            pulse_data = await database_service.get_radar_pulse()
            if pulse_data and "signals" in pulse_data:
                logger.info(f"🧪 [SANDBOX] Carregando {len(pulse_data['signals'])} sinais pré-existentes do Radar no Sandbox.")
                active_trades = await database_service.get_sandbox_trades(active_only=True)
                active_keys = {
                    (t.symbol.replace(".P", "").upper(), t.strategy, t.direction)
                    for t in active_trades
                }
                novos = [
                    s for s in pulse_data["signals"]
                    if (s.get("symbol", "").replace(".P", "").upper(),
                        s.get("strategy") or s.get("strategy_class") or "RADAR",
                        "LONG" if (s.get("side") or "Buy").lower() in ("buy", "long", "b") else "SHORT")
                    not in active_keys
                ]
                if novos:
                    logger.info(f"🧪 [SANDBOX] Processando {len(novos)} sinais novos do radar (já existem {len(active_trades)} ativos).")
                    await self._process_radar_signals(novos)
        except Exception as e:
            logger.error(f"Erro ao carregar sinais existentes no Sandbox: {e}")

    def stop(self):
        self.is_running = False
        if self._loop_task:
            self._loop_task.cancel()
        logger.info("🧪 Sandbox Service parado.")

    # ==================== PRICE RESOLUTION (espelha FlashAgent) ====================

    async def _get_rest_price(self, symbol: str) -> float:
        """Preço REST fresco para confirmar stops quando o WS/cache estiver atrasado."""
        try:
            from services.okx_rest import okx_rest_service
            ticker = await okx_rest_service.get_tickers(symbol=symbol)
            if isinstance(ticker, list) and ticker:
                return float(ticker[0].get("lastPrice") or 0)
            if isinstance(ticker, dict):
                return float(ticker.get("lastPrice") or ticker.get("last") or 0)
        except Exception as e:
            logger.debug(f"[SANDBOX] REST price fallback falhou para {symbol}: {e}")
        return 0.0

    async def _get_current_price(self, symbol: str) -> float:
        """
        Resolução de preço em cascata: WS → REST → cache local.
        Espelha FlashAgent._get_current_price para garantir que o stop
        nunca seja perdido por falha temporária do WebSocket.
        """
        # 1. Tenta WebSocket
        try:
            price = okx_ws_public_service.get_current_price(symbol)
            if price and price > 0:
                self._last_price_cache[symbol] = price
                self._last_price_cache_ts[symbol] = time.time()
                return price
        except Exception:
            pass

        # 2. Fallback REST
        rest_price = await self._get_rest_price(symbol)
        if rest_price > 0:
            self._last_price_cache[symbol] = rest_price
            self._last_price_cache_ts[symbol] = time.time()
            return rest_price

        # 3. Cache local (ate 60s de idade)
        last_price = self._last_price_cache.get(symbol, 0.0)
        last_ts = self._last_price_cache_ts.get(symbol, 0.0)
        if last_price > 0 and (time.time() - last_ts) < 60.0:
            return last_price

        return 0.0

    async def _check_stop_hit(self, side: str, stop_price: float, symbol: str) -> bool:
        """
        Verifica se o stop foi violado usando PREÇO CONSERVATIVO.
        Para LONG: usa o LOW dos últimos 120s (pega dips intra-ciclo)
        Para SHORT: usa o HIGH dos últimos 120s (pega pumps intra-ciclo)
        Fallback: preço atual WS → REST → cache (espelha FlashAgent).

        FIX (bug raiz LDOUSDT): antes, se WS retornava 0 em ambas as chamadas,
        retornava False sem consultar REST/cache — stop nunca era detectado.
        """
        if stop_price <= 0:
            return False

        try:
            check_price = okx_ws_public_service.get_conservative_price(symbol, side)
            if check_price > 0:
                stop_hit = (side.lower() == "buy" and check_price <= stop_price) or \
                           (side.lower() == "sell" and check_price >= stop_price)
                if stop_hit:
                    return True
        except Exception:
            pass

        # Fallback 1: preço atual via WS
        current_price = okx_ws_public_service.get_current_price(symbol)
        if current_price > 0:
            return (side.lower() == "buy" and current_price <= stop_price) or \
                   (side.lower() == "sell" and current_price >= stop_price)

        # Fallback 2: REST + cache (FIX — antes este fallback não existia)
        current_price = await self._get_current_price(symbol)
        if current_price <= 0:
            return False
        return (side.lower() == "buy" and current_price <= stop_price) or \
               (side.lower() == "sell" and current_price >= stop_price)

    # ==================== TICK SIZE ROUNDING ====================

    @staticmethod
    def _round_stop_to_tick(price: float, tick_size: float, side: str, stop_roi: float) -> float:
        """Arredonda stop price para o tick_size do contrato OKX."""
        if price <= 0 or tick_size <= 0:
            return price
        tick = Decimal(str(tick_size))
        if stop_roi >= 0 and side.lower() == "buy":
            rounding = ROUND_CEILING
        elif stop_roi >= 0 and side.lower() == "sell":
            rounding = ROUND_FLOOR
        else:
            rounding = ROUND_FLOOR if side.lower() == "buy" else ROUND_CEILING
        rounded = (Decimal(str(price)) / tick).quantize(Decimal("1"), rounding=rounding) * tick
        return float(rounded.normalize())

    # ==================== ADAPTIVE STOP ====================

    def _calculate_adaptive_stop(self, entry_price: float, side: str, contract_meta: dict, is_ranging: bool) -> float:
        """
        Calcula stop inicial adaptativo baseado no tick_size e volatilidade do ativo.
        Em vez de fixo -40%/-20%, usa um stop adaptativo:
        - Lateral: -15% ROI (mais apertado, mercado sem tendencia)
        - Tendencia: -30% ROI (mais largo, respiro para oscilacoes)
        Arredondado pelo tick_size do contrato.
        """
        if is_ranging:
            stop_roi = -15.0
        else:
            stop_roi = -30.0

        stop_price = proj_service.raw_price_from_roi(entry_price, stop_roi, side, 50.0)

        # Arredondar por tick_size se disponível
        tick_size = 0.0
        if isinstance(contract_meta, dict):
            tick_size = float(contract_meta.get("tickSize", 0) or 0)
        if tick_size > 0:
            stop_price = self._round_stop_to_tick(stop_price, tick_size, side, stop_roi)

        return stop_price

    # ==================== SIGNAL PROCESSING ====================

    async def on_radar_pulse(self, signals: List[Dict[str, Any]]):
        """Hook chamado sempre que novos sinais do radar são gerados."""
        if not signals:
            return
        async with self._process_lock:
            await self._process_radar_signals(signals)

    async def _process_radar_signals(self, signals: List[Dict[str, Any]]):
        """Processa sinais do radar com lock para evitar duplicatas por race condition."""
        for sig in signals:
            raw_symbol = sig.get("symbol")
            if not raw_symbol:
                continue
            symbol = raw_symbol.replace(".P", "").upper()

            signal_id = sig.get("id") or f"{symbol}_{sig.get('timestamp', 0)}"
            if signal_id in self._processed_signals:
                continue
            self._processed_signals.add(signal_id)
            if len(self._processed_signals) > 500:
                self._processed_signals.clear()

            side = sig.get("side", "Buy")
            direction = "LONG" if side.lower() in ("buy", "long", "b") else "SHORT"
            raw_strat = sig.get("strategy") or sig.get("strategy_class") or sig.get("strategy_type") or "RADAR"

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

            adx_val = 30.0
            try:
                val = getattr(okx_ws_public_service, "btc_adx", 0.0)
                if val > 0.1:
                    adx_val = val
            except Exception:
                pass
            is_ranging = (adx_val < 25)

            if is_ranging:
                if strategy not in ("DECOR SHADOW", "ALPHA SHIELD"):
                    continue
            else:
                if strategy not in ("VELOCITY FLOW", "ALPHA SHIELD"):
                    continue

            # [V113] Check static + auto-blocklist
            try:
                from config import settings
                static_blocklist = getattr(settings, 'ASSET_BLOCKLIST', set())
                is_auto = symbol in self._auto_blocklist
                if symbol in static_blocklist or is_auto:
                    reason = "auto-blocklist" if is_auto else "asset blocklist"
                    logger.info(f"🧪 [SANDBOX-BLOCKLIST] {symbol} descartado ({reason}).")
                    continue
            except Exception as e:
                logger.warning(f"Erro ao verificar blocklist: {e}")

            macro_trend = "BULLISH"
            decor_bypass = False
            try:
                from services.signal_generator import signal_generator
                btc_macro = await signal_generator.get_daily_macro_filter("BTCUSDT")
                macro_trend = "BULLISH" if btc_macro.get("above_200sma", True) else "BEARISH"

                if strategy == "DECOR SHADOW":
                    decor_data = sig.get("decorrelation") or {}
                    if decor_data.get("is_decorrelated", False) and decor_data.get("pearson", 1.0) < 0.35:
                        decor_bypass = True
            except Exception as e:
                logger.error(f"Error checking BTC macro trend for Sandbox: {e}")

            # [V113] Filtro horário — Abertura do mercado americano (13:30-14:30 UTC)
            # NÃO bloqueia, apenas exige confirmação extra
            try:
                now_utc = datetime.now(timezone.utc)
                current_hour_decimal = now_utc.hour + now_utc.minute / 60.0
                is_us_market_open = 13.5 <= current_hour_decimal < 14.5
            except Exception:
                is_us_market_open = False

            if is_us_market_open:
                if is_ranging:
                    # Em lateral durante abertura: só entra se tiver decor_bypass
                    if strategy == "DECOR SHADOW" and not decor_bypass:
                        logger.info(
                            f"🧪 [SANDBOX-OPEN-FILTER] {symbol} {strategy} descartado — "
                            f"abertura US (13:30-14:30) sem decor_bypass"
                        )
                        continue
                else:
                    # Em tendência durante abertura: exige ADX mais alto
                    if adx_val < 28:
                        logger.info(
                            f"🧪 [SANDBOX-OPEN-FILTER] {symbol} {strategy} descartado — "
                            f"abertura US (13:30-14:30) ADX {adx_val:.1f} < 28"
                        )
                        continue

            if not decor_bypass:
                if macro_trend == "BEARISH" and direction == "LONG":
                    logger.info(f"🧪 [SANDBOX-MACRO-BLOCK] {symbol} {strategy} LONG descartado em macro BEARISH.")
                    continue
                elif macro_trend == "BULLISH" and direction == "SHORT":
                    logger.info(f"🧪 [SANDBOX-MACRO-BLOCK] {symbol} {strategy} SHORT descartado em macro BULLISH.")
                    continue

            entry_price = float(sig.get("price") or sig.get("currentPrice") or 0.0)

            if entry_price <= 0.0:
                entry_price = okx_ws_public_service.get_current_price(symbol)
                if entry_price <= 0.0:
                    continue

            active_trades = await database_service.get_sandbox_trades(active_only=True)
            already_active = any(
                t.symbol.replace(".P", "").upper() == symbol
                and t.strategy == strategy
                and t.direction == direction
                for t in active_trades
            )
            if already_active:
                continue

            trade_id = f"sb_{symbol}_{strategy}_{int(time.time())}"

            # Stop inicial ADAPTATIVO (nao mais fixo -40%/-20%)
            contract_meta = sig.get("contract_info") or {}
            stop_price = self._calculate_adaptive_stop(entry_price, side, contract_meta, is_ranging)
            initial_stop_roi = -15.0 if is_ranging else -30.0

            # ==================== ENTRY SANITY CHECK ====================
            # Verifica se o preço de mercado atual já está além do stop
            # (sinal defasado / entry stale). Espelha verificação do sistema real.
            # Threshold: 70% do stop inicial (ex.: -30% stop → descarta se ROI < -21%)
            mkt_price = 0.0
            try:
                mkt_price = okx_ws_public_service.get_current_price(symbol)
                if mkt_price <= 0:
                    mkt_price = await self._get_rest_price(symbol)
                if mkt_price > 0 and entry_price > 0:
                    immediate_roi = proj_service.calculate_roi(entry_price, mkt_price, side, 50.0)
                    stale_threshold = initial_stop_roi * 0.7  # 70% do stop
                    if immediate_roi <= stale_threshold:
                        logger.warning(
                            f"🧪 [SANDBOX-STALE] {symbol} {strategy} {direction} descartado — "
                            f"entry defasado: ROI imediato={immediate_roi:.1f}% já passou "
                            f"{stale_threshold:.1f}% (stop={initial_stop_roi}%)"
                        )
                        continue
            except Exception as stale_err:
                logger.debug(f"[SANDBOX] Entry sanity check falhou para {symbol}: {stale_err}")
            # ==================== / ENTRY SANITY CHECK ====================

            trade_data = {
                "id": trade_id,
                "symbol": symbol,
                "strategy": strategy,
                "direction": direction,
                "entry_price": entry_price,
                "current_price": entry_price,
                "stop_loss": stop_price,
                "target": entry_price * 1.5,
                "max_roi": 0.0,
                "current_roi": 0.0,
                "pnl_pct": 0.0,
                "status": "ACTIVE",
                "opened_at": time.time(),
                "flash_state": {
                    "phase": "ESCADINHA",
                    "active_level": "INICIAL",
                    "stop_roi": initial_stop_roi,
                    "regime": "LATERAL" if is_ranging else "TRENDING",
                    "history": [f"Abertura em {entry_price} com SL inicial em {stop_price} ({initial_stop_roi}% ROI)"]
                },
                "contract_meta": contract_meta
            }

            await database_service.save_sandbox_trade(trade_data)
            asyncio.create_task(okx_ws_public_service.sync_topics([symbol]))

            logger.info(
                f"🧪 [SANDBOX-OPEN] {symbol} {strategy} {direction} | "
                f"Entry={entry_price:.4f} | SL={stop_price:.4f} ({initial_stop_roi}%) | "
                f"MktPrice={mkt_price:.4f} | TickSize={contract_meta.get('tickSize', 'N/A')}"
            )

    # ==================== AUTO-BLOCKLIST (V113) ====================

    async def _update_auto_blocklist(self):
        """[V113] Varre trades fechados e bloqueia pares com performance crítica.
        Critério: PnL total < -20% E win rate < 30% após 5+ trades fechados.
        """
        try:
            all_trades = await database_service.get_sandbox_trades(active_only=False)
            closed = [t for t in all_trades if t.status != "ACTIVE"]
            if len(closed) < 5:
                return

            pair_stats = {}
            for t in closed:
                sym = t.symbol
                if sym not in pair_stats:
                    pair_stats[sym] = {"total": 0, "wins": 0, "pnl": 0.0}
                pair_stats[sym]["total"] += 1
                pair_stats[sym]["pnl"] += t.pnl_pct
                if t.pnl_pct > 0:
                    pair_stats[sym]["wins"] += 1

            newly_blocked = []
            for sym, stats in pair_stats.items():
                if stats["total"] >= 5:
                    wr = (stats["wins"] / stats["total"]) * 100.0
                    if stats["pnl"] < -20.0 and wr < 30.0:
                        if sym not in self._auto_blocklist:
                            self._auto_blocklist.add(sym)
                            newly_blocked.append(sym)
                            logger.warning(
                                f"🧪 [SANDBOX-AUTO-BLOCKLIST] {sym} bloqueado automaticamente: "
                                f"PnL={stats['pnl']:.1f}%, WR={wr:.1f}% ({stats['wins']}/{stats['total']})"
                            )

            if newly_blocked:
                logger.info(
                    f"🧪 [SANDBOX-AUTO-BLOCKLIST] Total bloqueados: {len(self._auto_blocklist)} | "
                    f"Novos: {', '.join(newly_blocked)}"
                )
        except Exception as e:
            logger.error(f"Erro ao atualizar auto-blocklist: {e}")

    async def _initial_auto_blocklist_check(self):
        """Executa verificação inicial da auto-blacklist ao startup."""
        await asyncio.sleep(3.0)
        logger.info("🧪 [SANDBOX] Verificando auto-blocklist inicial...")
        await self._update_auto_blocklist()

    # ==================== MAIN LOOP (paridade com FlashAgent) ====================

    async def _price_update_loop(self):
        """
        Loop de 1s que monitora stops com a mesma logica robusta do FlashAgent:
        - Fallback REST → WS → cache quando preco indisponivel
        - Conservative price (HIGH/LOW 120s) para detectar spikes
        - Confirmacao REST antes de fechar
        - Peak ROI cache para decisao de escadinha
        - Tick size rounding no stop
        - Log detalhado quando stop nao e verificado
        - [V113] Auto-blocklist check a cada 120s
        """
        last_blocklist_check = 0.0
        while self.is_running:
            try:
                active_trades = await database_service.get_sandbox_trades(active_only=True)
                if not active_trades:
                    await asyncio.sleep(1.0)
                    continue

                for trade in active_trades:
                    try:
                        await self._process_trade_tick(trade)
                    except Exception as e:
                        logger.error(
                            f"[SANDBOX-ERROR] {trade.symbol} falhou no ciclo: {e}",
                            exc_info=True,
                        )

            except Exception as e:
                logger.error(f"Erro no loop de preços do Sandbox: {e}", exc_info=True)

            # [V113] Auto-blocklist check a cada 120s
            if time.time() - last_blocklist_check >= 120.0:
                asyncio.create_task(self._update_auto_blocklist())
                last_blocklist_check = time.time()

            await asyncio.sleep(1.0)

    async def _process_trade_tick(self, trade):
        """Processa um tick de UM trade — paridade com FlashAgent._process_slot."""
        symbol = trade.symbol
        side = "Buy" if trade.direction == "LONG" else "Sell"
        entry_price = float(trade.entry_price)

        if entry_price <= 0:
            return

        # 1. Resolver preco com fallback (REST → WS → cache)
        current_price = await self._get_current_price(symbol)
        if current_price <= 0:
            logger.warning(
                f"[SANDBOX-PRICE-UNAVAILABLE] {symbol} | "
                f"Entry={entry_price:.4f} Stop={trade.stop_loss:.4f} | "
                f"ACTION=SKIP (preço indisponível em todas as fontes)"
            )
            return

        # 2. Leverage e side
        leverage = 50.0
        if isinstance(trade.contract_meta, dict):
            try:
                leverage = float(trade.contract_meta.get("maxLeverage", 50.0) or 50.0)
            except (ValueError, TypeError):
                leverage = 50.0

        # 3. Calcular ROI
        current_roi = proj_service.calculate_roi(entry_price, current_price, side, leverage)

        # 4. Peak ROI (cache + persistido)
        trade_key = trade.id
        cached_peak = float(self._peak_roi_cache.get(trade_key, 0.0) or 0.0)
        stored_peak = float(trade.max_roi or 0.0)
        effective_roi = max(current_roi, cached_peak, stored_peak)
        self._peak_roi_cache[trade_key] = effective_roi
        max_roi = effective_roi

        # 5. Carregar estado do Flash
        raw_flash = trade.flash_state
        flash_state = dict(raw_flash) if raw_flash else {}
        history = list(flash_state.get("history", []))
        active_level_name = flash_state.get("active_level", "INICIAL")
        current_stop_roi = float(flash_state.get("stop_roi", -100.0))
        has_taken_partial = flash_state.get("has_taken_partial", False)
        partial_roi = flash_state.get("partial_roi", 0.0)

        # 6. ADX / regime
        adx_val = 30.0
        try:
            val = getattr(okx_ws_public_service, "btc_adx", 0.0)
            if val > 0.1:
                adx_val = val
        except Exception:
            pass
        is_ranging = (adx_val < 25)

        # 7. Partial TP (lateral, +15%)
        if is_ranging and max_roi >= 15.0 and not has_taken_partial:
            has_taken_partial = True
            partial_roi = max(15.0, current_roi)
            flash_state["has_taken_partial"] = True
            flash_state["partial_roi"] = partial_roi
            history.append(f"Saida Parcial de 50% executada a {partial_roi:.1f}% ROI")
            logger.info(f"🧪 [SANDBOX-PARTIAL] {symbol} parcial de 50% a {partial_roi:.1f}% ROI")

        # 8. PnL
        if has_taken_partial:
            pnl_pct = (partial_roi * 0.5) + (current_roi * 0.5)
        else:
            pnl_pct = current_roi

        # 9. Escadinha
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
                logger.info(f"🧪 [SANDBOX-FLASH] {symbol} subiu para {active_level.name} (SL {new_stop_roi}% ROI)")

        # 10. Stop price com tick_size rounding
        stop_price = proj_service.raw_price_from_roi(entry_price, updated_stop_roi, side, leverage)
        tick_size = 0.0
        if isinstance(trade.contract_meta, dict):
            try:
                tick_size = float(trade.contract_meta.get("tickSize", 0) or 0)
            except (ValueError, TypeError):
                tick_size = 0.0
        if tick_size > 0:
            stop_price = self._round_stop_to_tick(stop_price, tick_size, side, updated_stop_roi)

        # 11. Verificar stop hit com conservative price (HIGH/LOW 120s)
        is_closed = False
        should_run_blocklist = False
        status = "ACTIVE"
        closed_at = None
        exit_price = 0.0

        if stop_price > 0:
            stop_hit = await self._check_stop_hit(side, stop_price, symbol)
            if stop_hit:
                # Confirmacao REST antes de fechar
                fresh_price = await self._get_rest_price(symbol)
                if fresh_price > 0:
                    current_price = fresh_price
                    current_roi = proj_service.calculate_roi(entry_price, current_price, side, leverage)

                is_closed = True
                should_run_blocklist = True
                exit_price = stop_price
                closed_at = time.time()

        # 12. Atualizar flash state
        flash_state.update({
            "phase": updated_phase,
            "active_level": updated_level_name,
            "stop_roi": updated_stop_roi,
            "history": history
        })

        # 13. Payload de atualizacao
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
            actual_exit_roi = proj_service.calculate_roi(entry_price, exit_price, side, leverage)
            update_payload["current_roi"] = actual_exit_roi

            if has_taken_partial:
                final_pnl = (partial_roi * 0.5) + (actual_exit_roi * 0.5)
            else:
                final_pnl = actual_exit_roi
            update_payload["pnl_pct"] = final_pnl

            status = "CLOSED_TRAILING" if final_pnl > 0 else "CLOSED_SL"
            update_payload["status"] = status

            if status == "CLOSED_TRAILING":
                history.append(f"[TRAILING] Stop atingido em {exit_price} — fechado lucrativo com +{final_pnl:.1f}% ROI")
            else:
                history.append(f"Stop atingido em {exit_price} (SL configurado em {stop_price})")
                logger.warning(
                    f"📊 [SANDBOX-LOSS] {symbol} | Strategy={trade.strategy} | "
                    f"Dir={trade.direction} | Entry={entry_price:.4f} | "
                    f"Exit={exit_price:.4f} | ROI={final_pnl:.1f}% | "
                    f"StopROI={updated_stop_roi:.0f}% | MaxROI={max_roi:.1f}%"
                )

            # [V113] Auto-blocklist check após fechar trade
            if should_run_blocklist:
                asyncio.create_task(self._update_auto_blocklist())

            # Limpar cache de peak
            self._peak_roi_cache.pop(trade_key, None)

        await database_service.update_sandbox_trade(trade.id, update_payload)


sandbox_service = SandboxService()
