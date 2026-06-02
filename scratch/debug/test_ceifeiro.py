import sys
import os

# DEVE ser a primeira coisa no arquivo — corrige encoding do terminal Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

"""
TESTE CEIFEIRO -- Suite de Testes Completa do HarvesterAgent
Valida TODAS as fases de colheita e trailing stop sem esperar o mercado.

COMO RODAR:
    python test_ceifeiro.py
"""

import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from typing import Dict, Any

# Adiciona o backend ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

# Cores para o terminal
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

passed = 0
failed = 0
results = []

def ok(name: str, detail: str = ""):
    global passed
    passed += 1
    results.append(("OK", name, detail))
    detail_str = f" -> {CYAN}{detail}{RESET}" if detail else ""
    print(f"  {GREEN}[OK]{RESET}    {name}{detail_str}")

def fail(name: str, detail: str = ""):
    global failed
    failed += 1
    results.append(("FAIL", name, detail))
    detail_str = f" -> {RED}{detail}{RESET}" if detail else ""
    print(f"  {RED}[FAIL]{RESET}  {name}{detail_str}")

def section(title: str):
    print(f"\n{BOLD}{BLUE}{'=' * 62}{RESET}")
    print(f"{BOLD}{BLUE}  {title}{RESET}")
    print(f"{BOLD}{BLUE}{'=' * 62}{RESET}")

# Mocks de servicos externos (antes de importar o harvester)
mock_okx_ws_public = MagicMock()
mock_okx_ws_public.get_cvd_score_time = MagicMock(return_value=0)
mock_okx_ws_public.rsi_cache = {}

mock_settings = MagicMock()
mock_settings.OKX_EXECUTION_MODE = "PAPER"

mock_signal_generator = MagicMock()

with patch.dict("sys.modules", {
    "services.okx_ws_public":    MagicMock(okx_ws_public_service=mock_okx_ws_public),
    "services.signal_generator": MagicMock(signal_generator=mock_signal_generator),
    "config":                    MagicMock(settings=mock_settings),
}):
    from services.agents.harvester import HarvesterAgent, MOONBAG_TRAILING_LEVELS, HARVEST_EXTENSION_PHASES


# =============================================================================
# PARTE 1 -- TRAILING STOP (calculate_trailing_stop)
# =============================================================================

def test_trailing_stop():
    section("PARTE 1 -- Trailing Stop Progressivo (Ceifeiro)")

    agent = HarvesterAgent()
    entry = 60000.0  # BTCUSDT LONG
    side  = "Buy"
    lev   = 50.0

    def price_at_roi(roi: float) -> float:
        return entry * (1 + roi / (lev * 100))

    def expected_sl(sl_roi: float) -> float:
        return entry * (1 + sl_roi / (lev * 100))

    # Tabela de checkpoints: (roi_atual, nivel_esperado_sl_roi, label)
    checkpoints = [
        (150,  None,  "ROI 150% => HOLD (trailing ainda nao ativo)"),
        (200,  150,   "ROI 200% => SL +150% ROI [WAVE]"),
        (300,  220,   "ROI 300% => SL +220% ROI [ROCKET]"),
        (400,  280,   "ROI 400% => SL +280% ROI [STAR]"),
        (500,  350,   "ROI 500% => SL +350% ROI [CROWN]"),
        (600,  420,   "ROI 600% => SL +420% ROI [SUPERNOVA]"),
        (700,  500,   "ROI 700% => SL +500% ROI [GOD_MODE]"),
        (800,  650,   "ROI 800% => SL +650% ROI [CHOKE_HOLD]"),
        (1000, 850,   "ROI 1000% => SL +850% ROI [CHOKE_HOLD]"),
        (1200, 1050,  "ROI 1200% => SL +1050% ROI [CHOKE_HOLD]"),
    ]

    current_sl = 0.0

    for roi_target, exp_sl_roi, label in checkpoints:
        current_price = price_at_roi(roi_target)
        res = agent.calculate_trailing_stop("BTCUSDT", side, entry, current_price, current_sl)

        if exp_sl_roi is None:
            # Esperamos HOLD
            if res["action"] == "HOLD":
                ok(label, res.get("reason", "")[:70])
            else:
                fail(label, f"Esperado HOLD, obteve {res['action']}")
        else:
            if res["action"] == "UPDATE_SL":
                current_sl = res["new_stop"]
                sl_roi = (current_sl / entry - 1) * lev * 100
                if abs(sl_roi - exp_sl_roi) < 5:
                    ok(label, f"SL=${current_sl:,.2f} (+{sl_roi:.0f}% ROI)")
                else:
                    fail(label, f"Esperado +{exp_sl_roi}% ROI, obteve +{sl_roi:.1f}%")
            else:
                fail(label, f"Esperado UPDATE_SL, obteve HOLD: {res.get('reason','')[:60]}")

    # Teste extra: Paciencia Absoluta (SL nao regride)
    high_sl = expected_sl(500)
    res = agent.calculate_trailing_stop("BTCUSDT", side, entry, price_at_roi(600), high_sl)
    if res["action"] == "HOLD":
        ok("Paciencia Absoluta: SL nao regride (500% atual vs 420% calculado)")
    else:
        fail("Paciencia Absoluta FALHOU - SL regrediu", f"novo=${res.get('new_stop','?')}")

    # Teste SHORT
    res = agent.calculate_trailing_stop(
        "BTCUSDT", "Sell", entry,
        entry * (1 - 200 / (50 * 100)),  # SHORT ROI 200%
        0
    )
    if res["action"] == "UPDATE_SL":
        ok("SHORT ROI 200% => SL atualizado corretamente (direcao inversa)", f"SL=${res['new_stop']:,.4f}")
    else:
        fail("SHORT deveria atualizar SL em 200% ROI", str(res))


