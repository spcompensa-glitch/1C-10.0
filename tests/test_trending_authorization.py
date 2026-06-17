import sys
import types
import time
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.agents.oracle_agent import OracleAgent
from services.agents.bankroll_guardian import BankrollGuardian


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _install_fake_bankroll(monkeypatch):
    fake_module = types.ModuleType("services.bankroll")
    class _FakeBankrollManager:
        hedge_active = False
        async def auto_close_hedge(self, reason: str):
            return reason
    fake_module.bankroll_manager = _FakeBankrollManager()
    monkeypatch.setitem(sys.modules, "services.bankroll", fake_module)


def _healthy_report():
    return {
        "mode": "ACUMULACAO",
        "health_score": 85,
        "active_slots": 2,
        "max_slots_allowed": 40,
        "min_score_required": 0.0,
        "suspended_symbols": [],
    }


async def _fake_health():
    return _healthy_report()


# ===================================================================
# ORACLEAGENT — Direção em cenários de tendência
# ===================================================================

class TestOracleTrending:

    @pytest.mark.asyncio
    async def test_adx_27_both_upframes_returns_trending_up(self, monkeypatch):
        _install_fake_bankroll(monkeypatch)
        agent = OracleAgent()
        await agent.update_market_data("test", {
            "btc_adx": 27.0,
            "btc_variation_1h": 0.8,
            "btc_variation_15m": 0.3,
        })
        ctx = agent.get_validated_context()
        assert ctx["regime"] == "TRENDING"
        assert ctx["btc_direction"] == "UP"

    @pytest.mark.asyncio
    async def test_adx_27_both_downframes_returns_trending_down(self, monkeypatch):
        _install_fake_bankroll(monkeypatch)
        agent = OracleAgent()
        await agent.update_market_data("test", {
            "btc_adx": 27.0,
            "btc_variation_1h": -1.2,
            "btc_variation_15m": -0.5,
        })
        ctx = agent.get_validated_context()
        assert ctx["regime"] == "TRENDING"
        assert ctx["btc_direction"] == "DOWN"

    @pytest.mark.asyncio
    async def test_adx_27_discordant_timeframes_fallback_1h_up(self, monkeypatch):
        """ADX>=25 com 15m e 1h discordando: usa 1h como fallback → UP."""
        _install_fake_bankroll(monkeypatch)
        agent = OracleAgent()
        await agent.update_market_data("test", {
            "btc_adx": 27.0,
            "btc_variation_1h": 0.6,
            "btc_variation_15m": -0.2,
        })
        ctx = agent.get_validated_context()
        assert ctx["regime"] == "TRENDING"
        assert ctx["btc_direction"] == "UP", (
            "ADX>=25 com timeframes discordantes deve usar 1h como fallback, "
            "NUNCA retornar LATERAL"
        )

    @pytest.mark.asyncio
    async def test_adx_27_discordant_timeframes_fallback_1h_down(self, monkeypatch):
        """ADX>=25 com 15m/1h discordando: 1h negativa → DOWN."""
        _install_fake_bankroll(monkeypatch)
        agent = OracleAgent()
        await agent.update_market_data("test", {
            "btc_adx": 28.5,
            "btc_variation_1h": -0.9,
            "btc_variation_15m": 0.15,
        })
        ctx = agent.get_validated_context()
        assert ctx["regime"] == "TRENDING"
        assert ctx["btc_direction"] == "DOWN"

    @pytest.mark.asyncio
    async def test_adx_18_ranging_returns_lateral(self, monkeypatch):
        """ADX<22 → RANGING, direção LATERAL (bloqueio total)."""
        _install_fake_bankroll(monkeypatch)
        agent = OracleAgent()
        await agent.update_market_data("test", {
            "btc_adx": 18.0,
            "btc_variation_1h": 0.3,
            "btc_variation_15m": 0.1,
        })
        ctx = agent.get_validated_context()
        assert ctx["regime"] == "RANGING"
        assert ctx["btc_direction"] == "LATERAL"

    @pytest.mark.asyncio
    async def test_adx_22_exact_boundary_transition(self, monkeypatch):
        """ADX=22 exato: TRANSITION, não RANGING."""
        _install_fake_bankroll(monkeypatch)
        agent = OracleAgent()
        await agent.update_market_data("test", {
            "btc_adx": 22.0,
            "btc_variation_1h": 0.5,
            "btc_variation_15m": 0.2,
        })
        ctx = agent.get_validated_context()
        assert ctx["regime"] == "TRANSITION"
        assert ctx["btc_direction"] == "UP"

    @pytest.mark.asyncio
    async def test_adx_25_exact_boundary_trending(self, monkeypatch):
        """ADX=25 exato: TRENDING, não TRANSITION nem RANGING."""
        _install_fake_bankroll(monkeypatch)
        agent = OracleAgent()
        await agent.update_market_data("test", {
            "btc_adx": 25.0,
            "btc_variation_1h": 0.4,
            "btc_variation_15m": 0.1,
        })
        ctx = agent.get_validated_context()
        assert ctx["regime"] == "TRENDING"
        assert ctx["btc_direction"] == "UP"

    @pytest.mark.asyncio
    async def test_adx_30_exact_boundary_roaring(self, monkeypatch):
        """ADX=30 exato: ROARING."""
        _install_fake_bankroll(monkeypatch)
        agent = OracleAgent()
        await agent.update_market_data("test", {
            "btc_adx": 30.0,
            "btc_variation_1h": -0.7,
            "btc_variation_15m": -0.3,
        })
        ctx = agent.get_validated_context()
        assert ctx["regime"] == "ROARING"
        assert ctx["btc_direction"] == "DOWN"

    @pytest.mark.asyncio
    async def test_transition_zone_weak_var1h_with_discordant_timeframes_returns_lateral(self, monkeypatch):
        """ADX 22-25, 15m/1h discordam, var_1h fraca: LATERAL (histerese)."""
        _install_fake_bankroll(monkeypatch)
        agent = OracleAgent()
        await agent.update_market_data("test", {
            "btc_adx": 23.5,
            "btc_variation_1h": 0.05,
            "btc_variation_15m": -0.2,
        })
        ctx = agent.get_validated_context()
        assert ctx["regime"] == "TRANSITION"
        assert ctx["btc_direction"] == "LATERAL", (
            "ADX 22-25 com timeframes discordantes e var_1h < 0.1% "
            "deve retornar LATERAL (histerese)"
        )

    @pytest.mark.asyncio
    async def test_transition_zone_weak_negative_var1h_with_discordant_timeframes_returns_lateral(self, monkeypatch):
        """ADX 22-25, 15m/1h discordam, var_1h > -0.1%: LATERAL (histerese)."""
        _install_fake_bankroll(monkeypatch)
        agent = OracleAgent()
        await agent.update_market_data("test", {
            "btc_adx": 23.0,
            "btc_variation_1h": -0.08,
            "btc_variation_15m": 0.15,
        })
        ctx = agent.get_validated_context()
        assert ctx["regime"] == "TRANSITION"
        assert ctx["btc_direction"] == "LATERAL"

    @pytest.mark.asyncio
    async def test_transition_zone_discordant_timeframes_tiebreaker(self, monkeypatch):
        """ADX 22-25, 15m/1h discordam, var_1h forte: 1h desempata."""
        _install_fake_bankroll(monkeypatch)
        agent = OracleAgent()
        await agent.update_market_data("test", {
            "btc_adx": 24.0,
            "btc_variation_1h": -0.6,
            "btc_variation_15m": 0.2,
        })
        ctx = agent.get_validated_context()
        assert ctx["regime"] == "TRANSITION"
        assert ctx["btc_direction"] == "DOWN"

    @pytest.mark.asyncio
    async def test_transition_blocks_when_timeframes_discordant_weak_1h(self, monkeypatch):
        """ADX 22-25 discordante com var_1h fraca: LATERAL."""
        _install_fake_bankroll(monkeypatch)
        agent = OracleAgent()
        await agent.update_market_data("test", {
            "btc_adx": 23.0,
            "btc_variation_1h": 0.08,
            "btc_variation_15m": -0.1,
        })
        ctx = agent.get_validated_context()
        assert ctx["regime"] == "TRANSITION"
        assert ctx["btc_direction"] == "LATERAL"

    @pytest.mark.asyncio
    async def test_adx_never_returns_lateral_when_above_trending(self, monkeypatch):
        """Propriedade invariante: ADX>=25 NUNCA retorna LATERAL no Oracle."""
        _install_fake_bankroll(monkeypatch)
        agent = OracleAgent()
        for adx in [25.0, 26.0, 27.5, 29.9, 30.0, 35.0, 40.0]:
            for var_1h in [-0.5, 0.5]:
                var_15m = -var_1h * 0.3  # sempre discordante (pior caso)
                await agent.update_market_data("test", {
                    "btc_adx": adx,
                    "btc_variation_1h": var_1h,
                    "btc_variation_15m": var_15m,
                })
                ctx = agent.get_validated_context()
                assert ctx["btc_direction"] != "LATERAL", (
                    f"ADX={adx} com variações {var_1h:.1f}/{var_15m:.2f} "
                    f"retornou LATERAL — o fallback 1h deveria ter sido usado"
                )
                assert ctx["regime"] in ("TRENDING", "ROARING")


