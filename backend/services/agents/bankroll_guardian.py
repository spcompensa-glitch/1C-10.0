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
        self.last_report: Dict[str, Any] = {}
        self.last_report_at = 0.0

    def reset_runtime_state(self) -> Dict[str, Any]:
        snapshot = {
            "peak_equity": self.peak_equity,
            "last_report_at": self.last_report_at,
        }
        self.peak_equity = 0.0
        self.last_report = {}
        self.last_report_at = 0.0
        return snapshot

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
            return 24 * 3600
        if "STOP" in reason or roi <= -100.0 or pnl <= -3.0:
            return 6 * 3600
        if roi <= -50.0 or pnl <= -1.0:
            return 2 * 3600
        return 30 * 60

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

    def _health_mode(self, equity: float, base_balance: float, active_slots: int) -> Dict[str, Any]:
        if base_balance <= 0:
            base_balance = _safe_float(getattr(settings, "OKX_SIMULATED_BALANCE", 20.0), 20.0)

        if self.peak_equity <= 0:
            self.peak_equity = max(equity, base_balance)
        else:
            self.peak_equity = max(self.peak_equity, equity)

        session_profit = equity - base_balance
        session_roi = (session_profit / base_balance) * 100 if base_balance > 0 else 0.0
        drawdown_from_peak = self.peak_equity - equity
        drawdown_from_peak_pct = (drawdown_from_peak / self.peak_equity) * 100 if self.peak_equity > 0 else 0.0

        mode = "ACUMULACAO"
        state_label = "Acumulando"
        min_score = 45.0
        max_slots = 4
        health = 88
        reasons = ["Banca em condicao operacional."]

        if session_roi <= -8.0 or drawdown_from_peak_pct >= 10.0:
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
            max_slots = 1
            health = 45
            reasons = ["Banca em defesa. Apenas sinais de elite."]
        elif session_roi <= -3.0 or drawdown_from_peak_pct >= 4.0:
            mode = "CAUTELOSO"
            state_label = "Cauteloso"
            min_score = 85.0
            max_slots = 2
            health = 65
            reasons = ["Banca cautelosa. Reduzindo exposicao."]
        elif session_profit > 0:
            locked_profit = max(0.0, session_profit * 0.70)
            allowed_giveback = max(1.0, session_profit - locked_profit)
            health = 92 if active_slots <= 4 else 80
            reasons = [f"Lucro em acumulacao. Protegendo aproximadamente ${locked_profit:.2f}."]
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
            "locked_profit": 0.0,
            "allowed_giveback": 0.0,
            "reasons": reasons,
        }

    async def evaluate_bank_health(self) -> Dict[str, Any]:
        banca = await self._get_banca_status()
        slots = await self._get_slots()
        moonbags = await self._get_moonbags()
        history = await self._get_history()

        equity = _safe_float(banca.get("saldo_total"), 0.0)
        configured = _safe_float(banca.get("configured_balance"), 0.0)
        base_balance = configured or _safe_float(getattr(settings, "OKX_SIMULATED_BALANCE", 20.0), 20.0)

        active_slots = [
            s for s in slots
            if s.get("symbol") and _safe_float(s.get("entry_price"), 0.0) > 0 and _safe_float(s.get("qty"), 0.0) > 0
        ]
        active_moonbags = [m for m in moonbags if m.get("symbol")]

        memory = self._build_symbol_memory(history)
        suspensions = self._symbol_suspensions(memory)
        health = self._health_mode(equity, base_balance, len(active_slots))

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
            "active_slots": len(active_slots),
            "active_moonbags": len(active_moonbags),
            "max_slots_allowed": health["max_slots"],
            "min_score_required": health["min_score"],
            "suspended_symbols": list(suspensions.values()),
            "symbol_memory": memory,
            "reasons": health["reasons"],
            "message_ptbr": self._message_ptbr(health, equity, len(active_slots), len(active_moonbags), suspensions),
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
    ) -> str:
        suspended = ", ".join(sorted(suspensions.keys())) if suspensions else "nenhum"
        lines = [
            f"Guardiao da Banca: {health['state_label']}.",
            f"Saude da banca: {health['health_score']}/100.",
            f"Equity atual: ${equity:.2f}. Resultado da sessao: ${health['session_profit']:.2f} ({health['session_roi']:.1f}%).",
            f"Slots ativos: {active_slots}/4. Moonbags ativas: {active_moonbags}.",
            f"Modo: {health['mode']}. Score minimo para nova ordem: {health['min_score']:.0f}. Slots permitidos: {health['max_slots']}/4.",
            f"Lucro protegido: ${health['locked_profit']:.2f}. Devolucao permitida: ${health['allowed_giveback']:.2f}.",
            f"Pares suspensos: {suspended}.",
        ]
        return " ".join(lines)

    async def authorize_new_trade(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        report = await self.evaluate_bank_health()
        symbol = _normalize_symbol(signal.get("symbol"))
        score = _safe_float(signal.get("unified_confidence") or signal.get("score"), 0.0)

        approved = True
        reasons: List[str] = []

        if report["mode"] == "PRESERVACAO_TOTAL":
            approved = False
            reasons.append("Modo Preservacao Total ativo. Novas entradas pausadas.")

        if report["active_slots"] >= report["max_slots_allowed"]:
            approved = False
            reasons.append(
                f"Exposicao maxima do Guardiao atingida: {report['active_slots']}/{report['max_slots_allowed']} slots."
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
            "mode": report["mode"],
            "health_score": report["health_score"],
            "reasons": reasons or ["Banca liberou a entrada."],
            "report": report,
        }

        if approved:
            logger.info(f"[BANKROLL-GUARDIAN] {symbol} liberado. Saude {report['health_score']}/100 | modo {report['mode']}.")
        else:
            logger.warning(f"[BANKROLL-GUARDIAN] {symbol} bloqueado: {' | '.join(reasons)}")
        return decision


bankroll_guardian = BankrollGuardian()