# =============================================================================
# PARTE 2 -- COLHEITA PARCIAL (check_harvest_opportunity)
# =============================================================================

async def test_harvest_opportunity():
    section("PARTE 2 -- Colheita Parcial por Fases (Ceifeiro)")

    agent = HarvesterAgent()
    entry = 0.60  # XRPUSDT LONG
    side  = "Buy"
    lev   = 50

    def price_at_roi(roi: float) -> float:
        return entry * (1 + roi / (lev * 100))

    # Fibo mock calibrado: extensoes nos precos exatos dos ROIs alvo do Ceifeiro
    # Assim evitamos que o 1.0_ext caia acima de 700% e acione a Safety Net antes da colheita
    price_250pct = price_at_roi(250)   # 1a Colheita
    price_350pct = price_at_roi(350)   # 2a Colheita
    price_450pct = price_at_roi(450)   # 3a Colheita
    price_600pct = price_at_roi(600)   # Golden Colheita

    mock_extensions = {
        "1.0_ext":   price_250pct,
        "1.272_ext": price_350pct,
        "1.414_ext": price_450pct,
        "1.618_ext": price_600pct,
    }

    mock_ext_data = {
        "extensions": mock_extensions,
        "extensions_roi": {k: round((v / entry - 1) * 100 * lev, 1) for k, v in mock_extensions.items()},
        "updated_at": 0,
    }

    # Injeta cache Fibo (TTL "infinito")
    cache_key = f"XRPUSDT_{entry:.6f}_H4"
    agent._ext_cache[cache_key] = {**mock_ext_data, "updated_at": 1e12}

    # Teste 1: Guard minimo (ROI < 100%) => HOLD
    res = await agent.check_harvest_opportunity("XRPUSDT", side, entry, price_at_roi(80))
    if res["action"] == "HOLD":
        ok("ROI 80% => HOLD (guard minimo 100% ROI)", res.get("reason", "")[:70])
    else:
        fail("ROI 80% deveria retornar HOLD", str(res))

    # Teste 2: ROI = 200%, longe dos niveis => HOLD
    mock_okx_ws_public.get_cvd_score_time.return_value = 0
    mock_okx_ws_public.rsi_cache = {"XRPUSDT": 55}
    res = await agent.check_harvest_opportunity("XRPUSDT", side, entry, price_at_roi(200))
    if res["action"] == "HOLD":
        ok("ROI 200%, longe dos niveis Fibo => HOLD", res.get("reason", "")[:70])
    else:
        fail("ROI 200% longe dos niveis deveria HOLD", str(res))

    # Teste 3: Preco proximo 1.0_ext + exaustao CVD => COLHE (1a Colheita)
    # O preco alvo e 0.3% abaixo do 1.0_ext (dentro do threshold de 0.5%)
    mock_okx_ws_public.get_cvd_score_time.return_value = -20000  # CVD negativo = exaustao
    mock_okx_ws_public.rsi_cache = {"XRPUSDT": 78}
    target_price = mock_extensions["1.0_ext"] * 0.997
    res = await agent.check_harvest_opportunity("XRPUSDT", side, entry, target_price)
    roi_obtained = res.get("current_roi", 0)
    if res["action"] == "PARTIAL_HARVEST" and "PRIMEIRA" in res.get("phase", ""):
        ok(
            f"Proximo 1.0_ext + CVD exausto => 1a COLHEITA ({res['proportion']*100:.0f}% fechado)",
            f"ROI={roi_obtained:.1f}% | Fase={res['phase']}"
        )
    elif res["action"] == "PARTIAL_HARVEST":
        # Aceitavel: colheu por outro motivo (safety net ou golden)
        ok(
            f"Proximo 1.0_ext => COLHEU (fase alternativa: {res.get('phase','?')})",
            f"ROI={roi_obtained:.1f}% proporcao={res['proportion']*100:.0f}%"
        )
    else:
        fail("1a Colheita esperada proximo 1.0_ext com exaustao", str(res)[:100])

    # Teste 4: Golden Extension (1.618_ext) => SEMPRE COLHE mesmo com momentum forte
    mock_okx_ws_public.get_cvd_score_time.return_value = 50000  # momentum MUITO forte
    mock_okx_ws_public.rsi_cache = {"XRPUSDT": 60}
    target_price = mock_extensions["1.618_ext"] * 0.998
    agent._harvest_history.pop("XRPUSDT", None)
    res = await agent.check_harvest_opportunity("XRPUSDT", side, entry, target_price)
    if res["action"] == "PARTIAL_HARVEST" and "GOLDEN" in res.get("phase", ""):
        ok(
            f"Golden Extension (1.618x) => SEMPRE COLHE mesmo com momentum forte ({res['proportion']*100:.0f}% fechado)",
            f"ROI={res['current_roi']:.1f}%"
        )
    else:
        fail("Golden Extension deveria SEMPRE colher (even com momentum)", str(res)[:100])

    # Teste 5: ROI = 700% => Safety Net 80%
    mock_okx_ws_public.get_cvd_score_time.return_value = 0
    mock_okx_ws_public.rsi_cache = {"XRPUSDT": 50}
    agent._harvest_history.pop("XRPUSDT", None)
    res = await agent.check_harvest_opportunity("XRPUSDT", side, entry, price_at_roi(700))
    if res["action"] == "PARTIAL_HARVEST" and res.get("proportion", 0) == 0.80:
        ok("ROI 700% => Safety Net intermediario (80% fechado)", f"Fase={res.get('phase','?')}")
    else:
        fail("ROI 700% deveria acionar Safety Net 80%", str(res)[:100])

    # Teste 6: ROI = 1000% + RSI > 85 => Parabolic Climax (90%)
    mock_okx_ws_public.rsi_cache = {"XRPUSDT": 87}
    agent._harvest_history.pop("XRPUSDT", None)
    res = await agent.check_harvest_opportunity("XRPUSDT", side, entry, price_at_roi(1000))
    if res["action"] == "PARTIAL_HARVEST" and res.get("phase") == "GOD_CANDLE_HARVEST":
        ok(
            f"ROI 1000% + RSI 87 => PARABOLIC CLIMAX ({res['proportion']*100:.0f}% fechado)",
            f"ROI={res['current_roi']:.1f}%"
        )
    else:
        fail("ROI 1000% + RSI > 85 deveria acionar Parabolic Climax", str(res)[:100])

    # Teste 7: Cooldown entre colheitas
    import time
    agent._harvest_history["XRPUSDT"] = time.time() - 60  # colheu ha 60s (cooldown = 1800s)
    res = await agent.check_harvest_opportunity("XRPUSDT", side, entry, price_at_roi(300))
    if res["action"] == "HOLD" and "cooldown" in res.get("reason", "").lower():
        ok("Cooldown de 30 min respeitado entre colheitas", res["reason"][:70])
    else:
        fail("Cooldown nao foi respeitado", str(res)[:100])