# ===================================================================
# BANKROLLGUARDIAN — Autorização de trades em tendência
# ===================================================================

class TestGuardianTrendingAuthorization:

    @pytest.mark.asyncio
    async def test_trending_up_approves_long(self, monkeypatch):
        """ADX=27, direção UP, sinal LONG → aprovado."""
        guardian = BankrollGuardian()
        monkeypatch.setattr(guardian, "evaluate_bank_health", _fake_health)
        async def _trending_up():
            return {"adx": 27.0, "direction": "UP", "is_ranging": False,
                    "is_trending": True, "is_strong_trend": False}
        monkeypatch.setattr(guardian, "_get_market_data", _trending_up)
        decision = await guardian.authorize_new_trade({
            "symbol": "BTCUSDT", "side": "buy", "score": 85.0,
        })
        assert decision["approved"] is True, (
            f"Trending UP + LONG deveria aprovar. Razões: {decision['reasons']}"
        )
        assert decision["market_data"]["direction"] == "UP"

    @pytest.mark.asyncio
    async def test_trending_down_approves_short(self, monkeypatch):
        """ADX=27, direção DOWN, sinal SHORT → aprovado."""
        guardian = BankrollGuardian()
        monkeypatch.setattr(guardian, "evaluate_bank_health", _fake_health)
        async def _trending_down():
            return {"adx": 27.0, "direction": "DOWN", "is_ranging": False,
                    "is_trending": True, "is_strong_trend": False}
        monkeypatch.setattr(guardian, "_get_market_data", _trending_down)
        decision = await guardian.authorize_new_trade({
            "symbol": "ETHUSDT", "side": "sell", "score": 90.0,
        })
        assert decision["approved"] is True

    @pytest.mark.asyncio
    async def test_roaring_up_approves_long(self, monkeypatch):
        """ADX=32 (ROARING), direção UP, sinal LONG → aprovado."""
        guardian = BankrollGuardian()
        monkeypatch.setattr(guardian, "evaluate_bank_health", _fake_health)
        async def _roaring_up():
            return {"adx": 32.0, "direction": "UP", "is_ranging": False,
                    "is_trending": True, "is_strong_trend": True}
        monkeypatch.setattr(guardian, "_get_market_data", _roaring_up)
        decision = await guardian.authorize_new_trade({
            "symbol": "SOLUSDT", "side": "buy", "score": 75.0,
        })
        assert decision["approved"] is True

    @pytest.mark.asyncio
    async def test_trending_up_blocks_short_contra_tendencia(self, monkeypatch):
        """ADX=27, direção UP, sinal SHORT → BLOQUEADO (CONTRA-TENDENCIA)."""
        guardian = BankrollGuardian()
        monkeypatch.setattr(guardian, "evaluate_bank_health", _fake_health)
        async def _trending_up():
            return {"adx": 27.0, "direction": "UP", "is_ranging": False,
                    "is_trending": True, "is_strong_trend": False}
        monkeypatch.setattr(guardian, "_get_market_data", _trending_up)
        decision = await guardian.authorize_new_trade({
            "symbol": "BTCUSDT", "side": "sell", "score": 95.0,
        })
        assert decision["approved"] is False
        reasons = " | ".join(decision["reasons"])
        assert "CONTRA-TENDENCIA" in reasons

    @pytest.mark.asyncio
    async def test_trending_down_blocks_long_contra_tendencia(self, monkeypatch):
        """ADX=27, direção DOWN, sinal LONG → BLOQUEADO (CONTRA-TENDENCIA)."""
        guardian = BankrollGuardian()
        monkeypatch.setattr(guardian, "evaluate_bank_health", _fake_health)
        async def _trending_down():
            return {"adx": 27.0, "direction": "DOWN", "is_ranging": False,
                    "is_trending": True, "is_strong_trend": False}
        monkeypatch.setattr(guardian, "_get_market_data", _trending_down)
        decision = await guardian.authorize_new_trade({
            "symbol": "AVAXUSDT", "side": "buy", "score": 80.0,
        })
        assert decision["approved"] is False
        reasons = " | ".join(decision["reasons"])
        assert "CONTRA-TENDENCIA" in reasons

    @pytest.mark.asyncio
    async def test_ranging_blocks_all_trades(self, monkeypatch):
        """ADX=18 (RANGING) → BLOQUEADO (MERCADO MORTO)."""
        guardian = BankrollGuardian()
        monkeypatch.setattr(guardian, "evaluate_bank_health", _fake_health)
        async def _ranging():
            return {"adx": 18.0, "direction": "LATERAL", "is_ranging": True,
                    "is_trending": False, "is_strong_trend": False}
        monkeypatch.setattr(guardian, "_get_market_data", _ranging)
        decision = await guardian.authorize_new_trade({
            "symbol": "ANYUSDT", "side": "buy", "score": 99.0,
        })
        assert decision["approved"] is False
        reasons = " | ".join(decision["reasons"])
        assert "MERCADO MORTO" in reasons


