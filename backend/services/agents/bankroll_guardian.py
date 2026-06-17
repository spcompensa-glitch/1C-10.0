# -*- coding: utf-8 -*-
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import settings
from services.database_service import database_service

logger = logging.getLogger("BankrollGuardian")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _normalize_symbol(symbol: Optional[str]) -> str:
    return (symbol or "").upper().replace(".P", "").replace("-", "")


class BankrollGuardian:
    """
    Guardiao preventivo da banca.

    Ele nao substitui o Flash nem o antigo PortfolioGuardian/Facao. O papel aqui e
    impedir vazamento de banca antes da ordem abrir, usando saude da sessao,
    historico por par, slots ativos e moonbags.
    """

    def __init__(self):
        self.agent_id = "bankroll-guardian"
        self.name = "Guardiao da Banca"
        self.peak_equity = 0.0
        self.protected_profit_peak = 0.0
        self.last_report: Dict[str, Any] = {}
        self.last_report_at = 0.0

    def reset_runtime_state(self) -> Dict[str, Any]:
        snapshot = {
            "peak_equity": self.peak_equity,
            "protected_profit_peak": self.protected_profit_peak,
            "last_report_at": self.last_report_at,
        }
        self.peak_equity = 0.0
        self.protected_profit_peak = 0.0
        self.last_report = {}
        self.last_report_at = 0.0
        return snapshot

    async def _get_market_data(self) -> Dict[str, Any]:
        """
        [V111.2] Obtém regime de mercado (ADX e direção do BTC)
        para aplicar filtros de entrada.
        Retorna: { adx, direction, is_ranging, is_trending, is_strong_trend }
        """
        result = {
            "adx": 0.0,
            "direction": "LATERAL",
            "is_ranging": True,
            "is_trending": False,
            "is_strong_trend": False,
        }
        try:
            from services.okx_ws_public import okx_ws_public_service
            adx = getattr(okx_ws_public_service, 'btc_adx', 0.0)
            var_1h = getattr(okx_ws_public_service, 'btc_variation_1h', 0.0)
            var_15m = getattr(okx_ws_public_service, 'btc_variation_15m', 0.0)

            result["adx"] = adx
            result["is_ranging"] = (adx < settings.ADX_TRENDING_THRESHOLD)
            result["is_trending"] = (adx >= settings.ADX_TRENDING_THRESHOLD)
            result["is_strong_trend"] = (adx >= settings.ADX_STRONG_TREND_THRESHOLD)

            # Determinar direção do BTC com confluência 15m + 1h
            if adx >= 22:
                if var_15m > 0 and var_1h > 0:
                    result["direction"] = "UP"
                elif var_15m < 0 and var_1h < 0:
                    result["direction"] = "DOWN"
                elif adx >= settings.ADX_TRENDING_THRESHOLD:
                    # ADX >= 25: fallback para 1h se 15m/1h discordam
                    result["direction"] = "UP" if var_1h > 0 else "DOWN"
                else:
                    # ADX 22-25 com direção inconclusiva: usar 1h como tiebreaker
                    result["direction"] = "UP" if var_1h > 0.1 else ("DOWN" if var_1h < -0.1 else "LATERAL")
        except Exception:
            pass
        return result

    async def _get_banca_status(self) -> Dict[str, Any]:
        try:
            from services.firebase_service import firebase_service
            status = await firebase_service.get_banca_status(username="admin")
            if status and _safe_float(status.get("saldo_total"), 0.0) > 0:
                return status
        except Exception:
            pass

        try:
            return await database_service.get_banca_status()
        except Exception as exc:
            logger.warning(f"[BANKROLL-GUARDIAN] Falha ao ler banca: {exc}")
            return {}

    async def _get_slots(self) -> List[Dict[str, Any]]:
        try:
            slots = await database_service.get_active_slots()
            return [s for s in slots if isinstance(s, dict)]
        except Exception as exc:
            logger.warning(f"[BANKROLL-GUARDIAN] Falha ao ler slots: {exc}")
            return []

    async def _get_moonbags(self) -> List[Dict[str, Any]]:
        try:
            moonbags = await database_service.get_moonbags()
            return [m for m in moonbags if isinstance(m, dict)]
        except Exception as exc:
            logger.warning(f"[BANKROLL-GUARDIAN] Falha ao ler moonbags: {exc}")
            return []

    async def _get_history(self, limit: int = 120) -> List[Dict[str, Any]]:
        try:
            history = await database_service.get_trade_history(limit=limit)
            return [h for h in history if isinstance(h, dict)]
        except Exception as exc:
            logger.warning(f"[BANKROLL-GUARDIAN] Falha ao ler historico: {exc}")
            return []

    def _timestamp_seconds(self, value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value if value < 1e11 else value / 1000)
        if isinstance(value, datetime):
            dt = value
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        if isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.timestamp()
            except Exception:
                return 0.0
        return 0.0

    def _loss_cooldown_seconds(self, trade: Dict[str, Any], consecutive_losses: int) -> int:
        pnl = _safe_float(trade.get("pnl"), 0.0)
        roi = _safe_float(trade.get("pnl_percent") or trade.get("roi"), 0.0)
        reason = str(trade.get("close_reason") or "").upper()

        if consecutive_losses >= 2:
            return 15 * 60  # Reduzido de 24h para 15 minutos para re-entradas rápidas
        if "STOP" in reason or roi <= -100.0 or pnl <= -3.0:
            return 15 * 60  # Reduzido de 6h para 15 minutos
        if roi <= -50.0 or pnl <= -1.0:
            return 10 * 60  # Reduzido de 2h para 10 minutos
        return 5 * 60      # Reduzido de 30m para 5 minutos

    def _build_symbol_memory(self, history: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        memory: Dict[str, Dict[str, Any]] = {}
        ordered = sorted(history, key=lambda t: self._timestamp_seconds(t.get("timestamp")), reverse=True)

        for trade in ordered:
            symbol = _normalize_symbol(trade.get("symbol"))
            if not symbol:
                continue

            row = memory.setdefault(symbol, {
                "symbol": symbol,
                "wins": 0,
                "losses": 0,
                "total_pnl": 0.0,
                "total_roi": 0.0,
                "trades": 0,
                "consecutive_losses": 0,
                "latest_loss_at": 0.0,
                "latest_loss": None,
                "latest_trade_is_loss": None,
            })

            pnl = _safe_float(trade.get("pnl"), 0.0)
            roi = _safe_float(trade.get("pnl_percent") or trade.get("roi"), 0.0)
            is_loss = pnl < 0 or roi < 0

            row["trades"] += 1
            row["total_pnl"] += pnl
            row["total_roi"] += roi
            if is_loss:
                row["losses"] += 1
                ts = self._timestamp_seconds(trade.get("timestamp"))
                if ts > row["latest_loss_at"]:
                    row["latest_loss_at"] = ts
                    row["latest_loss"] = trade
            else:
                row["wins"] += 1

        for symbol, row in memory.items():
            recent = [t for t in ordered if _normalize_symbol(t.get("symbol")) == symbol]
            if recent:
                latest = recent[0]
                row["latest_trade_is_loss"] = (
                    _safe_float(latest.get("pnl"), 0.0) < 0
                    or _safe_float(latest.get("pnl_percent") or latest.get("roi"), 0.0) < 0
                )
            streak = 0
            for trade in recent:
                pnl = _safe_float(trade.get("pnl"), 0.0)
                roi = _safe_float(trade.get("pnl_percent") or trade.get("roi"), 0.0)
                if pnl < 0 or roi < 0:
                    streak += 1
                else:
                    break
            row["consecutive_losses"] = streak
            row["avg_roi"] = round(row["total_roi"] / row["trades"], 2) if row["trades"] else 0.0
            row["win_rate"] = round((row["wins"] / row["trades"]) * 100, 1) if row["trades"] else 0.0

        return memory

    def _symbol_suspensions(self, memory: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        now = time.time()
        suspensions: Dict[str, Dict[str, Any]] = {}

        for symbol, row in memory.items():
            latest_loss = row.get("latest_loss")
            latest_loss_at = _safe_float(row.get("latest_loss_at"), 0.0)
            if not latest_loss or latest_loss_at <= 0 or not row.get("latest_trade_is_loss"):
                continue

            duration = self._loss_cooldown_seconds(latest_loss, int(row.get("consecutive_losses") or 0))
            until = latest_loss_at + duration
            if until <= now:
                continue

            remaining = int(until - now)
            suspensions[symbol] = {
                "symbol": symbol,
                "remaining_seconds": remaining,
                "remaining_minutes": round(remaining / 60, 1),
                "until": until,
                "motivo": (
                    f"{row.get('consecutive_losses', 0)} perda(s) recente(s); "
                    f"ultimo PnL ${_safe_float(latest_loss.get('pnl'), 0.0):.2f} "
                    f"({ _safe_float(latest_loss.get('pnl_percent') or latest_loss.get('roi'), 0.0):.1f}% ROI)"
                ),
            }

        return suspensions

    def _position_pnl_usd(self, position: Dict[str, Any]) -> float:
        projection = position.get("projection")
        if isinstance(projection, dict):
            projected_pnl = projection.get("pnl_usd")
            if projected_pnl is not None:
                return _safe_float(projected_pnl, 0.0)

        direct_pnl = position.get("pnl_usd")
        if direct_pnl is not None:
            return _safe_float(direct_pnl, 0.0)

        pnl = position.get("pnl")
        if pnl is not None:
            return _safe_float(pnl, 0.0)

        roi = _safe_float(
            position.get("pnl_percent")
            or position.get("roi_percent")
            or position.get("roi"),
            0.0,
        )
        margin = _safe_float(position.get("entry_margin"), 0.0)

        if margin <= 0 and isinstance(projection, dict):
            margin = _safe_float(projection.get("entry_margin"), 0.0)

        if margin <= 0:
            entry = _safe_float(position.get("entry_price"), 0.0)
            qty = _safe_float(position.get("qty"), 0.0)
            leverage = _safe_float(position.get("leverage"), 50.0)
            contract = projection.get("contract") if isinstance(projection, dict) else position.get("contract_meta")
            ct_val = _safe_float(contract.get("ct_val") if isinstance(contract, dict) else None, 1.0)
            if entry > 0 and qty > 0 and leverage > 0:
                margin = (entry * qty * ct_val) / leverage

        return (roi / 100.0) * margin if margin > 0 else 0.0

    def _position_stop_roi(self, position: Dict[str, Any]) -> Optional[float]:
        entry = _safe_float(position.get("entry_price") or position.get("entry"), 0.0)
        stop = _safe_float(position.get("current_stop") or position.get("stop_loss") or position.get("stop"), 0.0)
        leverage = _safe_float(position.get("leverage"), 50.0)
        side = str(position.get("side") or position.get("direction") or "").lower()

        if entry <= 0 or stop <= 0 or leverage <= 0:
            return None

        if side in ("sell", "short"):
            return ((entry - stop) / entry) * leverage * 100
        if side in ("buy", "long"):
            return ((stop - entry) / entry) * leverage * 100
        return None

    def _protected_slot_count(self, active_slots: List[Dict[str, Any]]) -> int:
        protected = 0
        for slot in active_slots:
            stop_roi = self._position_stop_roi(slot)
            if stop_roi is not None and stop_roi >= 0.0:
                protected += 1
        return protected

    def _position_stop_pnl_usd(self, position: Dict[str, Any]) -> float:
        stop_roi = self._position_stop_roi(position)
        if stop_roi is None or stop_roi <= 0:
            return 0.0

        margin = _safe_float(position.get("entry_margin"), 0.0)
        projection = position.get("projection")
        if margin <= 0 and isinstance(projection, dict):
            margin = _safe_float(projection.get("entry_margin"), 0.0)

        if margin <= 0:
            entry = _safe_float(position.get("entry_price") or position.get("entry"), 0.0)
            qty = _safe_float(position.get("qty") or position.get("size"), 0.0)
            leverage = _safe_float(position.get("leverage"), 50.0)
            contract = projection.get("contract") if isinstance(projection, dict) else position.get("contract_meta")
            ct_val = _safe_float(contract.get("ct_val") if isinstance(contract, dict) else None, 1.0)
            if entry > 0 and qty > 0 and leverage > 0:
                margin = (entry * qty * ct_val) / leverage

        return max(0.0, (stop_roi / 100.0) * margin) if margin > 0 else 0.0

    def _realized_pnl_usd(self, history: List[Dict[str, Any]]) -> float:
        return sum(_safe_float(trade.get("pnl"), 0.0) for trade in history)

    def _live_bankroll_snapshot(
        self,
        banca: Dict[str, Any],
        base_balance: float,
        active_slots: List[Dict[str, Any]],
        active_moonbags: List[Dict[str, Any]],
        history: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        stored_equity = _safe_float(banca.get("saldo_total"), 0.0)
        realized_pnl = self._realized_pnl_usd(history)
        open_slots_pnl = sum(self._position_pnl_usd(slot) for slot in active_slots)
        open_moonbags_pnl = sum(self._position_pnl_usd(moonbag) for moonbag in active_moonbags)
        calculated_equity = base_balance + realized_pnl + open_slots_pnl + open_moonbags_pnl

        has_live_or_realized_pnl = any(abs(value) > 0.000001 for value in (realized_pnl, open_slots_pnl, open_moonbags_pnl))
        if has_live_or_realized_pnl:
            equity = calculated_equity
        elif stored_equity > 0:
            equity = stored_equity
        else:
            equity = base_balance

        return {
            "equity": equity,
            "stored_equity": stored_equity,
            "calculated_equity": calculated_equity,
            "realized_pnl": realized_pnl,
            "open_slots_pnl": open_slots_pnl,
            "open_moonbags_pnl": open_moonbags_pnl,
        }

    def _health_mode(
        self,
        equity: float,
        base_balance: float,
        active_slots: int,
        active_moonbags: int = 0,
        open_moonbags_pnl: float = 0.0,
        protected_slots: int = 0,
        realized_pnl: float = 0.0,
        secured_open_pnl: float = 0.0,
        is_ranging_mode: bool = True,
    ) -> Dict[str, Any]:
        max_regime_slots = 20 if is_ranging_mode else 40
        if base_balance <= 0:
            base_balance = _safe_float(getattr(settings, "OKX_SIMULATED_BALANCE", 100.0), 100.0)

        if self.peak_equity <= 0:
            self.peak_equity = max(equity, base_balance)
        else:
            self.peak_equity = max(self.peak_equity, equity)

        session_profit = equity - base_balance
        peak_profit = max(0.0, self.peak_equity - base_balance)
        secured_profit_now = max(
            0.0,
            min(max(0.0, session_profit), realized_pnl + secured_open_pnl),
        )
        self.protected_profit_peak = max(self.protected_profit_peak, secured_profit_now)
        session_roi = (session_profit / base_balance) * 100 if base_balance > 0 else 0.0
        drawdown_from_peak = self.peak_equity - equity
        drawdown_from_peak_pct = (drawdown_from_peak / self.peak_equity) * 100 if self.peak_equity > 0 else 0.0
        profit_multiple = (self.protected_profit_peak / base_balance) if base_balance > 0 else 0.0
        protected_profit_context = (
            (active_moonbags > 0 and open_moonbags_pnl > 0 and session_profit > 0)
            or (protected_slots > 0 and session_profit > 0)
        )
        material_profit_floor = self.protected_profit_peak >= max(1.0, base_balance * 0.05)

        lock_ratio = 0.0
        if self.protected_profit_peak > 0 and (material_profit_floor or protected_profit_context):
            if profit_multiple >= 4.0:
                lock_ratio = 0.85
            elif profit_multiple >= 1.0:
                lock_ratio = 0.80
            else:
                lock_ratio = 0.70
        locked_profit = max(0.0, self.protected_profit_peak * lock_ratio)
        allowed_giveback = max(0.0, self.protected_profit_peak - locked_profit)
        protected_floor = base_balance + locked_profit

        mode = "ACUMULACAO"
        state_label = "Acumulando"
        min_score = 45.0
        max_slots = max_regime_slots
        health = 88
        reasons = ["Banca em condicao operacional."]

        profitable_moonbag_active = active_moonbags > 0 and open_moonbags_pnl > 0 and session_profit > 0
        protected_slot_active = protected_slots > 0 and session_profit > 0

        if equity <= max(2.0, base_balance * 0.10):
            mode = "PRESERVACAO_TOTAL"
            state_label = "Preservacao total"
            min_score = 999.0
            max_slots = 0
            health = 5
            reasons = [f"Equity viva critica (${equity:.2f}). Kill-switch operacional ativo; novas entradas pausadas."]
            return {
                "mode": mode,
                "state_label": state_label,
                "health_score": health,
                "min_score": min_score,
                "max_slots": max_slots,
                "session_profit": round(session_profit, 4),
                "session_roi": round(session_roi, 2),
                "peak_equity": round(self.peak_equity, 4),
                "drawdown_from_peak": round(drawdown_from_peak, 4),
                "drawdown_from_peak_pct": round(drawdown_from_peak_pct, 2),
                "locked_profit": round(locked_profit, 4),
                "allowed_giveback": round(allowed_giveback, 4),
                "protected_floor": round(protected_floor, 4),
                "reasons": reasons,
            }

        if profitable_moonbag_active or protected_slot_active:
            if profit_multiple >= 4.0:
                min_score = 88.0
                health = 96
            else:
                min_score = 80.0
                health = 94
            mode = "ACUMULACAO_PROTEGIDA"
            state_label = "Acumulacao protegida"
            max_slots = max_regime_slots
            reasons = []
            if profitable_moonbag_active:
                reasons.append(f"Moonbag lucrativa ativa (${open_moonbags_pnl:.2f}). Mantendo fabrica de slots ligada.")
            if protected_slot_active:
                reasons.append(f"{protected_slots} slot(s) com stop em break-even/lucro. Escadinha protegida pelo Flash.")
            reasons.append(
                f"Lucro vivo da sessao ${session_profit:.2f}; Guardiao eleva o score minimo sem desligar a fabrica."
            )
            return {
                "mode": mode,
                "state_label": state_label,
                "health_score": health,
                "min_score": min_score,
                "max_slots": max_slots,
                "session_profit": round(session_profit, 4),
                "session_roi": round(session_roi, 2),
                "peak_equity": round(self.peak_equity, 4),
                "drawdown_from_peak": round(drawdown_from_peak, 4),
                "drawdown_from_peak_pct": round(drawdown_from_peak_pct, 2),
                "locked_profit": round(locked_profit, 4),
                "allowed_giveback": round(allowed_giveback, 4),
                "protected_floor": round(protected_floor, 4),
                "reasons": reasons,
            }
 
        is_paper = getattr(settings, "OKX_EXECUTION_MODE", "REAL") == "PAPER"

        if material_profit_floor and self.protected_profit_peak > 0 and equity <= protected_floor:
            if is_paper:
                mode = "CAUTELOSO"
                state_label = "Cauteloso (Simulado)"
                min_score = 75.0
                max_slots = max_regime_slots
                health = 65
                reasons = [f"[PAPER-BYPASS] Piso protegido atingido (${protected_floor:.2f}). Trava atenuada em simulado."]
            else:
                mode = "PRESERVACAO_TOTAL"
                state_label = "Preservacao total"
                min_score = 999.0
                max_slots = 0
                health = 20
                reasons = [f"Piso protegido atingido (${protected_floor:.2f}). Novas entradas pausadas para nao devolver lucro."]
        elif session_roi <= -8.0 or drawdown_from_peak_pct >= 10.0:
            if is_paper:
                mode = "CAUTELOSO"
                state_label = "Cauteloso (Simulado)"
                min_score = 75.0
                max_slots = max_regime_slots
                health = 60
                reasons = ["[PAPER-BYPASS] Perda/drawdown critico. Trava atenuada em simulado para permitir cacada."]
            else:
                mode = "PRESERVACAO_TOTAL"
                state_label = "Preservacao total"
                min_score = 999.0
                max_slots = 0
                health = 25
                reasons = ["Perda/drawdown critico. Novas entradas pausadas."]
        elif session_roi <= -5.0 or drawdown_from_peak_pct >= 7.0:
            mode = "DEFESA"
            state_label = "Defesa"
            min_score = 92.0
            max_slots = max(1, int(max_regime_slots * 0.25))
            health = 45
            reasons = ["Banca em defesa. Apenas sinais de elite."]
        elif session_roi <= -3.0 or drawdown_from_peak_pct >= 4.0:
            mode = "CAUTELOSO"
            state_label = "Cauteloso"
            min_score = 85.0
            max_slots = max(2, int(max_regime_slots * 0.50))
            health = 65
            reasons = ["Banca cautelosa. Reduzindo exposicao."]
        elif self.protected_profit_peak > 0:
            if profit_multiple >= 4.0:
                mode = "ACUMULACAO_PROTEGIDA"
                state_label = "Acumulacao protegida"
                min_score = 88.0
                max_slots = max_regime_slots
                health = 96
            elif profit_multiple >= 1.0:
                mode = "ACUMULACAO_PROTEGIDA"
                state_label = "Acumulacao protegida"
                min_score = 80.0
                max_slots = max_regime_slots
                health = 94
            else:
                health = 92 if active_slots <= max_regime_slots else 80
            reasons = [
                f"Lucro confirmado por historico/stops. Protegendo ${locked_profit:.2f} "
                f"de ${self.protected_profit_peak:.2f} assegurados.",
                f"Devolucao maxima planejada: ${allowed_giveback:.2f}.",
            ]
            return {
                "mode": mode,
                "state_label": state_label,
                "health_score": health,
                "min_score": min_score,
                "max_slots": max_slots,
                "session_profit": round(session_profit, 4),
                "session_roi": round(session_roi, 2),
                "peak_equity": round(self.peak_equity, 4),
                "drawdown_from_peak": round(drawdown_from_peak, 4),
                "drawdown_from_peak_pct": round(drawdown_from_peak_pct, 2),
                "locked_profit": round(locked_profit, 4),
                "allowed_giveback": round(allowed_giveback, 4),
                "protected_floor": round(protected_floor, 4),
                "reasons": reasons,
            }

        return {
            "mode": mode,
            "state_label": state_label,
            "health_score": health,
            "min_score": min_score,
            "max_slots": max_slots,
            "session_profit": round(session_profit, 4),
            "session_roi": round(session_roi, 2),
            "peak_equity": round(self.peak_equity, 4),
            "drawdown_from_peak": round(drawdown_from_peak, 4),
            "drawdown_from_peak_pct": round(drawdown_from_peak_pct, 2),
            "locked_profit": round(locked_profit, 4),
            "allowed_giveback": round(allowed_giveback, 4),
            "protected_floor": round(protected_floor, 4),
            "reasons": reasons,
        }

    async def evaluate_bank_health(self) -> Dict[str, Any]:
        banca = await self._get_banca_status()
        slots = await self._get_slots()
        moonbags = await self._get_moonbags()
        history = await self._get_history()

        configured = _safe_float(banca.get("configured_balance"), 0.0)
        base_balance = configured or _safe_float(getattr(settings, "OKX_SIMULATED_BALANCE", 100.0), 100.0)

        active_slots = [
            s for s in slots
            if s.get("symbol") and _safe_float(s.get("entry_price"), 0.0) > 0 and _safe_float(s.get("qty"), 0.0) > 0
        ]
        active_moonbags = [m for m in moonbags if m.get("symbol")]
        protected_slots = self._protected_slot_count(active_slots)
        secured_open_pnl = sum(
            self._position_stop_pnl_usd(position)
            for position in [*active_slots, *active_moonbags]
        )

        # Detecta regime de mercado dinamicamente pelo ADX do btc
        is_ranging_mode = True
        try:
            from services.okx_ws_public import okx_ws_public_service
            adx = getattr(okx_ws_public_service, 'btc_adx', 0)
            is_ranging_mode = (adx < 25)
        except Exception:
            pass

        memory = self._build_symbol_memory(history)
        suspensions = self._symbol_suspensions(memory)
        live_bankroll = self._live_bankroll_snapshot(banca, base_balance, active_slots, active_moonbags, history)
        equity = live_bankroll["equity"]

        # [V111 FIX] Em modo REAL, a base_balance deve refletir o equity real da exchange.
        # Senao, com simulated_balance=$100 e equity real=$20, o Guardian ve -80% de
        # drawdown e entra em PRESERVACAO_TOTAL (min_score=999) bloqueando TUDO.
        if settings.OKX_EXECUTION_MODE != "PAPER":
            base_balance = equity
        health = self._health_mode(
            equity,
            base_balance,
            len(active_slots),
            len(active_moonbags),
            open_moonbags_pnl=live_bankroll["open_moonbags_pnl"],
            protected_slots=protected_slots,
            realized_pnl=live_bankroll["realized_pnl"],
            secured_open_pnl=secured_open_pnl,
            is_ranging_mode=is_ranging_mode,
        )

        max_slots = 20 if is_ranging_mode else 40

        report = {
            "agent": self.name,
            "status": health["state_label"],
            "mode": health["mode"],
            "health_score": health["health_score"],
            "equity": round(equity, 4),
            "base_balance": round(base_balance, 4),
            "session_profit": health["session_profit"],
            "session_roi": health["session_roi"],
            "peak_equity": health["peak_equity"],
            "drawdown_from_peak": health["drawdown_from_peak"],
            "drawdown_from_peak_pct": health["drawdown_from_peak_pct"],
            "locked_profit": health["locked_profit"],
            "allowed_giveback": health["allowed_giveback"],
            "protected_floor": health.get("protected_floor", 0.0),
            "stored_equity": round(live_bankroll["stored_equity"], 4),
            "calculated_equity": round(live_bankroll["calculated_equity"], 4),
            "realized_pnl": round(live_bankroll["realized_pnl"], 4),
            "open_slots_pnl": round(live_bankroll["open_slots_pnl"], 4),
            "open_moonbags_pnl": round(live_bankroll["open_moonbags_pnl"], 4),
            "secured_open_pnl": round(secured_open_pnl, 4),
            "protected_profit_peak": round(self.protected_profit_peak, 4),
            "active_slots": len(active_slots),
            "protected_slots": protected_slots,
            "unprotected_slots": max(0, len(active_slots) - protected_slots),
            "active_moonbags": len(active_moonbags),
            "max_slots_allowed": health["max_slots"],
            "min_score_required": health["min_score"],
            "suspended_symbols": list(suspensions.values()),
            "symbol_memory": memory,
            "reasons": health["reasons"],
            "message_ptbr": self._message_ptbr(
                health,
                equity,
                len(active_slots),
                len(active_moonbags),
                suspensions,
                protected_slots,
                max_slots=max_slots,
            ),
            "timestamp": time.time(),
        }
        self.last_report = report
        self.last_report_at = time.time()
        return report

    def _message_ptbr(
        self,
        health: Dict[str, Any],
        equity: float,
        active_slots: int,
        active_moonbags: int,
        suspensions: Dict[str, Dict[str, Any]],
        protected_slots: int = 0,
        max_slots: int = 40,
    ) -> str:
        suspended = ", ".join(sorted(suspensions.keys())) if suspensions else "nenhum"
        lines = [
            f"Guardiao da Banca: {health['state_label']}.",
            f"Saude da banca: {health['health_score']}/100.",
            f"Equity atual: ${equity:.2f}. Resultado da sessao: ${health['session_profit']:.2f} ({health['session_roi']:.1f}%).",
            f"Slots ativos: {active_slots}/{max_slots}. Moonbags ativas: {active_moonbags}.",
            f"Slots protegidos pelo Flash: {protected_slots}.",
            f"Modo: {health['mode']}. Score minimo para nova ordem: {health['min_score']:.0f}. Slots permitidos: {health['max_slots']}/{max_slots}.",
            f"Lucro protegido: ${health['locked_profit']:.2f}. Devolucao permitida: ${health['allowed_giveback']:.2f}.",
            f"Pares suspensos: {suspended}.",
        ]
        return " ".join(lines)

    async def authorize_new_trade(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        report = await self.evaluate_bank_health()
        symbol = _normalize_symbol(signal.get("symbol"))
        radar_score = _safe_float(signal.get("score") or signal.get("score_radar"), 0.0)
        unified_confidence = _safe_float(signal.get("unified_confidence"), 0.0)
        score = radar_score or unified_confidence
        signal_side = str(signal.get("side") or signal.get("direction") or "Buy").lower()

        approved = True
        reasons: List[str] = []

        # [DECOR_HUNTER 2.0] Sinal DECOR_HUNTER é isento do filtro de regime de mercado
        # pois busca pares desgrudados que se movem independentemente do BTC.
        is_decor_hunter = signal.get("radar_mode") == "DECOR_HUNTER"

        if is_decor_hunter:
            market = await self._get_market_data()
            report["market_data"] = market
            logger.info(
                f"[DECOR-HUNTER 2.0] {symbol} bypass MERCADO MORTO. "
                f"ADX={market['adx']:.1f} Dir={market['direction']}"
            )
        else:
            # [V111.2] FILTRO DE REGIME DE MERCADO
            market = await self._get_market_data()
            report["market_data"] = market

            if market["adx"] < settings.ADX_MIN_ENTRY:
                approved = False
                reasons.append(
                    f"MERCADO MORTO: ADX={market['adx']:.1f} < {settings.ADX_MIN_ENTRY:.0f}. "
                    "Novas entradas bloqueadas em regime de baixa volatilidade."
                )
            elif market["is_strong_trend"] or market["is_trending"]:
                is_long = signal_side in ("buy", "long")
                if market["direction"] == "UP" and not is_long:
                    approved = False
                    reasons.append(
                        f"CONTRA-TENDENCIA: BTC em BULL (ADX={market['adx']:.1f}), "
                        f"mas sinal e {signal_side.upper()}. Apenas LONGs permitidos."
                    )
                elif market["direction"] == "DOWN" and is_long:
                    approved = False
                    reasons.append(
                        f"CONTRA-TENDENCIA: BTC em BEAR (ADX={market['adx']:.1f}), "
                        f"mas sinal e {signal_side.upper()}. Apenas SHORTs permitidos."
                    )
            elif market["adx"] >= settings.ADX_MIN_ENTRY and market["adx"] < settings.ADX_TRENDING_THRESHOLD:
                is_long = signal_side in ("buy", "long")
                if market["direction"] == "UP" and not is_long:
                    approved = False
                    reasons.append(
                        f"ZONA DE TRANSICAO: BTC em BULL leve (ADX={market['adx']:.1f}), "
                        f"apenas LONGs permitidos ate confirmacao de tendencia."
                    )
                elif market["direction"] == "DOWN" and is_long:
                    approved = False
                    reasons.append(
                        f"ZONA DE TRANSICAO: BTC em BEAR leve (ADX={market['adx']:.1f}), "
                        f"apenas SHORTs permitidos ate confirmacao de tendencia."
                    )

        if report["mode"] == "PRESERVACAO_TOTAL":
            approved = False
            reasons.append("Modo Preservacao Total ativo. Novas entradas pausadas.")
        
        if report.get("active_slots", 0) >= report.get("max_slots_allowed", 40):
            approved = False
            reasons.append(
                f"Exposicao maxima do Guardiao atingida: {report.get('active_slots', 0)}/{report.get('max_slots_allowed', 40)} slots."
            )

        if score < report["min_score_required"]:
            approved = False
            reasons.append(
                f"Score {score:.1f} abaixo do minimo da banca ({report['min_score_required']:.1f})."
            )

        suspensions = {
            _normalize_symbol(s.get("symbol")): s
            for s in report.get("suspended_symbols", [])
        }
        if symbol in suspensions:
            approved = False
            reasons.append(f"{symbol} suspenso: {suspensions[symbol].get('motivo')}.")

        decision = {
            "approved": approved,
            "symbol": symbol,
            "score": round(score, 1),
            "radar_score": round(radar_score, 1),
            "unified_confidence": round(unified_confidence, 1),
            "mode": report["mode"],
            "health_score": report["health_score"],
            "market_data": {
                "adx": round(market["adx"], 1),
                "direction": market["direction"],
                "is_trending": market["is_trending"],
            },
            "reasons": reasons or ["Banca liberou a entrada."],
            "report": report,
        }

        if approved:
            logger.info(f"[BANKROLL-GUARDIAN] {symbol} {signal_side.upper()} liberado. ADX={market['adx']:.1f} Dir={market['direction']} | Saude {report['health_score']}/100.")
        else:
            logger.warning(f"[BANKROLL-GUARDIAN] {symbol} {signal_side.upper()} bloqueado: {' | '.join(reasons)}")
        return decision


bankroll_guardian = BankrollGuardian()
