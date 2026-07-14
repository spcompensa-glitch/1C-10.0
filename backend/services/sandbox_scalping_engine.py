# -*- coding: utf-8 -*-
"""
[VWAP SNIPER] SandboxScalpingEngine - V1.0
===========================================
Motor primario e EXCLUSIVO do Scalping Lab.

Opera em timeframes de 1m e 5m para capturar momentum
de curtissimo prazo com 50x de alavancagem.

Estrategia: VWAP SNIPER
  Camada 1 - Filtro de Tendencia (5m):
    - EMA 200 (5m) define a direcao dominante.
    - So entrar LONG se preco > EMA200, SHORT se preco < EMA200.

  Camada 2 - Zona de Entrada (1m):
    - VWAP intradiario calculado sobre os candles de 1m.
    - Preco deve estar dentro de 0.15% da linha VWAP.

  Camada 3 - Gatilho (1m):
    - Stochastic RSI (14, 14, 3, 3).
    - Long: K cruza D de baixo pra cima saindo da sobrevenda (<25).
    - Short: K cruza D de cima pra baixo saindo da sobrecompra (>75).

  Bonus - Liquidity Sweep:
    - Pin Bar/Hammer de rejeicao de maxima/minima anterior.

Score final minimo: 60/100 para abrir posicao.
Stop Loss: 1.0x ATR do 1m, maximo -20% ROI (= 0.4% no preco com 50x).
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List

logger = logging.getLogger("ScalpingEngine")

# ── Constantes ─────────────────────────────────────────────────────────────────
_LEVERAGE           = 50.0
# [V126] Banca $10.000 | 40% = $4.000 | 20 ordens x $200 (10 Scalp + 10 Swing)
_MARGIN_PER_TRADE   = 200.0
_SCAN_INTERVAL      = 60      # segundos entre scans
_MAX_SLOTS          = 10      # slots simultaneos maximos de Scalping
# [V126] Score minimo aumentado de 60 para 70 para exigir Liquidity Sweep (15pts)
# Base: 168 trades reais — WR 57.58% mas R:R 1:0.88 (loss medio > win medio)
# Com score 70, o sinal obrigatoriamente passa pelas 3 camadas + Sweep.
_MIN_SCORE          = 70      # score minimo para entrada (obriga Sweep)
_MAX_STOP_ROI       = -20.0   # perda maxima em ROI (%)
_VWAP_TOLERANCE_PCT = 0.15    # tolerancia do preco vs VWAP (%)
_STOCH_OVERSOLD     = 25.0
_STOCH_OVERBOUGHT   = 75.0
_EMA_PERIOD         = 200
# [V126] Filtro de ATR minimo: mercado com ATR < 0.02% do preco nao tem
# volatilidade suficiente para o VWAP Sniper — stop ficaria micro e seria violado
_MIN_ATR_PCT        = 0.02    # ATR minimo como % do preco


# ── Utilitarios de Indicadores ─────────────────────────────────────────────────

def _calculate_ema(values: List[float], period: int) -> float:
    """EMA classica com inicializacao SMA."""
    if not values or len(values) < period:
        return 0.0
    multiplier = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for price in values[period:]:
        ema = (price - ema) * multiplier + ema
    return ema


def _calculate_vwap(candles: list) -> float:
    """VWAP intradiario: sum(TP*Vol) / sum(Vol). TP = (H+L+C)/3."""
    if not candles:
        return 0.0
    cum_tpv = 0.0
    cum_vol = 0.0
    for c in candles:
        try:
            high  = float(c[2] if isinstance(c, list) else c.get('high', c[2] if isinstance(c, list) else 0))
            low   = float(c[3] if isinstance(c, list) else c.get('low',  c[3] if isinstance(c, list) else 0))
            close = float(c[4] if isinstance(c, list) else c.get('close',c[4] if isinstance(c, list) else 0))
            vol   = float(c[5] if isinstance(c, list) else c.get('volume', c[5] if isinstance(c, list) else 0)) or 0.0
        except (IndexError, ValueError, TypeError):
            continue
        tp = (high + low + close) / 3.0
        cum_tpv += tp * vol
        cum_vol  += vol
    return cum_tpv / cum_vol if cum_vol > 0 else 0.0


def _parse_close(c) -> float:
    """Extrai o preco de fechamento de um candle (lista ou dict)."""
    try:
        if isinstance(c, list):
            return float(c[4])
        return float(c.get('close') or c.get('c') or 0)
    except (IndexError, ValueError, TypeError):
        return 0.0


def _parse_ohlcv(c):
    """Extrai open, high, low, close de um candle."""
    try:
        if isinstance(c, list):
            return float(c[1]), float(c[2]), float(c[3]), float(c[4])
        return (float(c.get('open', 0)), float(c.get('high', 0)),
                float(c.get('low', 0)),  float(c.get('close', 0)))
    except (IndexError, ValueError, TypeError):
        return 0.0, 0.0, 0.0, 0.0


def _calculate_rsi(closes: List[float], period: int = 14) -> List[float]:
    """RSI de Wilder."""
    if len(closes) < period + 1:
        return []
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    rsi_values = []
    for i in range(period, len(gains)):
        if al == 0:
            rsi_values.append(100.0)
        else:
            rsi_values.append(100.0 - (100.0 / (1.0 + ag / al)))
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    return rsi_values


def _calculate_stoch_rsi(closes: List[float], rsi_period: int = 14,
                          stoch_period: int = 14, k_smooth: int = 3,
                          d_smooth: int = 3) -> Dict[str, float]:
    """Stochastic RSI com suavizacao K e D."""
    empty = {"k": 50.0, "d": 50.0, "prev_k": 50.0, "prev_d": 50.0}
    rsi = _calculate_rsi(closes, rsi_period)
    if len(rsi) < stoch_period + k_smooth + d_smooth:
        return empty

    raw = []
    for i in range(stoch_period - 1, len(rsi)):
        w = rsi[i - stoch_period + 1: i + 1]
        lo, hi = min(w), max(w)
        rng = hi - lo
        raw.append(((rsi[i] - lo) / rng * 100.0) if rng > 0 else 50.0)

    if len(raw) < k_smooth + d_smooth:
        return empty

    k_vals = [sum(raw[i - k_smooth + 1: i + 1]) / k_smooth
               for i in range(k_smooth - 1, len(raw))]
    if len(k_vals) < d_smooth + 1:
        return empty

    d_vals = [sum(k_vals[i - d_smooth + 1: i + 1]) / d_smooth
               for i in range(d_smooth - 1, len(k_vals))]
    if len(d_vals) < 2:
        return empty

    return {
        "k":      round(k_vals[-1], 2),
        "d":      round(d_vals[-1], 2),
        "prev_k": round(k_vals[-2], 2),
        "prev_d": round(d_vals[-2], 2),
    }


def _detect_liquidity_sweep(candles_1m: list, direction: str) -> bool:
    """Detecta Pin Bar/Hammer nos ultimos 3 candles (armadilha de liquidez)."""
    for c in candles_1m[-3:]:
        o, h, l, cl = _parse_ohlcv(c)
        total = h - l
        if total <= 0:
            continue
        lower_wick = min(o, cl) - l
        upper_wick = h - max(o, cl)
        if direction == 'LONG':
            if lower_wick / total >= 0.60 and cl > (l + total * 0.67):
                return True
        else:
            if upper_wick / total >= 0.60 and cl < (h - total * 0.67):
                return True
    return False


def _calculate_atr_1m(candles: list, period: int = 14) -> float:
    """ATR medio dos ultimos `period` candles de 1m."""
    tr_list = []
    for i in range(1, len(candles)):
        _, h, l, _ = _parse_ohlcv(candles[i])
        _, _, _, pc = _parse_ohlcv(candles[i - 1])
        if h <= 0 or l <= 0:
            continue
        tr = max(h - l, abs(h - pc), abs(l - pc))
        tr_list.append(tr)
    if not tr_list:
        return 0.0
    return sum(tr_list[-period:]) / min(len(tr_list), period)


# ── Motor Principal ────────────────────────────────────────────────────────────

class SandboxScalpingEngine:
    """
    [V1.0] VWAP SNIPER - Motor autonomo de Scalping M1/M5.
    Roda em paralelo com o Radar de 1s e o Swing Lab M30.
    """

    def __init__(self):
        self._running         = False
        self._scan_task: Optional[asyncio.Task] = None
        self._processed: set  = set()
        self._peak_roi_cache: Dict[str, float] = {}

    # ── Start / Stop ────────────────────────────────────────────────────────────

    async def start(self):
        if self._running:
            return
        self._running   = True
        self._scan_task = asyncio.create_task(self._scan_loop())
        logger.info(
            "[VWAP-SNIPER] Motor iniciado | "
            f"Leverage={_LEVERAGE:.0f}x | Margem=${_MARGIN_PER_TRADE:.2f} | "
            f"Scan a cada {_SCAN_INTERVAL}s | Min Score={_MIN_SCORE}"
        )

    async def stop(self):
        self._running = False
        if self._scan_task:
            self._scan_task.cancel()
        logger.info("[VWAP-SNIPER] Motor parado.")

    # ── Scan Loop ───────────────────────────────────────────────────────────────

    async def _scan_loop(self):
        await asyncio.sleep(20.0)
        logger.info(f"[VWAP-SNIPER] Scan autonomo iniciado (intervalo={_SCAN_INTERVAL}s).")
        while self._running:
            try:
                await self._run_scan_cycle()
            except Exception as e:
                logger.error(f"[VWAP-SNIPER] Erro no ciclo: {e}")
                import traceback; traceback.print_exc()
            await asyncio.sleep(_SCAN_INTERVAL)

    async def _run_scan_cycle(self):
        """Ciclo completo: verifica slots, varre watchlist, abre melhor sinal."""
        from services.database_service import database_service
        from config import settings

        active_scalp = await database_service.get_sandbox_trades(active_only=True)
        if len(active_scalp) >= _MAX_SLOTS:
            logger.debug(f"[VWAP-SNIPER] Slots cheios ({len(active_scalp)}/{_MAX_SLOTS}).")
            return

        watchlist = list(getattr(settings, 'RADAR_WATCHLIST', None) or [
            "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
            "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "ADAUSDT",
            "DOTUSDT", "LTCUSDT", "UNIUSDT", "ATOMUSDT", "NEARUSDT",
        ])

        # Filtrar blocklist
        blocklist = getattr(settings, 'ASSET_BLOCKLIST', set())
        watchlist = [s for s in watchlist if s not in blocklist]

        logger.info(
            f"[VWAP-SNIPER] Scan M1/M5 | {len(watchlist)} ativos | "
            f"Slots: {len(active_scalp)}/{_MAX_SLOTS}"
        )

        sem = asyncio.Semaphore(5)

        async def _sem_analyze(sym):
            async with sem:
                return await self._analyze_symbol(sym)

        results = await asyncio.gather(
            *[_sem_analyze(s) for s in watchlist],
            return_exceptions=True
        )

        signals = [r for sym, r in zip(watchlist, results)
                   if r and not isinstance(r, Exception)]
        signals.sort(key=lambda s: s.get('score', 0), reverse=True)

        if not signals:
            logger.info("[VWAP-SNIPER] Nenhum setup M1 qualificado neste ciclo.")
            return

        logger.info(f"[VWAP-SNIPER] {len(signals)} setup(s) qualificado(s).")
        for sig in signals:
            fresh = await database_service.get_sandbox_trades(active_only=True)
            if len(fresh) >= _MAX_SLOTS:
                break
            opened = await self._try_open_trade(sig)
            if opened:
                break

    # ── Analise de Simbolo ──────────────────────────────────────────────────────

    async def _analyze_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Orquestra as 3 camadas de confirmacao do VWAP SNIPER.
        Retorna sinal dict se score >= _MIN_SCORE, senao None.
        """
        try:
            from services.okx_rest import okx_rest_service
            from services.okx_ws_public import okx_ws_public_service
            from config import settings

            norm = symbol.replace('.P', '').upper()
            
            # Filtro Blocklist
            blocklist = getattr(settings, 'ASSET_BLOCKLIST', set())
            if norm in blocklist:
                return None

            score = 0
            log   = []

            # ── CAMADA 1: EMA200 no 5m ──────────────────────────────────────────
            c5m = await okx_rest_service.get_klines(norm, interval='5', limit=220)
            if not c5m or len(c5m) < 210:
                return None

            c5m_chron  = list(reversed(c5m))
            closes_5m  = [_parse_close(c) for c in c5m_chron]
            closes_5m  = [v for v in closes_5m if v > 0]

            if len(closes_5m) < _EMA_PERIOD:
                return None

            ema200     = _calculate_ema(closes_5m, _EMA_PERIOD)
            cur_price  = closes_5m[-1]

            if ema200 <= 0:
                return None

            pct_ema = ((cur_price - ema200) / ema200) * 100.0
            if pct_ema > 0.05:
                direction, side = 'LONG', 'Buy'
            elif pct_ema < -0.05:
                direction, side = 'SHORT', 'Sell'
            else:
                return None   # ambiguo - muito proximo da EMA

            # Cooldown pós-stop
            from sqlalchemy import select, desc
            from services.database_service import SandboxTrade
            async with database_service.AsyncSessionLocal() as session:
                q = select(SandboxTrade).where(
                    SandboxTrade.symbol == norm,
                    SandboxTrade.direction == direction,
                    SandboxTrade.status != "ACTIVE"
                ).order_by(desc(SandboxTrade.closed_at)).limit(1)
                res = await session.execute(q)
                last_closed = res.scalar_one_or_none()
                if last_closed:
                    if last_closed.pnl_pct <= 0:
                        q_consec = select(SandboxTrade).where(
                            SandboxTrade.symbol == norm,
                            SandboxTrade.direction == direction
                        ).order_by(desc(SandboxTrade.opened_at)).limit(5)
                        res_consec = await session.execute(q_consec)
                        recent_trades = res_consec.scalars().all()
                        
                        consec_losses = 0
                        for rt in recent_trades:
                            if rt.status == "ACTIVE":
                                continue
                            if rt.pnl_pct <= 0:
                                consec_losses += 1
                            else:
                                break
                        
                        cooldown_secs = 900.0 if consec_losses >= 2 else 600.0  # 15min / 10min (V128: reduzido de 60/30)
                        elapsed = time.time() - (last_closed.closed_at or 0.0)
                        if elapsed < cooldown_secs:
                            logger.debug(
                                f"[VWAP-SNIPER] {norm} {direction} em cooldown pós stop-out: "
                                f"{int(cooldown_secs - elapsed)}s restantes (losses: {consec_losses})"
                            )
                            return None

            score += 30
            log.append(f"EMA200_5M:{direction}({pct_ema:+.2f}%)")

            # ── CAMADA 2: VWAP no 1m ────────────────────────────────────────────
            c1m = await okx_rest_service.get_klines(norm, interval='1', limit=390)
            if not c1m or len(c1m) < 30:
                return None

            c1m_chron = list(reversed(c1m))
            vwap      = _calculate_vwap(c1m_chron)
            if vwap <= 0:
                return None

            pct_vwap = abs((cur_price - vwap) / vwap) * 100.0
            if pct_vwap > _VWAP_TOLERANCE_PCT:
                return None   # preco longe da VWAP

            score += 25
            log.append(f"VWAP_TOUCH({pct_vwap:.3f}%)")

            # ── CAMADA 3: Stochastic RSI no 1m ──────────────────────────────────
            closes_1m = [_parse_close(c) for c in c1m_chron]
            closes_1m = [v for v in closes_1m if v > 0]

            if len(closes_1m) < 60:
                return None

            stoch = _calculate_stoch_rsi(closes_1m)
            k, d, pk, pd = stoch['k'], stoch['d'], stoch['prev_k'], stoch['prev_d']

            if direction == 'LONG':
                # Filtro Hermes: Exige cruzamento forte (K cruza D para cima) com origem em sobrevenda
                if not ((pk <= pd) and (k > d) and (pk < _STOCH_OVERSOLD or k < _STOCH_OVERSOLD)):
                    return None
            else:
                # Filtro Hermes: Exige cruzamento forte (K cruza D para baixo) com origem em sobrecompra
                if not ((pk >= pd) and (k < d) and (pk > _STOCH_OVERBOUGHT or k > _STOCH_OVERBOUGHT)):
                    return None

            score += 30
            log.append(f"STOCH_CROSS:K={k:.1f}/D={d:.1f}")

            # ── BONUS: Liquidity Sweep ───────────────────────────────────────────
            sweep = _detect_liquidity_sweep(c1m_chron, direction)
            if sweep:
                score += 15
                log.append("LIQUIDITY_SWEEP")

            if score < _MIN_SCORE:
                return None

            # ── Stop Loss baseado em ATR ─────────────────────────────────────────
            atr = _calculate_atr_1m(c1m_chron)

            # [V126] Filtro de ATR minimo: mercado sem volatilidade gera stops
            # microscopicos que sao violados por ruido, causando losses desnecessarios.
            atr_pct = (atr / cur_price) * 100.0 if cur_price > 0 else 0.0
            if atr_pct < _MIN_ATR_PCT:
                logger.debug(
                    f"[VWAP-SNIPER] {norm} ATR muito baixo ({atr_pct:.4f}% < {_MIN_ATR_PCT}%) — mercado sem volatilidade. Descartado."
                )
                return None

            max_dist = cur_price * (abs(_MAX_STOP_ROI) / (_LEVERAGE * 100.0))
            if atr > 0:
                raw_stop = cur_price - atr if direction == 'LONG' else cur_price + atr
                if direction == 'LONG':
                    stop = max(raw_stop, cur_price - max_dist)
                else:
                    stop = min(raw_stop, cur_price + max_dist)
            else:
                stop = (cur_price - max_dist) if direction == 'LONG' else (cur_price + max_dist)

            logger.info(
                f"[VWAP-SNIPER] {norm} {direction} | Score={score} | "
                f"Price={cur_price:.6f} | VWAP={vwap:.6f} | EMA200={ema200:.6f} | "
                f"K={k:.1f}/D={d:.1f} | Stop={stop:.6f} | {log}"
            )

            return {
                "symbol":            norm,
                "side":              side,
                "direction":         direction,
                "strategy":          "VWAP SNIPER",
                "strategy_class":    "VWAP SNIPER",
                "score":             score,
                "entry_price_signal": cur_price,
                "stop_price":        stop,
                "vwap":              vwap,
                "ema200_5m":         ema200,
                "stoch_k":           k,
                "stoch_d":           d,
                "liquidity_sweep":   sweep,
                "signals":           log,
                "timestamp":         time.time(),
            }

        except Exception as e:
            logger.debug(f"[VWAP-SNIPER] Erro ao analisar {symbol}: {e}")
            return None

    # ── Abertura de Trade ────────────────────────────────────────────────────────

    async def _try_open_trade(self, signal: Dict[str, Any]) -> bool:
        """Salva o trade virtual no banco (tabela sandbox_trades)."""
        try:
            from services.database_service import database_service
            from services.okx_ws_public import okx_ws_public_service

            symbol    = signal['symbol']
            direction = signal['direction']
            score     = signal['score']

            # Anti-duplicata por simbolo+direcao
            active = await database_service.get_sandbox_trades(active_only=True)
            if any(t.symbol.replace('.P', '').upper() == symbol and t.direction == direction
                   for t in active):
                return False

            # Cross-block com Swing Lab
            swing = await database_service.get_swing_trades(active_only=True)
            if any(t.symbol.replace('.P', '').upper() == symbol for t in swing):
                logger.debug(f"[VWAP-SNIPER] {symbol} no Swing Lab. Cross-block.")
                return False

            # Dedup por janela de 1 minuto
            sig_id = f"vwap_{symbol}_{direction}_{int(signal.get('timestamp', time.time()) // 60)}"
            if sig_id in self._processed:
                return False
            self._processed.add(sig_id)
            if len(self._processed) > 500:
                self._processed.clear()

            # Preco de entrada
            cur_price = float(signal.get('entry_price_signal') or 0)
            if cur_price <= 0:
                cur_price = okx_ws_public_service.get_current_price(symbol) or 0
            if cur_price <= 0:
                return False

            # Stop Loss
            stop = float(signal.get('stop_price') or 0)
            if stop <= 0:
                dist = cur_price * (abs(_MAX_STOP_ROI) / (_LEVERAGE * 100.0))
                stop = (cur_price - dist) if direction == 'LONG' else (cur_price + dist)

            trade_id = f"vwap_{symbol}_{int(time.time())}"

            trade_data = {
                "id":            trade_id,
                "symbol":        symbol,
                "strategy":      "VWAP SNIPER",
                "direction":     direction,
                "entry_price":   cur_price,
                "current_price": cur_price,
                "stop_loss":     stop,
                "target":        None,
                "max_roi":       0.0,
                "current_roi":   0.0,
                "pnl_pct":       0.0,
                "status":        "ACTIVE",
                "opened_at":     time.time(),
                "closed_at":     None,
                "flash_state": {
                    "phase":             "ESCADINHA",
                    "active_level":      "INICIAL",
                    "stop_roi":          _MAX_STOP_ROI,
                    "has_taken_partial": False,
                    "partial_roi":       0.0,
                    "history": [
                        f"VWAP SNIPER: Score={score} | "
                        f"VWAP={signal.get('vwap', 0):.6f} | "
                        f"EMA200_5m={signal.get('ema200_5m', 0):.6f} | "
                        f"K={signal.get('stoch_k', 0):.1f}/D={signal.get('stoch_d', 0):.1f} | "
                        f"Sweep={'SIM' if signal.get('liquidity_sweep') else 'NAO'}"
                    ],
                },
                "contract_meta":     None,
                "explosion_score":   score,
                "explosion_signals": signal.get("signals", []),
            }

            await database_service.save_sandbox_trade(trade_data)
            self._peak_roi_cache[trade_id] = 0.0

            logger.info(
                f"[VWAP-SNIPER] Trade aberto: {symbol} {direction} | "
                f"Entrada={cur_price:.6f} | Stop={stop:.6f} | Score={score}"
            )
            return True

        except Exception as e:
            logger.error(f"[VWAP-SNIPER] Erro ao abrir trade {signal.get('symbol')}: {e}")
            import traceback; traceback.print_exc()
            return False


# ── Instancia global ──────────────────────────────────────────────────────────
sandbox_scalping_engine = SandboxScalpingEngine()