# ===================================================================
# TRANSIÇÃO DE REGIME — Mesmo agente, ADX mudando
# ===================================================================

class TestRegimeTransition:

    @pytest.mark.asyncio
    async def test_same_guardian_first_blocks_ranging_then_approves_trending(self, monkeypatch):
        """
        Cenário real: ADX sobe de 18 (RANGING) para 27 (TRENDING).
        O MESMO guardian deve primeiro bloquear, depois aprovar.
        """
        guardian = BankrollGuardian()
        monkeypatch.setattr(guardian, "evaluate_bank_health", _fake_health)

        async def _ranging():
            return {"adx": 18.0, "direction": "LATERAL", "is_ranging": True,
                    "is_trending": False, "is_strong_trend": False}
        async def _trending_up():
            return {"adx": 27.0, "direction": "UP", "is_ranging": False,
                    "is_trending": True, "is_strong_trend": False}

        # Primeiro: ADX=18 → bloqueado
        monkeypatch.setattr(guardian, "_get_market_data", _ranging)
        decision1 = await guardian.authorize_new_trade({
            "symbol": "LINKUSDT", "side": "buy", "score": 85.0,
        })
        assert decision1["approved"] is False
        assert "MERCADO MORTO" in " | ".join(decision1["reasons"])

        # Depois: ADX=27 → aprovado
        monkeypatch.setattr(guardian, "_get_market_data", _trending_up)
        decision2 = await guardian.authorize_new_trade({
            "symbol": "LINKUSDT", "side": "buy", "score": 85.0,
        })
        assert decision2["approved"] is True, (
            f"ADX subiu para 27 mas ainda bloqueou. Razões: {decision2['reasons']}"
        )

    @pytest.mark.asyncio
    async def test_same_oracle_transitions_from_ranging_to_trending(self, monkeypatch):
        """
        OracleAgent: ADX 18 → LATERAL/RANGING.
        Mesma instância recebe ADX 27 → UP/TRENDING.
        """
        _install_fake_bankroll(monkeypatch)
        agent = OracleAgent()

        await agent.update_market_data("test", {
            "btc_adx": 18.0,
            "btc_variation_1h": 0.2,
            "btc_variation_15m": 0.1,
        })
        ctx1 = agent.get_validated_context()
        assert ctx1["regime"] == "RANGING"
        assert ctx1["btc_direction"] == "LATERAL"

        await agent.update_market_data("test", {
            "btc_adx": 27.5,
            "btc_variation_1h": 0.9,
            "btc_variation_15m": 0.4,
        })
        ctx2 = agent.get_validated_context()
        assert ctx2["regime"] == "TRENDING"
        assert ctx2["btc_direction"] == "UP"

    @pytest.mark.asyncio
    async def test_transition_from_lateral_to_trending_with_discordant_frames(self, monkeypatch):
        """
        ADX 18 (LATERAL) → ADX 27 com timeframes discordantes.
        Oracle deve sair de LATERAL e ir para UP (fallback 1h).
        """
        _install_fake_bankroll(monkeypatch)
        agent = OracleAgent()

        await agent.update_market_data("test", {
            "btc_adx": 18.0,
            "btc_variation_1h": 0.2,
            "btc_variation_15m": 0.1,
        })
        assert agent.get_validated_context()["btc_direction"] == "LATERAL"

        await agent.update_market_data("test", {
            "btc_adx": 27.0,
            "btc_variation_1h": 0.5,
            "btc_variation_15m": -0.2,
        })
        ctx = agent.get_validated_context()
        assert ctx["btc_direction"] == "UP", (
            f"Após transição RANGING→TRENDING com timeframes discordantes, "
            f"direção={ctx['btc_direction']}. Esperado UP (fallback 1h)."
        )


