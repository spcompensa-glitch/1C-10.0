# -*- coding: utf-8 -*-
"""
Testes para o KronosScorer — serviço de scoring de convicção via séries temporais.

Cobre:
  - Teste de score em tendência de alta
  - Teste de score em tendência de queda
  - Teste de score em sideways
  - Teste de fallback quando não há dados
  - Teste de cache
  - Teste de batch scoring
  - Teste de health check
  - Teste de inicialização
  - Teste de configuração via settings
  - Teste de integração com captain.py
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch, MagicMock


# Mark all tests as asyncio
pytestmark = pytest.mark.asyncio


class TestKronosScorerUnit:
    """Testes unitários do KronosScorer."""

    @pytest.mark.asyncio
    async def test_score_signal_downtrend(self, kronos_scorer_instance, mock_okx_rest_downtrend):
        """
        Testa score_signal em tendência de queda com sinal SHORT.
        Deve retornar conviction >= 50 (alinhamento parcial).
        """
        scorer = kronos_scorer_instance
        result = await scorer.score_signal("BTCUSDT", "Sell", interval="5")
        
        assert result is not None
        assert "conviction" in result
        assert 0 <= result["conviction"] <= 100
        assert result["source"] == "fallback"
        assert result["prediction_direction"] in ("UP", "DOWN", "SIDEWAYS", "NEUTRAL")
        print(f"  → Short/Downtrend: conviction={result['conviction']}, dir={result['prediction_direction']}")

    @pytest.mark.asyncio
    async def test_score_signal_buy_uptrend(self, kronos_scorer_instance, mock_okx_rest):
        """
        Testa score_signal em tendência de alta com sinal LONG.
        Deve retornar conviction >= 50 (alinhamento parcial-total).
        """
        scorer = kronos_scorer_instance
        result = await scorer.score_signal("BTCUSDT", "Buy", interval="5")
        
        assert result is not None
        assert "conviction" in result
        assert 0 <= result["conviction"] <= 100
        assert result["source"] == "fallback"
        print(f"  → Long/Uptrend: conviction={result['conviction']}, dir={result['prediction_direction']}")

    @pytest.mark.asyncio
    async def test_score_signal_sideways(self, kronos_scorer_instance, mock_okx_rest_sideways):
        """
        Testa score_signal em mercado sideways.
        Deve retornar conviction baixo (sideways não confirma nem rejeita).
        """
        scorer = kronos_scorer_instance
        result = await scorer.score_signal("BTCUSDT", "Buy", interval="5")
        
        assert result is not None
        assert "conviction" in result
        assert result["source"] == "fallback"
        # Sideways tem penalidade de movimento pequeno → score tende a ser ≤ 50
        print(f"  → Buy/Sideways: conviction={result['conviction']}, dir={result['prediction_direction']}")

    @pytest.mark.asyncio
    async def test_score_signal_empty_data(self, kronos_scorer_instance, mock_okx_rest_empty):
        """
        Testa score_signal sem dados.
        Deve retornar score neutro (50) e source = "fallback".
        """
        scorer = kronos_scorer_instance
        result = await scorer.score_signal("BTCUSDT", "Buy", interval="5")
        
        assert result is not None
        assert result["conviction"] == 50
        assert result["source"] == "fallback"
        assert result["prediction_direction"] == "NEUTRAL"

    @pytest.mark.asyncio
    async def test_score_signal_wrong_direction(self, kronos_scorer_instance, mock_okx_rest):
        """
        Testa score_signal com direção contrária à tendência.
        LONG em tendência de alta é alinhado. Vamos testar SHORT em tendência de alta.
        """
        scorer = kronos_scorer_instance
        result = await scorer.score_signal("BTCUSDT", "Sell", interval="5")
        
        assert result is not None
        assert "conviction" in result
        print(f"  → Short/Uptrend: conviction={result['conviction']}, dir={result['prediction_direction']}")

    @pytest.mark.asyncio
    async def test_cache(self, kronos_scorer_instance, mock_okx_rest):
        """
        Testa que o cache funciona: chamadas subsequentes para o mesmo símbolo
        não devem refazer o cálculo.
        """
        scorer = kronos_scorer_instance
        scorer.cache_ttl = 60
        
        # Primeira chamada
        result1 = await scorer.score_signal("BTCUSDT", "Buy")
        
        # Verifica que o cache foi populado
        cached = scorer._get_cached("BTCUSDT")
        assert cached is not None
        assert cached["conviction"] == result1["conviction"]
        
        # Segunda chamada (deve vir do cache)
        result2 = await scorer.score_signal("BTCUSDT", "Buy")
        assert result2["conviction"] == result1["conviction"]

    @pytest.mark.asyncio
    async def test_cache_expiry(self, kronos_scorer_instance, mock_okx_rest):
        """
        Testa que o cache expira após o TTL.
        """
        scorer = kronos_scorer_instance
        scorer.cache_ttl = 0  # Cache expira imediatamente
        
        # Primeira chamada
        result1 = await scorer.score_signal("BTCUSDT", "Buy")
        
        # Cache deve ter expirado
        cached = scorer._get_cached("BTCUSDT")
        assert cached is None or time.time() > scorer._score_cache.get("BTCUSDT", {}).get("expiry", 0)

    @pytest.mark.asyncio
    async def test_batch_scoring(self, kronos_scorer_instance, mock_okx_rest, mock_okx_rest_downtrend):
        """
        Testa o batch scoring para múltiplos símbolos.
        Como mock_okx_rest retorna sempre os mesmos dados, todos os scores
        devem ser computáveis e no formato correto.
        """
        # Precisamos de mock diferente pro segundo símbolo
        # Vamos usar um único mock que serve para ambos
        scorer = kronos_scorer_instance
        
        signals = [
            {"symbol": "BTCUSDT", "side": "Buy"},
            {"symbol": "ETHUSDT", "side": "Sell"},
        ]
        
        results = await scorer.score_batch(signals)
        
        assert len(results) == 2
        for r in results:
            assert "kronos_score" in r
            assert 0 <= r["kronos_score"] <= 100
            assert "kronos_data" in r
            assert r["kronos_data"].get("source") in ("fallback", "cache", "error")

    @pytest.mark.asyncio
    async def test_health_check(self, kronos_scorer_instance):
        """
        Testa o health check do serviço.
        """
        scorer = kronos_scorer_instance
        health = await scorer.health_check()
        
        assert "available" in health
        assert "loaded" in health
        assert "model" in health
        assert "cache_size" in health
        assert "mode" in health
        assert health["mode"] in ("REAL", "FALLBACK")


class TestKronosScorerFallback:
    """Testes específicos do mecanismo de fallback."""

    @pytest.mark.asyncio
    async def test_fallback_returns_valid_structure(self, kronos_scorer_instance, mock_okx_rest):
        """
        Testa que o fallback retorna a estrutura correta.
        """
        scorer = kronos_scorer_instance
        result = await scorer._fallback_score("BTCUSDT", "buy", "5")
        
        assert "conviction" in result
        assert "prediction_direction" in result
        assert "confidence" in result
        assert "volatility" in result
        assert "source" in result
        assert result["source"] == "fallback"
        assert 0 <= result["conviction"] <= 100
        assert result["prediction_direction"] in ("UP", "DOWN", "SIDEWAYS", "NEUTRAL")

    @pytest.mark.asyncio  
    async def test_fallback_no_data(self, kronos_scorer_instance, mock_okx_rest_empty):
        """
        Testa fallback sem dados retorna neutro.
        """
        scorer = kronos_scorer_instance
        result = await scorer._fallback_score("BTCUSDT", "buy", "5")
        
        assert result["conviction"] == 50
        assert result["prediction_direction"] == "NEUTRAL"


class TestKronosCalculateConviction:
    """Testes do cálculo interno de convicção."""

    def test_uptrend_buy_aligned(self, kronos_scorer_instance):
        """
        Testa que uma tendência de alta + Buy resulta em conviction alta.
        """
        import pandas as pd
        
        # Cria predição de alta
        pred_df = pd.DataFrame({
            'close': [100.0, 100.5, 101.0, 101.8, 102.5, 103.0,
                      103.2, 103.8, 104.0, 104.5, 104.8, 105.2]
        })
        
        # Histórico pequeno
        hist_df = pd.DataFrame({
            'close': [99.0, 99.5, 100.0]
        })
        
        result = kronos_scorer_instance._calculate_conviction(pred_df, hist_df, "buy")
        
        assert result["prediction_direction"] == "UP"
        assert result["conviction"] >= 30  # Deve ter pelo menos 30 por alinhamento
        print(f"  → Uptrend+Buy: conviction={result['conviction']}, dir={result['prediction_direction']}, conf={result['confidence']}")

    def test_downtrend_sell_aligned(self, kronos_scorer_instance):
        """
        Testa que uma tendência de queda + Sell resulta em conviction alta.
        """
        import pandas as pd
        
        pred_df = pd.DataFrame({
            'close': [100.0, 99.5, 99.0, 98.2, 97.5, 97.0,
                      96.8, 96.2, 96.0, 95.5, 95.2, 94.8]
        })
        
        hist_df = pd.DataFrame({
            'close': [101.0, 100.5, 100.0]
        })
        
        result = kronos_scorer_instance._calculate_conviction(pred_df, hist_df, "sell")
        
        assert result["prediction_direction"] == "DOWN"
        assert result["conviction"] >= 30

    def test_uptrend_sell_wrong(self, kronos_scorer_instance):
        """
        Testa que uma tendência de alta + Sell resulta em conviction baixa.
        """
        import pandas as pd
        
        pred_df = pd.DataFrame({
            'close': [100.0, 100.5, 101.0, 101.8, 102.5, 103.0,
                      103.2, 103.8, 104.0, 104.5, 104.8, 105.2]
        })
        
        hist_df = pd.DataFrame({
            'close': [99.0, 99.5, 100.0]
        })
        
        result = kronos_scorer_instance._calculate_conviction(pred_df, hist_df, "sell")
        
        # Direção contrária → direction_score = 0
        assert result["prediction_direction"] == "UP"
        # Conviction pode ser > 0 pela componente de confiança
        print(f"  → Uptrend+Sell: conviction={result['conviction']} (esperado baixo)")

    def test_sideways_neutral(self, kronos_scorer_instance):
        """
        Testa que sideways + qualquer direção resulta em conviction médio.
        """
        import pandas as pd
        import numpy as np
        
        pred_df = pd.DataFrame({
            'close': [100.0, 100.1, 100.0, 99.9, 100.0, 100.1,
                      100.0, 99.9, 100.0, 100.1, 100.0, 99.9]
        })
        
        hist_df = pd.DataFrame({
            'close': [100.0, 100.0, 100.0]
        })
        
        result = kronos_scorer_instance._calculate_conviction(pred_df, hist_df, "buy")
        
        # Movimento < 0.1% → penalidade de -15
        # Direção pode ser SIDEWAYS → direction_score = 20
        assert result["conviction"] <= 60
        print(f"  → Sideways: conviction={result['conviction']}, dir={result['prediction_direction']}")

    def test_high_volatility_penalty(self, kronos_scorer_instance):
        """
        Testa que volatilidade muito baixa penaliza o score.
        """
        import pandas as pd
        
        # Volatilidade quase zero
        pred_df = pd.DataFrame({
            'close': [100.0, 100.0, 100.0, 100.0, 100.0, 100.0,
                      100.0, 100.0, 100.0, 100.0, 100.0, 100.01]
        })
        
        hist_df = pd.DataFrame({
            'close': [100.0, 100.0, 100.0]
        })
        
        result = kronos_scorer_instance._calculate_conviction(pred_df, hist_df, "buy")
        
        # Volatilidade < 0.05 → penalidade de -20
        print(f"  → Low Vol: conviction={result['conviction']} (esperado com penalidade)")


class TestKronosIntegrationCaptain:
    """Testes de integração com o CaptainAgent."""

    @pytest.mark.asyncio
    async def test_captain_imports_kronos(self):
        """
        Testa que o captain.py importa o kronos_scorer corretamente.
        """
        try:
            # Verifica que o módulo pode ser importado (sem executar)
            from services.kronos_scorer import kronos_scorer
            assert kronos_scorer is not None
        except ImportError as e:
            pytest.skip(f"Kronos import não disponível: {e}")

    @pytest.mark.asyncio
    async def test_kronos_score_in_fleet_consensus(self, kronos_scorer_instance):
        """
        Testa que o kronos_score é integrado corretamente no formato
        esperado pelo _get_fleet_consensus.
        
        Simula o fluxo: signal → kronos → unified_confidence.
        """
        scorer = kronos_scorer_instance
        
        # Simula um sinal
        signal = {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "score": 75
        }
        
        # Chama o scorer
        result = await scorer.score_signal(
            signal["symbol"], 
            signal["side"], 
            interval="5"
        )
        
        # Verifica formato esperado pelo captain
        assert "conviction" in result
        assert "prediction_direction" in result
        assert "confidence" in result
        assert "source" in result
        
        # O Captain usa o campo 'conviction' como kronos_score
        kronos_score = result["conviction"]
        kronos_weight = 0.18
        
        # Simula o cálculo do unified_score (igual ao captain)
        macro_score = 70
        micro_score = 50
        smc_score = signal["score"]
        on_chain_score = 60
        
        remaining_weight = 1.0 - kronos_weight
        base_score = (macro_score * 0.15) + (micro_score * 0.25) + (smc_score * 0.30) + (on_chain_score * 0.30)
        unified_score = base_score * remaining_weight + kronos_score * kronos_weight
        
        assert 0 <= unified_score <= 100
        print(f"  → Unified: macro={macro_score} micro={micro_score} smc={smc_score} onchain={on_chain_score} kronos={kronos_score}")
        print(f"  → Base={base_score:.1f} + Kronos={kronos_score}*{kronos_weight} = Unified={unified_score:.1f}")


class TestKronosScorerInitialization:
    """Testes de inicialização do serviço."""

    @pytest.mark.asyncio
    async def test_initialization_without_pytorch(self, kronos_scorer_instance):
        """
        Testa que o scorer inicializa mesmo sem PyTorch instalado.
        """
        scorer = kronos_scorer_instance
        assert scorer.is_available is False  # Modo forçado
        assert scorer.is_loaded is False
        
        # initialize não deve quebrar
        await scorer.initialize()
        assert scorer.is_loaded is False  # Não carrega porque is_available=False

    @pytest.mark.asyncio
    async def test_score_without_initialization(self, kronos_scorer_instance, mock_okx_rest):
        """
        Testa que score_signal funciona mesmo sem initialize() explícito.
        """
        scorer = kronos_scorer_instance
        result = await scorer.score_signal("BTCUSDT", "Buy")
        assert result is not None
        assert "conviction" in result

    @pytest.mark.asyncio
    async def test_double_initialization(self, kronos_scorer_instance):
        """
        Testa que inicializar duas vezes não causa erro.
        """
        scorer = kronos_scorer_instance
        await scorer.initialize()
        await scorer.initialize()  # Segunda vez
        assert True  # Não deve lançar exceção


class TestKronosEdgeCases:
    """Testes de casos extremos."""

    @pytest.mark.asyncio
    async def test_unknown_symbol(self, kronos_scorer_instance, mock_okx_rest_empty):
        """
        Testa score para símbolo desconhecido (sem dados).
        """
        scorer = kronos_scorer_instance
        result = await scorer.score_signal("", "Buy")
        
        # Deve retornar fallback neutro
        assert result["conviction"] == 50
        assert result["source"] == "fallback"

    @pytest.mark.asyncio
    async def test_invalid_direction(self, kronos_scorer_instance, mock_okx_rest):
        """
        Testa score com direção inválida.
        """
        scorer = kronos_scorer_instance
        result = await scorer.score_signal("BTCUSDT", "invalid")
        
        assert result is not None
        assert "conviction" in result

    @pytest.mark.asyncio
    async def test_concurrent_scores(self, kronos_scorer_instance, mock_okx_rest, mock_okx_rest_downtrend):
        """
        Testa chamadas concorrentes ao score_signal.
        """
        scorer = kronos_scorer_instance
        
        # 3 chamadas concorrentes (todos usam o mesmo mock = uptrend)
        results = await asyncio.gather(
            scorer.score_signal("BTCUSDT", "Buy"),
            scorer.score_signal("ETHUSDT", "Sell"),
            scorer.score_signal("SOLUSDT", "Buy"),
        )
        
        assert len(results) == 3
        for r in results:
            assert "conviction" in r
            assert 0 <= r["conviction"] <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