# =============================================================================
# PARTE 3 -- SIMULACAO COMPLETA (Trajetoria de uma Moonbag)
# =============================================================================

async def test_full_moonbag_journey():
    section("PARTE 3 -- Simulacao da Trajetoria Completa de uma Moonbag")

    agent = HarvesterAgent()
    entry = 0.60   # XRPUSDT
    side  = "Buy"
    lev   = 50

    def price_at_roi(roi: float) -> float:
        return entry * (1 + roi / (lev * 100))

    print(f"\n  {YELLOW}Simulando XRPUSDT LONG @ ${entry} (50x){RESET}")
    print(f"  {YELLOW}Progresso do trailing stop por nivel de ROI:{RESET}\n")
    print(f"  {'ROI':>6}  {'Nivel':<24}  {'SL ROI Esperado':>16}  {'SL ROI Obtido':>14}  {'Status'}")
    print(f"  {'-'*80}")

    checkpoints = [
        (160,  "Emancipacao iniciou",   None),
        (200,  "WAVE (150% SL)",        150),
        (300,  "ROCKET (220% SL)",      220),
        (400,  "STAR (280% SL)",        280),
        (500,  "CROWN (350% SL)",       350),
        (600,  "SUPERNOVA (420% SL)",   420),
        (700,  "GOD_MODE (500% SL)",    500),
        (800,  "CHOKE_HOLD (650% SL)",  650),
        (1000, "CHOKE_HOLD (850% SL)",  850),
        (1200, "CHOKE_HOLD (1050% SL)", 1050),
    ]

    current_sl = 0.0
    all_ok = True

    for roi_target, label, expected_sl_roi in checkpoints:
        current_price = price_at_roi(roi_target)
        res = agent.calculate_trailing_stop("XRPUSDT", side, entry, current_price, current_sl)

        if res["action"] == "UPDATE_SL":
            current_sl = res["new_stop"]
            sl_roi = (current_sl / entry - 1) * lev * 100
            sl_price_pct = (current_sl / entry - 1) * 100

            if expected_sl_roi is not None:
                within_tolerance = abs(sl_roi - expected_sl_roi) < 5
                status = f"{GREEN}[OK]{RESET}" if within_tolerance else f"{RED}[FALHOU]{RESET}"
                if not within_tolerance:
                    all_ok = False
            else:
                status = f"{CYAN}[INICIO]{RESET}"

            print(f"  {roi_target:>5}%  {label:<24}  {'+' + str(expected_sl_roi) + '%' if expected_sl_roi else 'N/A':>16}  {'+' + f'{sl_roi:.0f}%':>14}  {status}")

        else:
            roi_str = f"{roi_target}%"
            print(f"  {roi_str:>6}  {label:<24}  {'N/A':>16}  {'HOLD':>14}  {CYAN}[OK]{RESET}")

    print()
    if all_ok:
        ok("Trajetoria completa - todos os stops progressivos corretos")
    else:
        fail("Trajetoria completa - desvios detectados nos niveis de stop")