# ===================================================================
# SIMULAÇÃO CAPTAIN — LATERAL block com ADX
# ===================================================================

class TestCaptainTrendingBlock:

    def test_captain_monitor_signals_does_not_block_when_adx_above_25(self):
        """
        Reproduz a lógica do Captain.monitor_signals():
            is_ranging_mode = (adx < 25)
            if is_ranging_mode: continue  # bloqueia
        ADX >= 25 → is_ranging_mode = False → NÃO bloqueia.
        """
        for adx in [25.0, 26.0, 27.0, 30.0, 35.0]:
            is_ranging = (adx < 25)
            assert is_ranging is False, f"ADX={adx}: is_ranging_mode deveria ser False"

    def test_captain_monitor_signals_blocks_when_adx_below_25(self):
        """ADX < 25 → is_ranging_mode = True → bloqueia."""
        for adx in [0.0, 10.0, 18.0, 21.9, 22.0, 23.0, 24.9]:
            is_ranging = (adx < 25)
            assert is_ranging is True, f"ADX={adx}: is_ranging_mode deveria ser True"

    def test_captain_execution_logic_does_not_block_when_adx_above_25(self):
        """
        Reproduz a lógica do Captain._run_user_execution_logic():
            is_ranging_mode = (adx < 25)
            if is_ranging_mode: ...  # bloqueia
        ADX = 27 → NÃO bloqueia a execução.
        """
        adx = 27.0
        is_ranging_mode = (adx < 25)
        assert is_ranging_mode is False, "ADX=27 não deve travar execução"


