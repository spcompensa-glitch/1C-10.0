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

Doutrina das Extrações (step-lock de stop):
  - Break-even: +30% ROI  → SL em 0%
  - Pre-Unit1:  +60% ROI  → SL em +30%
  - Unidade 1:  +100% ROI → SL em +80% (garantido)
  - Emancipado: +150% ROI → SL em +110%
  - Unidade 2:  +200% ROI → SL em +170%
  - Unidade 3:  +300% ROI → SL em +250%

Cross-Block com SandboxService (Scalping Lab):
  - O mesmo ativo NAO pode estar ativo nas duas abas simultaneamente.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

logger = logging.getLogger("SandboxSwingService")

# Constantes padrão (sobrescritas pelo config.py se disponível)
_DEFAULT_VIRTUAL_BALANCE  = 100.0
_DEFAULT_MARGIN_PER_TRADE = 5.0
_DEFAULT_LEVERAGE         = 20.0
_DEFAULT_SCAN_INTERVAL    = 300   # 5 minutos


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
        max_swing_slots = 10
        if len(active_trades) >= max_swing_slots:
            logger.debug(f"[SWING-LAB] Slots Swing cheios ({len(active_trades)}/{max_swing_slots}). Pulando scan.")
            return


        # 2. Macro BTC para contexto de regime
        btc_dir = "LATERAL"
        btc_adx = 0.0
        try:
            from services.okx_ws_public import okx_ws_public_service
            btc_adx = float(getattr(okx_ws_public_service, "btc_adx", 0.0))
            btc_dir = "UP" if btc_adx >= 25 else "LATERAL"
        except Exception:
            pass

        # 3. Watchlist
        watchlist = getattr(settings, "RADAR_WATCHLIST", [])
        if not watchlist:
            watchlist = [
                "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "ADAUSDT", "MATICUSDT",
                "DOTUSDT", "LTCUSDT", "UNIUSDT", "ATOMUSDT", "NEARUSDT"
            ]

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
        for sig in signals:
            if len(active_trades) >= max_swing_slots:
                break
            opened = await self._try_open_swing_trade(sig)
            if opened:
                active_trades.append(opened)   # Atualiza contagem local

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
            side      = signal.get("side", "Buy")
            direction = "LONG" if side.upper() in ("BUY", "LONG") else "SHORT"
            strategy  = signal.get("strategy_class", signal.get("strategy", "VELOCITY FLOW"))
            score     = float(signal.get("score", 0))

            if not symbol:
                return None

            # --- Cross-Block: Scalping Lab ---
            scalp_active = await database_service.get_sandbox_trades(active_only=True)
            scalp_symbols = {t.symbol.replace(".P", "").upper() for t in scalp_active}
            if symbol in scalp_symbols:
                logger.debug(f"[SWING-CROSS-BLOCK] {symbol} ativo no Scalping Lab. Bloqueado.")
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

            # --- Preço de entrada ---
            current_price = float(signal.get("entry_price_signal", 0) or 0)
            if current_price <= 0:
                current_price = okx_ws_public_service.get_current_price(signal.get("symbol", symbol))
            if current_price <= 0:
                logger.warning(f"[SWING-LAB] {symbol} sem preço — setup descartado.")
                return None

            # --- Stop Loss inicial: -5% no preço = -100% ROI com 20x ---
            if direction == "LONG":
                stop_price = current_price * (1 - (50.0 / (self.leverage * 100.0)))
            else:
                stop_price = current_price * (1 + (50.0 / (self.leverage * 100.0)))

            # --- Extrai metadados do sinal ---
            indicators = signal.get("indicators", {})
            fib_zone_raw = indicators.get("fib_zone")
            fib_zone_str = None
            if fib_zone_raw and isinstance(fib_zone_raw, (list, tuple)) and len(fib_zone_raw) == 2:
                fib_zone_str = f"{fib_zone_raw[0]:.3f}-{fib_zone_raw[1]:.3f}"
            elif isinstance(fib_zone_raw, str):
                fib_zone_str = fib_zone_raw

            trade_id = f"swing_{symbol}_{int(time.time())}"

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
                    "stop_roi":     -50.0,   # Stop inicial em -50% ROI
                    "blitz_unit":   0,
                    "history":      [],
                    "mirror_mode":  "ON" if self.mirror_mode_on else "OFF",
                    "scan_source":  "AUTONOMOUS",
                },
                "contract_meta": signal.get("contract_meta"),
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
            }

            await database_service.save_swing_trade(trade_data)
            self._peak_roi_cache[trade_id] = 0.0

            logger.info(
                f"[SWING-LAB] ✅ Trade aberto: {symbol} {direction} | "
                f"Estratégia: {strategy} | Score: {score:.0f} | "
                f"Entrada: {current_price:.6f} | Stop: {stop_price:.6f} | "
                f"Margem virtual: ${self.margin_per_trade:.2f}"
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
                strategy_class=strategy,
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