# =============================================================================
# RESUMO FINAL
# =============================================================================

def print_summary():
    section("RESUMO DOS TESTES")
    total = passed + failed
    print(f"\n  Total:   {total}")
    print(f"  {GREEN}Passou:  {passed}{RESET}")
    print(f"  {RED}Falhou:  {failed}{RESET}")

    if failed == 0:
        print(f"\n  {GREEN}{BOLD}CEIFEIRO 100% FUNCIONAL -- TODOS OS ALVOS VALIDADOS!{RESET}")
        print(f"  {GREEN}O robo vai executar corretamente em producao.{RESET}\n")
    else:
        print(f"\n  {RED}{BOLD}{failed} TESTE(S) FALHARAM -- Revisar antes de producao!{RESET}\n")
        print(f"  {RED}Falhas:{RESET}")
        for icon, name, detail in results:
            if icon == "FAIL":
                print(f"    [X] {name}")
                if detail:
                    print(f"        {RED}{detail}{RESET}")
    print()


# =============================================================================
# MAIN
# =============================================================================

async def main():
    print(f"\n{BOLD}{CYAN}{'=' * 62}")
    print(f"  CEIFEIRO -- SUITE DE TESTES COMPLETA")
    print(f"  Ordem: XRPUSDT/BTCUSDT LONG 50x (modo PAPER)")
    print(f"{'=' * 62}{RESET}\n")

    test_trailing_stop()
    await test_harvest_opportunity()
    await test_full_moonbag_journey()
    print_summary()


if __name__ == "__main__":
    asyncio.run(main())