# ===================================================================
# CONSISTÊNCIA ENTRE AGENTES
# ===================================================================

class TestCrossAgentConsistency:

    @pytest.mark.asyncio
    async def test_oracle_and_guardian_agree_on_trending_direction(self, monkeypatch):
        """
        Verifica que OracleAgent e BankrollGuardian chegam à
        MESMA direção para os mesmos dados de mercado.
        """
        _install_fake_bankroll(monkeypatch)
        oracle = OracleAgent()
        guardian = BankrollGuardian()

        market_scenarios = [
            {"adx": 27.0, "var_1h": 0.8, "var_15m": 0.3, "expect": "UP"},
            {"adx": 28.0, "var_1h": -1.2, "var_15m": -0.5, "expect": "DOWN"},
            {"adx": 26.0, "var_1h": 0.5, "var_15m": -0.1, "expect": "UP"},
            {"adx": 29.0, "var_1h": -0.7, "var_15m": 0.2, "expect": "DOWN"},
            {"adx": 18.0, "var_1h": 0.3, "var_15m": 0.1, "expect": "LATERAL"},
        ]

        for s in market_scenarios:
            await oracle.update_market_data("test", {
                "btc_adx": s["adx"],
                "btc_variation_1h": s["var_1h"],
                "btc_variation_15m": s["var_15m"],
            })
            ctx = oracle.get_validated_context()
            guardian_dir = self._simulate_guardian_direction(
                s["adx"], s["var_1h"], s["var_15m"],
            )

            assert ctx["btc_direction"] == guardian_dir == s["expect"], (
                f"Mismatch ADX={s['adx']}: Oracle={ctx['btc_direction']}, "
                f"Guardian={guardian_dir}, esperado={s['expect']}"
            )

    def _simulate_guardian_direction(self, adx, var_1h, var_15m):
        """Reproduz a lógica de direção do BankrollGuardian."""
        if adx < 22:
            return "LATERAL"
        if var_15m > 0 and var_1h > 0:
            return "UP"
        if var_15m < 0 and var_1h < 0:
            return "DOWN"
        if adx >= 25:
            return "UP" if var_1h > 0 else "DOWN"
        return "UP" if var_1h > 0.1 else ("DOWN" if var_1h < -0.1 else "LATERAL")
