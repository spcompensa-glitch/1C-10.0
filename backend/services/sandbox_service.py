import asyncio
import logging
import time

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

        # [V117] Cooldown pós stop-out: {(symbol, direction): timestamp_do_stop}
        # Impede re-entry imediato no mesmo par+direção após loss
        # Ex: ADAUSDT SHORT pode ter cooldown mas ADAUSDT LONG ainda entra
        self._stop_cooldown: Dict[tuple, float] = {}

        # [V117] Rastreio de stops consecutivos por direção: {(symbol, direction): count}
        self._consecutive_stops: Dict[tuple, int] = {}

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

    # ==================== ADAPTIVE STOP (V119 — 30M Structural) ====================

    async def _get_30m_structural_stop(self, symbol: str, entry_price: float, side: str) -> Optional[float]:
        """
        [V119] Stop estrutural baseado no TF 30M.

        Lógica:
          - Busca 100 candles de 30M (~50h de dados)
          - Para LONG: encontra swing lows (suportes) abaixo do entry
          - Para SHORT: encontra swing highs (resistências) acima do entry
          - Posiciona stop com buffer de 0.15% além do nível estrutural
          - Se não encontrar swing válido: retorna None (fallback para % fixo)

        Swing detection (lookback=2 para filtrar ruído):
          - swing low: candle low < lows dos 2 candles vizinhos
          - swing high: candle high > highs dos 2 candles vizinhos
        """
        try:
            from services.okx_rest import okx_rest_service
            candles = await okx_rest_service.get_klines(symbol, interval="30", limit=100)
            if not candles or len(candles) < 15:
                logger.debug(f"[SANDBOX-V119] {symbol}: klines 30M insuficientes ({len(candles) if candles else 0}) — fallback")
                return None

            # OKX retorna mais recentes primeiro → inverter para ordem cronológica
            candles = list(reversed(candles))

            is_long = side.lower() in ("buy", "long", "b")
            lookback = 2

            if is_long:
                # Encontrar swing lows (suportes) abaixo do entry
                swing_lows = []
                for i in range(lookback, len(candles) - lookback):
                    try:
                        low_prev = float(candles[i - lookback].get("low") or candles[i - lookback][3])
                        low_curr = float(candles[i].get("low") or candles[i][3])
                        low_next = float(candles[i + lookback].get("low") or candles[i + lookback][3])
                        if low_curr < low_prev and low_curr < low_next and low_curr < entry_price:
                            swing_lows.append(low_curr)
                    except Exception:
                        pass

                if not swing_lows:
                    logger.debug(f"[SANDBOX-V119] {symbol} LONG: nenhum swing low abaixo de {entry_price:.4f}")
                    return None

                # [V119-FIX] Seleciona o swing low mais significativo (maior distância até o entry)
                # para dar espaço real para o preço respirar
                structural_level = max(swing_lows, key=lambda x: entry_price - x)
                distance_pct = (entry_price - structural_level) / entry_price * 100
                # [V119.1] Distância mínima 0.3% e máxima 8% do entry
                if distance_pct < 0.3:
                    logger.debug(f"[SANDBOX-V119] {symbol} LONG: swing low muito próximo ({distance_pct:.2f}% < 0.3%) — fallback")
                    return None
                if distance_pct > 8.0:
                    logger.debug(f"[SANDBOX-V119] {symbol} LONG: swing low muito distante ({distance_pct:.2f}% > 8%) — fallback")
                    return None
                buffer = structural_level * 0.0015  # 0.15% buffer abaixo do suporte
                buffer = max(buffer, structural_level * 0.0005)  # mínimo 0.05% do nível estrutural
                stop_price = structural_level - buffer
                logger.debug(
                    f"🧪 [SANDBOX-V119] {symbol} LONG: stop estrutural 30M="
                    f"{stop_price:.4f} (swing_low={structural_level:.4f}, buffer={buffer:.6f}, "
                    f"swing_lows_detectados={len(swing_lows)})"
                )
            else:
                # Encontrar swing highs (resistências) acima do entry
                swing_highs = []
                for i in range(lookback, len(candles) - lookback):
                    try:
                        high_prev = float(candles[i - lookback].get("high") or candles[i - lookback][2])
                        high_curr = float(candles[i].get("high") or candles[i][2])
                        high_next = float(candles[i + lookback].get("high") or candles[i + lookback][2])
                        if high_curr > high_prev and high_curr > high_next and high_curr > entry_price:
                            swing_highs.append(high_curr)
                    except Exception:
                        pass

                if not swing_highs:
                    logger.debug(f"[SANDBOX-V119] {symbol} SHORT: nenhum swing high acima de {entry_price:.4f}")
                    return None

                # [V119-FIX] Seleciona o swing high mais significativo (maior distância até o entry)
                # para dar espaço real para o preço respirar
                structural_level = min(swing_highs, key=lambda x: x - entry_price)
                distance_pct = (structural_level - entry_price) / entry_price * 100
                # [V119.1] Distância mínima 0.3% e máxima 8% do entry
                if distance_pct < 0.3:
                    logger.debug(f"[SANDBOX-V119] {symbol} SHORT: swing high muito próximo ({distance_pct:.2f}% < 0.3%) — fallback")
                    return None
                if distance_pct > 8.0:
                    logger.debug(f"[SANDBOX-V119] {symbol} SHORT: swing high muito distante ({distance_pct:.2f}% > 8%) — fallback")
                    return None
                buffer = structural_level * 0.0015  # 0.15% buffer acima da resistência
                buffer = max(buffer, structural_level * 0.0005)  # mínimo 0.05% do nível estrutural
                stop_price = structural_level + buffer
                logger.debug(
                    f"🧪 [SANDBOX-V119] {symbol} SHORT: stop estrutural 30M="
                    f"{stop_price:.4f} (swing_high={structural_level:.4f}, buffer={buffer:.6f}, "
                    f"swing_highs_detectados={len(swing_highs)})"
                )

            return stop_price

        except Exception as e:
            logger.debug(f"[SANDBOX-V119] {symbol}: erro ao calcular stop estrutural 30M: {e} — fallback")
            return None

    async def _calculate_adaptive_stop(self, symbol: str, entry_price: float, side: str, contract_meta: dict, is_ranging: bool) -> Dict[str, Any]:
        """
        [V119] Stop inicial adaptativo baseado em estrutura 30M.

        Prioridade:
          1. Stop estrutural 30M (swing low/high + buffer)
          2. Fallback: regime fixo — LATERAL -10%, TRENDING -15%

        GARANTIA_5 (escadinha): +5% ROI → stop vai a 0% (proteção rápida do capital).
        Arredondado pelo tick_size do contrato.

        Retorna dict:
          { "stop_price": float, "stop_roi": float, "source": str }
        """
        leverage = 50.0
        fallback_roi = -15.0 if is_ranging else -25.0
        tick_size = 0.0
        if isinstance(contract_meta, dict):
            tick_size = float(contract_meta.get("tickSize", 0) or 0)

        # 1. Tentar stop estrutural 30M
        structural_stop = await self._get_30m_structural_stop(symbol, entry_price, side)
        if structural_stop and structural_stop > 0:
            stop_price = structural_stop
            # Verificar se o ROI resultante é razoável (entre -10% e -40%)
            stop_roi = proj_service.calculate_roi(entry_price, stop_price, side, leverage)
            if -40.0 <= stop_roi <= -10.0:
                source = "structural_30m"
                if tick_size > 0:
                    stop_price = self._round_stop_to_tick(stop_price, tick_size, side, stop_roi)
                logger.info(
                    f"🧪 [SANDBOX-V119] {symbol} stop estrutural 30M aprovado: "
                    f"{stop_price:.4f} (ROI={stop_roi:.1f}%, source={source})"
                )
                return {"stop_price": stop_price, "stop_roi": stop_roi, "source": source}
            else:
                logger.info(
                    f"🧪 [SANDBOX-V119] {symbol} stop estrutural 30M rejeitado: "
                    f"ROI={stop_roi:.1f}% fora do range [-40%, -10%] — usando fallback"
                )

        # 2. Fallback: regime fixo
        stop_price = proj_service.raw_price_from_roi(entry_price, fallback_roi, side, leverage)
        if tick_size > 0:
            stop_price = self._round_stop_to_tick(stop_price, tick_size, side, fallback_roi)
        stop_roi = proj_service.calculate_roi(entry_price, stop_price, side, leverage)
        source = "regime_fixed"
        logger.info(
            f"🧪 [SANDBOX-V119] {symbol} usando fallback regime: "
            f"{stop_price:.4f} (ROI={stop_roi:.1f}%, source={source})"
        )
        return {"stop_price": stop_price, "stop_roi": stop_roi, "source": source}

    # ==================== SIGNAL PROCESSING ====================

    async def on_radar_pulse(self, signals: List[Dict[str, Any]]):
        """Hook chamado sempre que novos sinais do radar são gerados."""
        if not signals:
            return
        async with self._process_lock:
            await self._process_radar_signals(signals)

    async def _process_radar_signals(self, signals: List[Dict[str, Any]]):
        """Processa sinais do radar com lock para evitar duplicatas por race condition."""
        logger.info(f"🧪 [SANDBOX-DEBUG] _process_radar_signals chamado com {len(signals)} sinais")
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

            # [V119] Restabelecimento do ADX Regime Gating no Sandbox
            # Evita o ruído de rodar estratégias de tendência em mercado lateral e vice-versa
            if is_ranging:
                # Mercado Lateral: permite apenas DECOR SHADOW (e subsets)
                if strategy not in ("DECOR SHADOW", "DECOR_HUNTER"):
                    logger.info(f"🧪 [SANDBOX-REGIME-BLOCK] {symbol} {strategy} descartado — regime LATERAL (ADX={adx_val:.1f} < 25) aceita apenas DECOR SHADOW")
                    continue
            else:
                # Mercado em Tendência: permite apenas VELOCITY FLOW e ALPHA SHIELD
                if strategy in ("DECOR SHADOW", "DECOR_HUNTER"):
                    logger.info(f"🧪 [SANDBOX-REGIME-BLOCK] {symbol} {strategy} descartado — regime TENDENCIA (ADX={adx_val:.1f} >= 25) bloqueia DECOR SHADOW")
                    continue

            # [V118] Check static + auto-blocklist
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
                    # [V118-FIX] Chaves reais do decorrelation: is_active (nao is_decorrelated), correlation (nao pearson)
                    ds_decorrelated = decor_data.get("is_decorrelated", decor_data.get("is_active", False))
                    ds_pearson = decor_data.get("pearson", decor_data.get("correlation", 1.0))
                    if ds_decorrelated and ds_pearson < 0.35:
                        decor_bypass = True
            except Exception as e:
                logger.error(f"Error checking BTC macro trend for Sandbox: {e}")

            # [V118] LONG trades exigem desgrudado do BTC (Pearson < 0.35) + GÁS (confidence >= 70)
            # [V118-FIX] O decorrelation data vem do _sync_radar_rtdb com as chaves:
            #   is_active (NÃO is_decorrelated), score (NÃO confidence), correlation (NÃO pearson)
            if direction == "LONG":
                decor_data = sig.get("decorrelation") or {}
                # Fallback para ambas as nomenclaturas (signal_generator usa is_decorrelated, radar usa is_active)
                is_decorrelated = decor_data.get("is_decorrelated", decor_data.get("is_active", False))
                pearson = decor_data.get("pearson", decor_data.get("correlation", 1.0))
                decor_confidence = decor_data.get("confidence", decor_data.get("score", 0.0))

                # Se dados de decorrelação ausentes (pearson perto de 1.0 ou sem signals), tenta computar ao vivo
                if pearson >= 0.99 or not decor_data.get("signals"):
                    try:
                        from services.signal_generator import signal_generator
                        d_res = await signal_generator.detect_btc_decorrelation(symbol)
                        is_decorrelated = d_res.get("is_decorrelated", d_res.get("is_active", False))
                        pearson = d_res.get("pearson", d_res.get("correlation", 1.0))
                        decor_confidence = d_res.get("confidence", d_res.get("score", 0.0))
                    except Exception:
                        pass

                if not is_decorrelated or pearson >= 0.35 or decor_confidence < 70:
                    logger.info(
                        f"🧪 [SANDBOX-V118-FILTER] {symbol} {strategy} LONG descartado — "
                        f"decorrelated={is_decorrelated} pearson={pearson:.2f} conf={decor_confidence:.0f} "
                        f"(raw keys: is_active={decor_data.get('is_active')}, score={decor_data.get('score')}, "
                        f"correlation={decor_data.get('correlation')})"
                    )
                    continue
                # Se passou no filtro V118, também passa no MACRO-BLOCK
                decor_bypass = True

            # [V117] Filtro de horário e ADX noturno
            # UTC 22h-08h = noite asiática/madrugada europeia — chop mesmo com ADX=TRENDING
            # Durante esse horário, exige ADX >= 28 para entrar (filtra TRENDING falso)
            # US open (13:30-14:30 UTC): exige ADX >= 28 em tendência, decor_bypass em lateral
            try:
                now_utc = datetime.now(timezone.utc)
                current_hour = now_utc.hour
                current_hour_decimal = current_hour + now_utc.minute / 60.0
                is_us_market_open = 13.5 <= current_hour_decimal < 14.5
                is_night_session = current_hour >= 22 or current_hour < 8  # UTC 22h-08h
            except Exception:
                is_us_market_open = False
                is_night_session = False

            # [V117] Horário noturno: exige ADX >= 28 para TRENDING (evita chop de madrugada)
            if is_night_session and not is_ranging:
                if adx_val < 28:
                    logger.info(
                        f"🧪 [SANDBOX-NIGHT-FILTER] {symbol} {strategy} descartado — "
                        f"sessão noturna (UTC {now_utc.hour:02d}h) ADX {adx_val:.1f} < 28"
                    )
                    continue

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

            # [V118] MACRO-BLOCK desativado no Sandbox
            # Motivo: o V118 já protege LONGS com filtro de descorrelação (Pearson<0.35 + conf>=70).
            # SHORTs não têm proteção equivalente mas o sandbox é simulação — sem risco real.
            # O MACRO-BLOCK original (V115) ainda roda no sistema real (FlashAgent/Captain).

            entry_price = float(sig.get("price") or sig.get("currentPrice") or 0.0)

            if entry_price <= 0.0:
                entry_price = okx_ws_public_service.get_current_price(symbol)
                if entry_price <= 0.0:
                    logger.debug(f"🧪 [SANDBOX-NO-PRICE] {symbol} {strategy} {direction} sem preço — descartado (sig.price={sig.get('price')}, sig.currentPrice={sig.get('currentPrice')})")
                    continue

            active_trades = await database_service.get_sandbox_trades(active_only=True)
            already_active = any(
                t.symbol.replace(".P", "").upper() == symbol
                and t.strategy == strategy
                and t.direction == direction
                for t in active_trades
            )
            if already_active:
                logger.debug(f"🧪 [SANDBOX-ALREADY-ACTIVE] {symbol} {strategy} {direction} já está ativo — ignorando sinal duplicado")
                continue

            # [V117] Cooldown pós stop-out POR DIREÇÃO (symbol+direction)
            # 2 stops consecutivos SHORT → 10min; 1 stop → 5min
            cooldown_key = (symbol, direction)
            consecutive = self._consecutive_stops.get(cooldown_key, 0)
            COOLDOWN_SECS = 600.0 if consecutive >= 2 else 300.0  # 10min se 2+ stops, senão 5min
            last_sl_ts = self._stop_cooldown.get(cooldown_key, 0.0)
            elapsed = time.time() - last_sl_ts
            if elapsed < COOLDOWN_SECS:
                remaining = int(COOLDOWN_SECS - elapsed)
                logger.info(
                    f"🧪 [SANDBOX-COOLDOWN] {symbol} {direction} em cooldown: {remaining}s restantes "
                    f"(stops consecutivos: {consecutive}, cooldown: {int(COOLDOWN_SECS)}s)"
                )
                continue

            # [V114] Confirmação 1M — garante que o momentum de 1 minuto não está na direção contrária
            tf_1m_ok = await self._check_1m_confirmation(symbol, side)
            if not tf_1m_ok:
                logger.info(
                    f"🧪 [SANDBOX-1M-BLOCK] {symbol} {direction} bloqueado por falta de momentum no TF 1M"
                )
                continue

            # [V118.3] Confirmação 5M — exige maioria 2/3 dos candles alinhada com a direção do sinal
            tf_result = await self._check_5m_confirmation(symbol, side)
            if not tf_result.get("confirmed", True):
                logger.info(
                    f"🧪 [SANDBOX-5M-BLOCK] {symbol} {direction} bloqueado — "
                    f"{tf_result.get('detail', '')}"
                )
                continue
            score = float(sig.get("score", 0) or 0)
            boosted_score = score + tf_result.get("score_boost", 0.0)

            trade_id = f"sb_{symbol}_{strategy}_{int(time.time())}"

            # [V119] Stop inicial adaptativo baseado em estrutura 30M
            contract_meta = sig.get("contract_info") or {}
            stop_result = await self._calculate_adaptive_stop(symbol, entry_price, side, contract_meta, is_ranging)
            stop_price = stop_result["stop_price"]
            initial_stop_roi = stop_result["stop_roi"]

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
                    stale_threshold = max(initial_stop_roi * 0.7, -10.0)  # [V113.2] Floor -10% p/ evitar descartes por ruído de tick (com -5% stop, 70% = -3.5% = 0.07% price move — muito apertado)
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
                    "history": [f"Abertura em {entry_price} com SL inicial em {stop_price} ({initial_stop_roi}% ROI, source={stop_result['source']})"]
                },
                "contract_meta": contract_meta
            }

            await database_service.save_sandbox_trade(trade_data)
            asyncio.create_task(okx_ws_public_service.sync_topics([symbol]))

            logger.info(
                f"🧪 [SANDBOX-OPEN] {symbol} {strategy} {direction} | "
                f"Entry={entry_price:.4f} | SL={stop_price:.4f} ({initial_stop_roi:.1f}%, src={stop_result['source']}) | "
                f"MktPrice={mkt_price:.4f} | TickSize={contract_meta.get('tickSize', 'N/A')}"
            )

    # ==================== [V114] 1M CONFIRMATION FILTER ====================

    async def _check_1m_confirmation(self, symbol: str, side: str) -> bool:
        """
        [V114] Confirmação de entrada pelo TF de 1 minuto.

        Lógica:
          - Busca os últimos 5 candles de 1M via OKX REST (usa cache 3min do get_klines)
          - Para SHORT: pelo menos 2 dos 3 candles mais recentes devem ser BEARISH
            (close <= open) — sinal de momentum descendente antes de entrar
          - Para LONG:  pelo menos 2 dos 3 candles mais recentes devem ser BULLISH
            (close >= open)
          - Se não conseguir buscar candles: APROVA (fail-open, não bloqueia por falha de API)

        Por que 3 candles com threshold 2/3:
          - Exige consenso mínimo sem exigir unanimidade (que rejeitaria entradas legítimas
            onde 1 candle faz ruído antes de confirmar a direção)
          - Elimina entradas onde o ativo está indo na direção OPOSTA no curto prazo
            (ex.: INJ SHORT mas 1M mostrando pump — exatamente o que causou os stop-outs em 7s)
        """
        try:
            from services.okx_rest import okx_rest_service
            # interval="1" = 1 minuto no mapeamento do OKX REST
            candles = await okx_rest_service.get_klines(symbol, interval="1", limit=5)
            if not candles or len(candles) < 3:
                logger.debug(f"[SANDBOX-1M] {symbol}: candles insuficientes para confirmação — aprovando")
                return True

            # Candles retornados mais recentes primeiro (OKX padrão)
            # Pega os 3 mais recentes e avalia direção: close vs open
            recent = candles[:3]
            bearish_count = 0
            bullish_count = 0
            for c in recent:
                try:
                    if isinstance(c, dict):
                        o = float(c.get("open") or c.get("o") or 0.0)
                        cl = float(c.get("close") or c.get("c") or 0.0)
                    else:  # Lista/tupla nativa do OKX REST
                        o = float(c[1])
                        cl = float(c[4])
                    
                    if cl < o:   # candle vermelho
                        bearish_count += 1
                    else:        # candle verde ou doji
                        bullish_count += 1
                except Exception as ex:
                    logger.debug(f"[SANDBOX-1M] Erro ao parsear candle 1M: {ex}")

            is_short = side.lower() in ("sell", "short", "s")
            if is_short:
                # [V119] Sandbox: Exige maioria (pelo menos 2 de 3) de candles de 1M bearish para SHORT
                confirmed = bearish_count >= 2
                if not confirmed:
                    logger.info(
                        f"🧪 [SANDBOX-1M-REJECT] {symbol} SHORT — minoria de momentum 1M bearish "
                        f"({bullish_count}/3 bullish, {bearish_count}/3 bearish)"
                    )
                return confirmed
            else:
                # [V119] Sandbox: Exige maioria (pelo menos 2 de 3) de candles de 1M bullish para LONG
                confirmed = bullish_count >= 2
                if not confirmed:
                    logger.info(
                        f"🧪 [SANDBOX-1M-REJECT] {symbol} LONG — minoria de momentum 1M bullish "
                        f"({bullish_count}/3 bullish, {bearish_count}/3 bearish)"
                    )
                return confirmed

        except Exception as e:
            logger.debug(f"[SANDBOX-1M] {symbol}: falha ao checar confirmação 1M: {e} — aprovando")
            return True  # fail-open

    # ==================== [V116] 5M CONFIRMATION FILTER ====================

    async def _check_5m_confirmation(self, symbol: str, side: str) -> dict:
        """
        [V118.3] Confirmação de entrada pelo TF de 5 minutos com alinhamento de tendência.

        Lógica:
          - Busca os últimos 5 candles de 5m via OKX REST
          - Avalia os 3 candles mais recentes FECHADOS (ignora candle aberto em formação)
          - Para SHORT: BLOQUEIA se < 2 candles são bearish (0 ou 1 bearish = minoria)
          - Para LONG:  BLOQUEIA se < 2 candles são bullish (0 ou 1 bullish = minoria)
          - Exige maioria 2/3 para confirmar alinhamento com a direção do sinal
          - Se aprovado: score_boost = +10 (3/3) ou +5 (2/3)
          - Fail-open: se API falhar ou candles insuficientes, APROVA sem bloquear

        Retorna dict:
          {
            "confirmed": bool — False = BLOQUEIA o trade, True = APROVA
            "score_boost": float — bônus informativo (0, +5 ou +10)
            "detail": str — descrição para log
          }
        """
        result = {"confirmed": True, "score_boost": 0.0, "detail": ""}

        try:
            from services.okx_rest import okx_rest_service
            candles = await okx_rest_service.get_klines(symbol, interval="5", limit=5)
            if not candles or len(candles) < 4:
                result["detail"] = "candles insuficientes — fail-open"
                return result

            # Ignora candle[0] que pode estar aberto; usa [1], [2] e [3] (fechados)
            closed = candles[1:4]

            bearish_count = 0
            bullish_count = 0
            directions = []
            is_short = side.lower() in ("sell", "short", "s")

            for c in closed:
                try:
                    if isinstance(c, dict):
                        o = float(c.get("open") or c.get("o") or 0.0)
                        cl = float(c.get("close") or c.get("c") or 0.0)
                    else:  # Lista/tupla nativa do OKX REST
                        o = float(c[1])
                        cl = float(c[4])
                    
                    if cl < o:
                        bearish_count += 1
                        directions.append("BEAR")
                    elif cl > o:
                        bullish_count += 1
                        directions.append("BULL")
                    else:
                        directions.append("DOJI")
                except Exception as ex:
                    logger.debug(f"[SANDBOX-5M] Erro ao parsear candle 5M: {ex}")
                    directions.append("UNK")

            dir_str = " + ".join(directions)

            # Se todos DOJI/UNK, fail-open (não consegue determinar direção)
            total_valid = bearish_count + bullish_count
            if total_valid == 0:
                result["detail"] = "candles sem direção definida — fail-open"
                return result

            if is_short:
                # [V118.3] SHORT: exige maioria bearish (>= 2/3)
                if bearish_count < 2:
                    result["confirmed"] = False
                    result["score_boost"] = 0.0
                    result["detail"] = f"5m BLOCK SHORT — {bearish_count}/3 bearish ({dir_str}): 5M nao esta em SHORT"
                    return result
                boost = 10.0 if bearish_count >= 3 else 5.0
                label = "FORTE" if bearish_count >= 3 else "MODERADA"
            else:
                # [V118.3] LONG: exige maioria bullish (>= 2/3)
                if bullish_count < 2:
                    result["confirmed"] = False
                    result["score_boost"] = 0.0
                    result["detail"] = f"5m BLOCK LONG — {bullish_count}/3 bullish ({dir_str}): 5M nao esta em LONG"
                    return result
                boost = 10.0 if bullish_count >= 3 else 5.0
                label = "FORTE" if bullish_count >= 3 else "MODERADA"

            result["confirmed"] = True
            result["score_boost"] = boost
            result["detail"] = f"5m OK {label} ({dir_str}) boost=+{boost:.0f}"

            logger.debug(f"🧪 [SANDBOX-5M] {symbol} {side} — {result['detail']}")
            return result

        except Exception as e:
            result["confirmed"] = True  # fail-open
            result["detail"] = f"erro: {e} — fail-open"
            logger.debug(f"[SANDBOX-5M] {symbol}: {result['detail']}")
            return result

    # ==================== AUTO-BLOCKLIST (V113) ====================

    async def _update_auto_blocklist(self):
        """[V118] Varre trades fechados e bloqueia pares com performance crítica.
        Critério: PnL total < -15% E win rate < 35% após 3+ trades fechados.
        """
        try:
            all_trades = await database_service.get_sandbox_trades(active_only=False)
            closed = [t for t in all_trades if t.status != "ACTIVE"]
            if len(closed) < 3:
                return

            pair_stats = {}
            for t in closed:
                sym = t.symbol
                if sym not in pair_stats:
                    pair_stats[sym] = {"total": 0, "wins": 0, "pnl": 0.0}
                pair_stats[sym]["total"] += 1
                # [V118] Garantir que pnl_pct seja float
                try:
                    pnl_val = float(t.pnl_pct or 0.0)
                except (ValueError, TypeError):
                    pnl_val = 0.0
                pair_stats[sym]["pnl"] += pnl_val
                if pnl_val > 0:
                    pair_stats[sym]["wins"] += 1

            newly_blocked = []
            for sym, stats in pair_stats.items():
                if stats["total"] >= 3:  # [V118] Reduzido de 5 para 3 trades
                    wr = (stats["wins"] / stats["total"]) * 100.0
                    # [V118] Critério mais agressivo: PnL < -15% (era -20%) e WR < 35% (era 30%)
                    if stats["pnl"] < -15.0 and wr < 35.0:
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
        # [V118] GARANTIA_5: degrau antecipado — +5% ROI → stop vai a 0% (break-even)
        # Protege a largada rapidamente: se o preço mover +0.1% (50x) e cair, saímos empatados
        # Se o trade tem força, +5% ROI é só o começo (vai pro +100%, +200%, +1200%...)
        # Se voltar do +5% para o 0%, pagamos só taxas e estamos prontos para re-tentar
        ladder = proj_service.get_stop_ladder(max_roi, is_ranging=is_ranging)
        active_level = proj_service.get_active_level(max_roi, ladder, is_ranging=is_ranging)

        updated_stop_roi = current_stop_roi
        updated_level_name = active_level_name
        updated_phase = flash_state.get("phase", "ESCADINHA")

        # [V118] GARANTIA_5 — break-even antecipado em +5% ROI
        # Só aplica se ainda não passou do GARANTIA_5 (current_stop_roi < 0)
        if max_roi >= 5.0 and current_stop_roi < 0.0:
            new_stop_roi = 0.0  # break-even
            if new_stop_roi > current_stop_roi:
                updated_stop_roi = new_stop_roi
                updated_level_name = "GARANTIA_5"
                updated_phase = "ESCADINHA"
                history.append(f"[V118] GARANTIA_5: Break-even ativado a {max_roi:.1f}% ROI — stop → 0%")
                logger.info(f"🧪 [SANDBOX-FLASH] {symbol} GARANTIA_5 ativado (max_roi={max_roi:.1f}%) — stop agora em 0% ROI")

        if active_level:
            new_stop_roi = active_level.stop_roi
            if new_stop_roi > current_stop_roi and new_stop_roi > updated_stop_roi:
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
                # [V117] Cooldown por DIREÇÃO (symbol+direction)
                # 2+ stops consecutivos mesma direção → 10min; 1 stop → 5min
                clean_sym = symbol.replace(".P", "").upper()
                trade_dir = trade.direction  # "LONG" ou "SHORT"
                cooldown_key = (clean_sym, trade_dir)
                prev_consec = self._consecutive_stops.get(cooldown_key, 0)
                self._consecutive_stops[cooldown_key] = prev_consec + 1
                # Zera o contador da direção oposta (se era SHORT, limpa LONG e vice-versa)
                opposite_dir = "LONG" if trade_dir == "SHORT" else "SHORT"
                self._consecutive_stops[(clean_sym, opposite_dir)] = 0
                self._stop_cooldown[cooldown_key] = time.time()
                new_consec = self._consecutive_stops[cooldown_key]
                cooldown_applied = 600 if new_consec >= 2 else 300
                logger.info(
                    f"🧪 [SANDBOX-COOLDOWN-SET] {clean_sym} {trade_dir} cooldown de {cooldown_applied}s "
                    f"(stops consecutivos nesta direção: {new_consec})"
                )
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
