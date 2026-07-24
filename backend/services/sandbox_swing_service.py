# -*- coding: utf-8 -*-
"""
[Swing Lab] SandboxSwingService — V2.0 (Motor Primário)
=========================================================
V2.0: Inversão completa de arquitetura.

ANTES (V1.0): Espelhava passivamente as ordens REAIS do BlitzSniperAgent.
AGORA (V2.0): MOTOR PRIMÁRIO — detecta setups M30 de forma autônoma e:
  1. Abre posições VIRTUAIS no Swing Lab (banca de $100)
  2. Opcionalmente espelha na OKX REAL via SWING_MIRROR_MODE

Fluxo V2.0:
  SandboxSwingService._scan_loop() detecta setup
    → _try_open_swing_trade() abre virtual
      → SE SWING_MIRROR_MODE=ON: chama BankrollManager para abrir na OKX real
      → Conta real é OPCIONAL — Sandbox continua mesmo se pausada

Estratégias suportadas (3 mães + sub-classes):
  - ALPHA SHIELD: DVAP, MOLA, FAS, LRT
  - VELOCITY FLOW: TREND, ABCD, 1-2-3
  - DECOR SHADOW: DECOR, DECOR_HUNTER

Indicadores absorvidos do BLITZ_30M:
  - Fibonacci Golden Zone (0.618–0.786)
  - Price Action patterns (Wick Reclaim, Engulf, Sweep & Reclaim)

[V130] Correção Estrutural do R:R (2026-07-17):
  - Diagnóstico: R:R de 0.46 (avg win 3.6% vs avg loss 8.0%).
    Causa: leverage 50x + stop -5% ROI = 0.1% de preço.
    Breakeven em +10% ROI criava gap de 15% entre stop e proteção.
  - Solução V130:
    1. Leverage 50x → 10x (stop -5% = 0.5% de preço, 5x mais espaço)
    2. Escadinha: breakeven +10% → +5%, gap eliminado (R:R 1:1 na entrada)
    3. Position sizing dinâmico por score do sinal (score < 70 = 30% da margem)

Doutrina das Extrações V130 (step-lock de stop):
  - Break-even: +5% ROI   → SL em 0%   (R:R 1:1 na entrada)
  - Proteção Parcial: +12% ROI → SL em +3%
  - Pre-Unit1:        +40% ROI → SL em +20%
  - Unidade 1:        +80% ROI → SL em +55% (garantido)
  - Emancipado:      +120% ROI → SL em +85%
  - Unidade 2:       +160% ROI → SL em +130%
  - Unidade 3:       +250% ROI → SL em +200%

[V130] Filtros adicionais:
  - Regime filter: bearish → so SHORT; bullish → so LONG
  - Hour filter: pausa 14:00-15:00 UTC (pico de losses)
  - Dynamic blacklist: auto-bloqueio apos 3+ trades com WR<20%
  - 5m breakout: score bonus (+10/+5/0) em vez de gate duro

Cross-Block com SandboxService (Scalping Lab):
  - O mesmo ativo NAO pode estar ativo nas duas abas simultaneamente.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

logger = logging.getLogger("SandboxSwingService")

# [V130-FIX] Constantes padrão (sobrescritas pelo config.py se disponível)
# _DEFAULT_LEVERAGE reduzido de 50x → 10x para:
#   - Aumentar o stop em termos de preço (0.1% → 0.5% com -5% ROI)
#   - Melhorar R:R ratio (projetado: 0.46 → ~1.5)
_DEFAULT_VIRTUAL_BALANCE  = 100.0
_DEFAULT_MARGIN_PER_TRADE = 5.0
_DEFAULT_LEVERAGE         = 50.0   # [V132-SWING-2H] Alavancagem forçada a 50x
_DEFAULT_SCAN_INTERVAL    = 1800   # [V132-SWING-2H] Intervalo de scan de 30min para coincidir com 2H


def _get_settings():
    """Lê settings de forma lazy para evitar import circular."""
    try:
        from config import settings
        return settings
    except Exception:
        return None


class SandboxSwingService:
    """
    [V2.0] Motor primário do Swing Lab.
    Detecta setups M30 de forma autônoma e gerencia posições virtuais.
    """

    def __init__(self):
        self._flash_loop_task: Optional[asyncio.Task] = None
        self._scan_loop_task: Optional[asyncio.Task] = None
        self._running = False
        self._peak_roi_cache: Dict[str, float] = {}   # { trade_id: max_roi }
        self._processed_signals: set = set()           # dedup de IDs de sinal
        # [V128] Blacklist dinâmica por performance
        self._pair_stats: Dict[str, Dict] = {}         # { symbol: {wins, losses, total} }
        self._dynamic_blocklist: set = set()            # auto-bloqueio após WR<20% em 3+ trades

    # =========================================================================
    # PROPRIEDADES DINÂMICAS (lidas do config em runtime)
    # =========================================================================

    @property
    def virtual_balance(self) -> float:
        s = _get_settings()
        return float(getattr(s, "SWING_VIRTUAL_BALANCE", _DEFAULT_VIRTUAL_BALANCE)) if s else _DEFAULT_VIRTUAL_BALANCE

    @property
    def margin_per_trade(self) -> float:
        s = _get_settings()
        return float(getattr(s, "SWING_MARGIN_PER_TRADE", _DEFAULT_MARGIN_PER_TRADE)) if s else _DEFAULT_MARGIN_PER_TRADE

    @property
    def leverage(self) -> float:
        s = _get_settings()
        return float(getattr(s, "SWING_LEVERAGE", _DEFAULT_LEVERAGE)) if s else _DEFAULT_LEVERAGE

    @property
    def scan_interval(self) -> int:
        s = _get_settings()
        return int(getattr(s, "SWING_SCAN_INTERVAL", _DEFAULT_SCAN_INTERVAL)) if s else _DEFAULT_SCAN_INTERVAL

    @property
    def mirror_mode_on(self) -> bool:
        """Retorna True se SWING_MIRROR_MODE=ON (espelhar na OKX real)."""
        # Prioriza variável de ambiente para refletir alterações em runtime imediatamente
        import os
        env_mode = os.environ.get("SWING_MIRROR_MODE")
        if env_mode is not None:
            return env_mode.strip().upper() == "ON"
        s = _get_settings()
        if not s:
            return False
        return str(getattr(s, "SWING_MIRROR_MODE", "OFF")).upper() == "ON"

    # =========================================================================
    # START / STOP
    # =========================================================================

    async def start(self):
        """Inicia o motor primário de scan autônomo do Swing Lab."""
        if self._running:
            return
        self._running = True

        # Scan loop (detecta setups M30 a cada SWING_SCAN_INTERVAL)
        self._scan_loop_task = asyncio.create_task(self._scan_loop())

        mirror_status = "ON (espelhando na OKX real)" if self.mirror_mode_on else "OFF (apenas virtual)"
        logger.info(
            f"[SWING-LAB V2.0] Motor primário iniciado | "
            f"Leverage={self.leverage:.0f}x | Margem=${self.margin_per_trade:.2f} | "
            f"Banca virtual=${self.virtual_balance:.0f} | Mirror={mirror_status}"
        )

    async def stop(self):
        self._running = False
        for task in (self._flash_loop_task, self._scan_loop_task):
            if task:
                task.cancel()
        logger.info("[SWING-LAB V2.0] SandboxSwingService parado.")

    # =========================================================================
    # SCAN LOOP — motor primário de detecção de setups
    # =========================================================================

    async def _scan_loop(self):
        """
        [V2.0] Loop autônomo que varre a watchlist a cada SWING_SCAN_INTERVAL segundos
        buscando setups M30 com as 3 estratégias (ALPHA SHIELD, VELOCITY FLOW, DECOR SHADOW).
        """
        await asyncio.sleep(10.0)   # Aguarda o sistema inicializar completamente
        logger.info(f"[SWING-LAB] Scan autônomo iniciado (intervalo={self.scan_interval}s).")

        while self._running:
            try:
                await self._run_scan_cycle()
            except Exception as e:
                logger.error(f"[SWING-LAB] Erro no ciclo de scan: {e}")
                import traceback; traceback.print_exc()
            await asyncio.sleep(self.scan_interval)

    async def _run_scan_cycle(self):
        """Executa um ciclo de scan: obtém macro BTC, varre watchlist, processa sinais."""
        from services.signal_generator import signal_generator
        from config import settings

        # 1. Capacidade: não abrir mais trades se limite de 10 slots de Swing ativo for alcançado
        from services.database_service import database_service
        active_trades = await database_service.get_swing_trades(active_only=True)
        # [V128] Banca $10.000 | 15 slots Swing (2 simultâneos com risco, fila de 13) | $200/trade
        max_swing_slots = 15

        if len(active_trades) >= max_swing_slots:
            logger.debug(f"[SWING-LAB] Slots Swing cheios ({len(active_trades)}/{max_swing_slots}). Pulando scan.")
            return

        # 1.5. Regra Risco Zero (Zero-Risk Stacking) - 2 Slots de Risco
        # Permite no máximo 2 posições simultâneas com risco de mesa.
        trades_with_risk = 0
        for t in active_trades:
            is_long = t.direction.upper() in ("LONG", "BUY")
            if is_long:
                if t.stop_loss is None or t.stop_loss < t.entry_price:
                    trades_with_risk += 1
            else:
                if t.stop_loss is None or t.stop_loss > t.entry_price:
                    trades_with_risk += 1

        allowed_new_risk_slots = 2 - trades_with_risk
        if allowed_new_risk_slots <= 0:
            logger.info(f"[SWING-LAB] O limite de 2 ordens com risco simultâneo foi atingido. Aguardando pelo menos uma atingir risco zero (break-even).")
            return



        # 2. Macro BTC para contexto de regime
        btc_dir = "LATERAL"
        btc_adx = 0.0
        try:
            from services.okx_ws_public import okx_ws_public_service
            btc_adx = float(getattr(okx_ws_public_service, "btc_adx", 0.0))
            # [V133-SWING] ADX mínimo elevado de 25 para 30 para Swing Lab
            # Swing opera em 2H, precisa de tendência mais forte para confirmar
            btc_dir = "UP" if btc_adx >= 30 else "LATERAL"

            # [V128] Detectar downtrend BTC: SMA8 < SMA21 no M30 = "DOWN"
            try:
                btc_ohlcv = await okx_ws_public_service.get_ohlcv("BTCUSDT", "M30", limit=30)
                if btc_ohlcv and len(btc_ohlcv) >= 21:
                    closes = [c["c"] for c in btc_ohlcv]
                    sma8 = sum(closes[-8:]) / 8.0
                    sma21 = sum(closes[-21:]) / 21.0
                    if sma8 < sma21:
                        btc_dir = "DOWN"
            except Exception:
                pass
        except Exception:
            pass

        # [V128] Filtro de horário — evitar 14:00-15:00 UTC (pico de losses)
        from datetime import datetime, timezone
        current_hour = datetime.now(timezone.utc).hour
        if current_hour in (14, 15):
            logger.info(f"[SWING-LAB] Scan pausado (hora {current_hour}:00 UTC — alto risco historico)")
            return

        # [V128] Regime filter: bearish → so SHORT; bullish → so LONG; lateral → ambos
        is_bearish = btc_dir == "DOWN"
        is_bullish = btc_dir == "UP"

        # 3. Watchlist
        watchlist = getattr(settings, "RADAR_WATCHLIST", [])
        if not watchlist:
            watchlist = [
                "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "ADAUSDT", "MATICUSDT",
                "DOTUSDT", "LTCUSDT", "UNIUSDT", "ATOMUSDT", "NEARUSDT"
            ]

        # Filtro Blocklist
        blocklist = getattr(settings, 'ASSET_BLOCKLIST', set())
        watchlist = [s for s in watchlist if s not in blocklist]

        # [V128] Filtro Blocklist dinâmica (auto-bloqueio por performance)
        watchlist = [s for s in watchlist if s not in self._dynamic_blocklist]

        logger.info(
            f"[SWING-LAB] Scan M30 | {len(watchlist)} ativos | "
            f"BTC: {btc_dir} (ADX={btc_adx:.1f}) | "
            f"Slots: {len(active_trades)}/{max_swing_slots} | "
            f"Mirror: {'ON' if self.mirror_mode_on else 'OFF'}"
        )

        # 4. Scan com as 3 estratégias
        signals = await signal_generator.scan_m30_swing_watchlist(watchlist, btc_dir, btc_adx)

        if not signals:
            logger.info("[SWING-LAB] Nenhum setup M30 qualificado neste ciclo.")
            return

        logger.info(f"[SWING-LAB] {len(signals)} setup(s) qualificado(s). Processando...")
        opened_in_cycle = 0
        for sig in signals:
            if len(active_trades) >= max_swing_slots:
                break
            if opened_in_cycle >= allowed_new_risk_slots:
                break

            # [V128] Filtro de direção por regime
            sig_side = sig.get("side", "Buy")
            sig_dir = "LONG" if sig_side.upper() in ("BUY", "LONG") else "SHORT"
            sig_score = float(sig.get("score", 0))

            if is_bearish and sig_dir == "LONG":
                logger.info(f"[SWING-LAB] {sig.get('symbol')} LONG descartado (regime bearish)")
                continue
            if is_bullish and sig_dir == "SHORT":
                logger.info(f"[SWING-LAB] {sig.get('symbol')} SHORT descartado (regime bullish)")
                continue

            # [V129] Regra para Mercado LATERAL: Exigir score >= 80 e volume/gás >= 1.5x
            if btc_dir == "LATERAL":
                indicators = sig.get("indicators", {}) or {}
                vol_ratio = float(indicators.get("volume_ratio", 0.0))
                if sig_score < 80:
                    logger.info(f"[SWING-LAB] {sig.get('symbol')} {sig_dir} descartado em LATERAL por score baixo ({sig_score:.0f} < 80)")
                    continue
                if vol_ratio < 1.5:
                    logger.info(f"[SWING-LAB] {sig.get('symbol')} {sig_dir} descartado em LATERAL por falta de volume/gás (vol_ratio={vol_ratio:.2f} < 1.5x)")
                    continue

            opened = await self._try_open_swing_trade(sig)
            if opened:
                active_trades.append(opened)   # Atualiza contagem local
                opened_in_cycle += 1
                logger.info(f"[SWING-LAB] Zero-Risk Stacking: Nova ordem aberta ({opened_in_cycle}/{allowed_new_risk_slots} de risco disponíveis neste ciclo).")
                
                if opened_in_cycle >= allowed_new_risk_slots:
                    logger.info(f"[SWING-LAB] Capacidade de risco preenchida. Interrompendo abertura de mais ordens.")
                    break

        # [V128] Atualizar stats de pares com trades fechados recentemente
        try:
            from services.database_service import database_service
            all_trades = await database_service.get_swing_trades(active_only=False)
            for t in all_trades:
                if t.status != "ACTIVE" and hasattr(t, 'pnl_pct') and t.pnl_pct is not None:
                    pnl_usd = t.pnl_pct / 100.0 * self.margin_per_trade
                    self._update_pair_stats(t.symbol, pnl_usd)
        except Exception:
            pass

    # =========================================================================
    # ABERTURA DE TRADE — Motor primário com mirror opcional
    # =========================================================================

    async def _try_open_swing_trade(self, signal: Dict[str, Any]) -> Optional[Any]:
        """
        [V2.0] Tenta abrir um trade virtual no Swing Lab.
        Se SWING_MIRROR_MODE=ON, também espelha na OKX real.

        Returns:
            O objeto do trade se aberto com sucesso, None caso contrário.
        """
        try:
            from services.database_service import database_service
            from services.okx_ws_public import okx_ws_public_service

            symbol    = (signal.get("symbol") or "").replace(".P", "").upper()
            
            # Filtro Blocklist
            s = _get_settings()
            blocklist = getattr(s, 'ASSET_BLOCKLIST', set()) if s else set()
            if symbol in blocklist:
                return None

            side      = signal.get("side", "Buy")
            direction = "LONG" if side.upper() in ("BUY", "LONG") else "SHORT"
            strategy  = signal.get("strategy_class", signal.get("strategy", "VELOCITY FLOW"))
            score     = float(signal.get("score", 0))

            if not symbol:
                return None

            # Cooldown pós-stop
            from sqlalchemy import select, desc
            from services.database_service import SandboxSwingTrade
            async with database_service.AsyncSessionLocal() as session:
                q = select(SandboxSwingTrade).where(
                    SandboxSwingTrade.symbol == symbol,
                    SandboxSwingTrade.direction == direction,
                    SandboxSwingTrade.status != "ACTIVE"
                ).order_by(desc(SandboxSwingTrade.closed_at)).limit(1)
                res = await session.execute(q)
                last_closed = res.scalar_one_or_none()
                if last_closed:
                    if last_closed.pnl_pct <= 0:
                        q_consec = select(SandboxSwingTrade).where(
                            SandboxSwingTrade.symbol == symbol,
                            SandboxSwingTrade.direction == direction
                        ).order_by(desc(SandboxSwingTrade.opened_at)).limit(5)
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
                        
                        cooldown_secs = 3600.0 if consec_losses >= 2 else 1800.0
                        elapsed = time.time() - (last_closed.closed_at or 0.0)
                        if elapsed < cooldown_secs:
                            logger.info(
                                f"[SWING-LAB] {symbol} {direction} em cooldown pós stop-out: "
                                f"{int(cooldown_secs - elapsed)}s restantes (losses: {consec_losses})"
                            )
                            return None

            # --- Cross-Block: Scalping Lab ---
            scalp_active = await database_service.get_sandbox_trades(active_only=True)
            scalp_symbols = {t.symbol.replace(".P", "").upper() for t in scalp_active}
            if symbol in scalp_symbols:
                logger.debug(f"[SWING-CROSS-BLOCK] {symbol} ativo no Scalping Lab. Bloqueado.")
                return None

            # [V128] Filtro volume mínimo — rejeita sinais com volume < 0.5x da média
            vol_ratio = float(signal.get("indicators", {}).get("volume_ratio", 0) or 0)
            if vol_ratio < 0.5:
                logger.info(f"[SWING-LAB] {symbol} {direction} descartado: volume {vol_ratio:.2f}x < 0.5x mínimo")
                return None

            # --- Anti-duplicata ---
            swing_active = await database_service.get_swing_trades(active_only=True)
            already = any(
                t.symbol.replace(".P", "").upper() == symbol and t.direction == direction
                for t in swing_active
            )
            if already:
                logger.debug(f"[SWING-LAB] {symbol} {direction} já ativo no Swing Lab.")
                return None

            # --- Dedup por signal ID ---
            sig_id = signal.get("id") or f"{symbol}_{direction}_{int(time.time() // 300)}"
            if sig_id in self._processed_signals:
                return None
            self._processed_signals.add(sig_id)
            if len(self._processed_signals) > 1000:
                self._processed_signals.clear()

            # --- [V127.1] Confirmação 5m: filtro SOFT (bonus de score) ---
            breakout_bonus = await self._get_5m_breakout_score(symbol, direction)
            score += breakout_bonus
            if breakout_bonus >= 10:
                logger.info(f"[SWING-LAB] {symbol} {direction} 5m breakout confirmado (direção+volume). Bonus +{breakout_bonus}")
            elif breakout_bonus > 0:
                logger.info(f"[SWING-LAB] {symbol} {direction} 5m parcial (direção OU volume). Bonus +{breakout_bonus}")
            else:
                logger.info(f"[SWING-LAB] {symbol} {direction} 5m sem confirmação. Score sem bonus.")

            # --- Preço de entrada ---
            current_price = float(signal.get("entry_price_signal", 0) or 0)
            if current_price <= 0:
                current_price = okx_ws_public_service.get_current_price(signal.get("symbol", symbol))
            if current_price <= 0:
                logger.warning(f"[SWING-LAB] {symbol} sem preço — setup descartado.")
                return None

            # [V133-SWING] Stop Loss inicial reduzido de -35% para -20% ROI (0.4% no preço com 50x)
            # Trade-off: menos runway (0.4% vs 0.7%), mas R:R muito melhor (1:2+ vs 1:0.28)
            stop_roi_target = 20.0
            if direction == "LONG":
                stop_price = current_price * (1 - (stop_roi_target / (self.leverage * 100.0)))
            else:
                stop_price = current_price * (1 + (stop_roi_target / (self.leverage * 100.0)))

            # --- Extrai metadados do sinal ---
            indicators = signal.get("indicators", {})
            fib_zone_raw = indicators.get("fib_zone")
            fib_zone_str = None
            if fib_zone_raw and isinstance(fib_zone_raw, (list, tuple)) and len(fib_zone_raw) == 2:
                fib_zone_str = f"{fib_zone_raw[0]:.3f}-{fib_zone_raw[1]:.3f}"
            elif isinstance(fib_zone_raw, str):
                fib_zone_str = fib_zone_raw

            trade_id = f"swing_{symbol}_{int(time.time())}"

            # [V130-FIX] Position sizing dinâmico por score do sinal (Swing Lab).
            # Base: 2% da banca total, com multiplicador por convicção:
            #   score >= 85 → 100% da margem base
            #   score 70-84 →  60% da margem base
            #   score < 70 →  30% da margem base (score mínimo é ~65)
            current_balance = await database_service.get_sandbox_unified_balance()
            base_margin = round(current_balance * 0.02, 2)
            if score >= 85:
                score_mult = 1.0
            elif score >= 70:
                score_mult = 0.60
            else:
                score_mult = 0.30
            dynamic_margin = round(base_margin * score_mult, 2)

            contract_meta = signal.get("contract_meta") or {}
            if not isinstance(contract_meta, dict):
                contract_meta = {}
            contract_meta["margin"] = dynamic_margin
            logger.info(
                f"[V130-POSITION-SIZING] Swing {symbol} {strategy} score={score} "
                f"mult={score_mult:.2f} margem=${dynamic_margin:.2f} "
                f"(base=${base_margin:.2f})"
            )

            trade_data = {
                "id":            trade_id,
                "symbol":        symbol,
                "strategy":      strategy,
                "direction":     direction,
                "entry_price":   current_price,
                "current_price": current_price,
                "stop_loss":     stop_price,
                "target":        None,
                "max_roi":       0.0,
                "current_roi":   0.0,
                "pnl_pct":       0.0,
                "status":        "ACTIVE",
                "opened_at":     time.time(),
                "closed_at":     None,
                "flash_state": {
                    "phase":        "SWING_V2",
                    "active_level": "INICIAL",
                    "stop_roi":     -abs(stop_roi_target),
                    "blitz_unit":   0,
                    "history":      [f"[INICIO] Margem Dinâmica alocada: ${dynamic_margin:.2f}"],
                    "mirror_mode":  "ON" if self.mirror_mode_on else "OFF",
                    "scan_source":  "AUTONOMOUS",
                    "stop_method":  "CONFIG",
                    "stop_roi_target": stop_roi_target,
                },
                "contract_meta": contract_meta,
                "blitz_score":   score,
                "fib_zone":      fib_zone_str,
                "sma_cross":     str(indicators.get("sma_cross", indicators.get("sma_pattern", "NONE"))),
                "cvd_value":     float(indicators.get("cvd", 0)),
                "volume_ratio":  float(indicators.get("volume_ratio", 0)),
                "pa_pattern":    str(indicators.get("pa_pattern", indicators.get("pattern", ""))),
                "reasons":       signal.get("reasons", []),
                "blitz_unit":    0,
                "explosion_score": score,
                "explosion_signals": signal.get("reasons", []),
                "stop_method":   "CONFIG",
                "stop_roi_target": stop_roi_target,
            }

            await database_service.save_swing_trade(trade_data)
            self._peak_roi_cache[trade_id] = 0.0

            logger.info(
                f"[SWING-LAB] ✅ Trade aberto: {symbol} {direction} | "
                f"Estratégia: {strategy} | Score: {score:.0f} | "
                f"Entrada: {current_price:.6f} | Stop: {stop_price:.6f} | "
                f"Stop ROI: {stop_roi_target:.1f}% | "
                f"Margem virtual: ${dynamic_margin:.2f}"
            )

            # --- MIRROR: espelhar na OKX real se SWING_MIRROR_MODE=ON ---
            if self.mirror_mode_on:
                await self._mirror_to_real_account(signal, current_price, stop_price, trade_id)

            # Retorna um objeto simples para atualizar contagem local
            class _TradePlaceholder:
                def __init__(self, tid, sym, dirn):
                    self.id, self.symbol, self.direction = tid, sym, dirn

            return _TradePlaceholder(trade_id, symbol, direction)

        except Exception as e:
            logger.error(f"[SWING-LAB] Erro ao abrir trade para {signal.get('symbol')}: {e}")
            import traceback; traceback.print_exc()
            return None

    async def _get_5m_breakout_score(self, symbol: str, direction: str) -> int:
        """
        [V127.1] Filtro SOFT: retorna bonus de score baseado na confirmação 5m.
        +10 se candle 5m fecha na direção E volume >= 1.5x média.
        +5 se apenas um dos critérios é atendido.
        0 se nenhum (não bloqueia, só não dá bonus).
        """
        try:
            from services.okx_rest import okx_rest_service
            klines = await okx_rest_service.get_klines(symbol=symbol, interval="5", limit=12)
            if not klines or len(klines) < 6:
                return 5  # Sem dados → bonus neutro

            candles = list(reversed(klines))
            closes = [float(c[4]) for c in candles]
            volumes = [float(c[5]) if len(c) > 5 else 0.0 for c in candles]

            last_close = closes[-1]
            prev_close = closes[-2]
            last_vol = volumes[-1]
            avg_vol = sum(volumes[-11:-1]) / 10.0 if len(volumes) >= 11 else 1.0

            volume_ok = last_vol >= avg_vol * 1.5

            if direction == "LONG":
                direction_ok = last_close > prev_close
            else:
                direction_ok = last_close < prev_close

            if direction_ok and volume_ok:
                return 10
            elif direction_ok or volume_ok:
                return 5
            return 0

        except Exception as e:
            logger.warning(f"[SWING-LAB] Erro ao checar 5m breakout para {symbol}: {e}")
            return 5  # Em caso de erro, bonus neutro

    def _update_pair_stats(self, symbol: str, pnl: float):
        """[V128] Rastreia performance por par. Auto-bloqueia apos 3+ trades com WR<20%."""
        if symbol not in self._pair_stats:
            self._pair_stats[symbol] = {"wins": 0, "losses": 0, "total": 0}
        stats = self._pair_stats[symbol]
        stats["total"] += 1
        if pnl > 0:
            stats["wins"] += 1
        elif pnl < 0:
            stats["losses"] += 1
        # Auto-blocklist: 3+ trades e WR < 20%
        if stats["total"] >= 3 and stats["wins"] / stats["total"] < 0.20:
            if symbol not in self._dynamic_blocklist:
                self._dynamic_blocklist.add(symbol)
                logger.warning(
                    f"[SWING-LAB] {symbol} AUTO-BLOQUEADO "
                    f"(WR {stats['wins']}/{stats['total']} = {stats['wins']/stats['total']*100:.0f}%)"
                )

    async def _mirror_to_real_account(
        self,
        signal: Dict[str, Any],
        entry_price: float,
        stop_price: float,
        swing_trade_id: str,
    ):
        """
        [V2.0] Espelha a posição virtual na OKX real.
        Chamado APENAS se SWING_MIRROR_MODE=ON.
        Falha silenciosa — o trade virtual já foi aberto com sucesso.
        """
        try:
            from services.bankroll import bankroll_manager

            symbol = signal.get("symbol", "")
            side   = signal.get("side", "Buy")
            strategy = signal.get("strategy_class", signal.get("strategy", "VELOCITY FLOW"))

            # Enriquecer o sinal para o Captain/Bankroll
            mirror_signal = {
                **signal,
                "symbol": symbol,
                "side":   side,
                "score":  signal.get("score", 70),
                "layer":  "SWING_MIRROR",
                "is_blitz": True,
                "slot_type": "BLITZ_30M",
                "swing_mirror_id": swing_trade_id,  # Liga o trade real ao virtual
                "strategy_class": strategy,
                "leverage": int(self.leverage),
            }

            logger.info(
                f"[SWING-MIRROR] 🔗 Espelhando {symbol} {side} na OKX real | "
                f"Mirror ID: {swing_trade_id}"
            )

            result = await bankroll_manager.open_position(
                symbol=symbol,
                side=side,
                signal_data=mirror_signal,
                slot_type="BLITZ_30M",
            )

            if result:
                logger.info(f"[SWING-MIRROR] ✅ Espelhado na OKX real com sucesso: {symbol}")
            else:
                logger.warning(
                    f"[SWING-MIRROR] ⚠️ Espelhamento falhou para {symbol} (sem slots ou bloqueado). "
                    f"Trade virtual continua ativo normalmente."
                )

        except Exception as e:
            logger.warning(
                f"[SWING-MIRROR] ⚠️ Erro ao espelhar {signal.get('symbol')} na OKX real: {e}. "
                f"Trade virtual NÃO foi afetado."
            )

    # =========================================================================
    # MÉTODO LEGACY — mantido para compatibilidade (não usado no V2.0)
    # =========================================================================

    async def on_blitz_signal(self, signal: Dict[str, Any], entry_price: float, stop_price: float):
        """
        [DEPRECATED V2.0] Este método era chamado pelo BankrollManager no fluxo invertido (V1.0).
        No V2.0, o fluxo foi invertido: o SandboxSwingService é o motor primário.
        Mantido por compatibilidade — redireciona para _try_open_swing_trade.
        """
        logger.warning(
            "[SWING-LAB] on_blitz_signal() chamado (fluxo legado V1.0). "
            "Considere remover esta chamada — use o scan autônomo do V2.0."
        )
        # [V125] _flash_loop e _update_swing_trade removidos.
        # O monitoramento de stops virtuais do Swing Lab é feito centralizadamente pelo FlashAgent.
        enriched = {**signal, "entry_price_signal": entry_price}
        await self._try_open_swing_trade(enriched)

    # =========================================================================
    # STATUS — para APIs e frontend
    # =========================================================================

    async def get_status(self) -> Dict[str, Any]:
        """Retorna status atual do motor primário para APIs."""
        try:
            from services.database_service import database_service
            active = await database_service.get_swing_trades(active_only=True)
            all_trades = await database_service.get_swing_trades(active_only=False)
            closed = [t for t in all_trades if t.status != "ACTIVE"]
            wins   = [t for t in closed if t.pnl_pct > 0]
            losses = [t for t in closed if t.pnl_pct <= 0]
            total_pnl = sum(t.pnl_pct / 100.0 * self.margin_per_trade for t in closed)

            return {
                "running":        self._running,
                "mirror_mode":    "ON" if self.mirror_mode_on else "OFF",
                "leverage":       self.leverage,
                "margin_per_trade": self.margin_per_trade,
                "virtual_balance": self.virtual_balance,
                "scan_interval":  self.scan_interval,
                "active_trades":  len(active),
                "total_trades":   len(all_trades),
                "wins":           len(wins),
                "losses":         len(losses),
                "win_rate":       round(len(wins) / len(closed) * 100, 1) if closed else 0,
                "total_pnl_usd":  round(total_pnl, 2),
                "strategies": list({t.strategy for t in all_trades if t.strategy}),
            }
        except Exception as e:
            logger.error(f"[SWING-LAB] Erro ao obter status: {e}")
            return {"running": self._running, "error": str(e)}

    async def set_mirror_mode(self, mode: str):
        """
        Altera o SWING_MIRROR_MODE em runtime sem reiniciar o servidor.
        Persiste na variável de ambiente e no settings.
        """
        import os
        normalized = mode.strip().upper()
        if normalized not in ("ON", "OFF"):
            raise ValueError(f"SWING_MIRROR_MODE deve ser ON ou OFF, recebido: {mode}")
        os.environ["SWING_MIRROR_MODE"] = normalized
        try:
            from config import settings
            settings.__dict__["SWING_MIRROR_MODE"] = normalized
        except Exception:
            pass
        logger.info(
            f"[SWING-LAB] Mirror Mode alterado para {normalized} em runtime. "
            f"{'Ordens swing serão espelhadas na OKX real.' if normalized == 'ON' else 'Apenas posições virtuais serão abertas.'}"
        )


# Instância global
sandbox_swing_service = SandboxSwingService()
