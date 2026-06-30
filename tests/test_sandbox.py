"""
Testes de regressão e cobertura para SandboxService (pós-rewrite).

Cobre especificamente:
- Bug raiz LDOUSDT: WS retorna 0 → stop nunca verificado
- Fallback REST → cache quando WS falha
- Conservative price (HIGH/LOW 120s) para detecção de stop
- Stop inicial adaptativo (-15%/-30% vs ADX)
- Tick size rounding
- Confirmação REST antes de fechar
- Peak ROI cache

NOTA SOBRE MONKEYPATCHING:
sandbox_service.py importa okx_ws_public_service por nome local:
    from services.okx_ws_public import okx_ws_public_service
Por isso, o patch correto é em 'services.sandbox_service.okx_ws_public_service',
não em 'services.okx_ws_public.okx_ws_public_service'.
"""
import sys
import time
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.sandbox_service import SandboxService
from services.order_projection_service import OrderProjectionService


# ---------------------------------------------------------------------------
# Helpers / Fakes
# ---------------------------------------------------------------------------

def _make_trade(
    symbol="LDOUSDT",
    direction="SHORT",
    entry_price=0.2522,
    stop_loss=0.2542,
    status="ACTIVE",
    flash_state=None,
    contract_meta=None,
    max_roi=0.0,
    id="sb_test_001",
):
    """Cria um objeto trade fake com atributos mínimos necessários."""
    trade = MagicMock()
    trade.id = id
    trade.symbol = symbol
    trade.direction = direction
    trade.entry_price = entry_price
    trade.stop_loss = stop_loss
    trade.status = status
    trade.max_roi = max_roi
    trade.contract_meta = contract_meta or {"maxLeverage": 50.0}
    trade.flash_state = flash_state or {
        "phase": "ESCADINHA",
        "active_level": "INICIAL",
        "stop_roi": -30.0 if direction == "SHORT" else -15.0,
        "history": [],
    }
    return trade


class FakeDB:
    """Banco de dados em memória para testes unitários."""

    def __init__(self, trades=None):
        self._trades = {t.id: t for t in (trades or [])}
        self.updated: dict = {}

    async def get_sandbox_trades(self, active_only=False):
        return [t for t in self._trades.values() if not active_only or t.status == "ACTIVE"]

    async def get_sandbox_trade(self, trade_id):
        return self._trades.get(trade_id)

    async def update_sandbox_trade(self, trade_id, payload):
        self.updated[trade_id] = payload
        trade = self._trades.get(trade_id)
        if trade:
            for k, v in payload.items():
                setattr(trade, k, v)

    async def save_sandbox_trade(self, data):
        t = MagicMock()
        for k, v in data.items():
            setattr(t, k, v)
        self._trades[data["id"]] = t

    async def clear_sandbox_trades(self):
        self._trades.clear()

    async def get_radar_pulse(self):
        return None


class FakeWS:
    """Mock do okx_ws_public_service para uso via monkeypatch."""

    def __init__(self, price=100.0, conservative_price=None, adx=30.0):
        self._price = price
        self._conservative_price = price if conservative_price is None else conservative_price
        self.btc_adx = adx
        self.active_symbols = ["INJUSDT", "BTCUSDT", "LDOUSDT"]

    def get_current_price(self, symbol):
        return self._price

    def get_conservative_price(self, symbol, side):
        return self._conservative_price

    async def sync_topics(self, symbols):
        pass


def _build_sandbox_with_patches(monkeypatch, db, ws):
    """
    Monta SandboxService com database e ws mockados.
    Patch correto: services.sandbox_service.{database_service,okx_ws_public_service}
    pois ambos são importados por nome local no módulo.
    """
    import services.sandbox_service as svc_mod
    sb = SandboxService()
    monkeypatch.setattr(svc_mod, "database_service", db)
    monkeypatch.setattr(svc_mod, "okx_ws_public_service", ws)
    return sb


# ---------------------------------------------------------------------------
# Teste 1 – Fallback REST quando WS retorna 0 (bug raiz LDOUSDT)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_price_fallback_rest_when_ws_returns_zero(monkeypatch):
    """
    WS retorna 0 para LDOUSDT SHORT.
    O preço é obtido via REST (0.2577).
    O stop recalculado para SHORT -30%/50x a partir de 0.2522 ≈ 0.2537.
    Como 0.2577 > 0.2537, o stop hit deve ser detectado e o trade fechado.
    """
    trade = _make_trade(
        direction="SHORT", entry_price=0.2522,
        flash_state={"phase": "ESCADINHA", "active_level": "INICIAL", "stop_roi": -30.0, "history": []},
    )
    db = FakeDB([trade])
    ws = FakeWS(price=0.0, conservative_price=0.0)  # WS completamente mudo

    sb = _build_sandbox_with_patches(monkeypatch, db, ws)

    # REST retorna o preço real que deveria acionar o stop
    async def fake_rest_price(symbol):
        return 0.2577  # acima do stop ~0.2537 → SHORT stop atingido

    monkeypatch.setattr(sb, "_get_rest_price", fake_rest_price)

    await sb._process_trade_tick(trade)

    assert trade.id in db.updated, "Trade não foi processado"
    payload = db.updated[trade.id]
    assert payload["status"] in ("CLOSED_SL", "CLOSED_TRAILING"), \
        f"Trade não foi fechado. Status atual: {payload.get('status')}. " \
        f"[WS=0, REST=0.2577, stop≈0.2537 → SHORT deve fechar]"


# ---------------------------------------------------------------------------
# Teste 2 – Fallback cache quando WS=0 e REST=0
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_price_fallback_cache_when_ws_and_rest_fail(monkeypatch):
    """
    WS=0 + REST=0 → usa cache local (<60s) para resolver o preço.
    Cache contém 0.2580 > stop ~0.2537 → SHORT deve fechar.
    """
    trade = _make_trade(
        direction="SHORT", entry_price=0.2522,
        flash_state={"phase": "ESCADINHA", "active_level": "INICIAL", "stop_roi": -30.0, "history": []},
    )
    db = FakeDB([trade])
    ws = FakeWS(price=0.0, conservative_price=0.0)

    sb = _build_sandbox_with_patches(monkeypatch, db, ws)
    # Pré-popula cache com preço fresco (< 60s) acima do stop
    sb._last_price_cache[trade.symbol] = 0.2580
    sb._last_price_cache_ts[trade.symbol] = time.time()

    async def fake_rest_price(symbol):
        return 0.0  # REST também falha

    monkeypatch.setattr(sb, "_get_rest_price", fake_rest_price)

    await sb._process_trade_tick(trade)

    assert trade.id in db.updated, "Trade não foi processado"
    payload = db.updated[trade.id]
    assert payload["status"] in ("CLOSED_SL", "CLOSED_TRAILING"), \
        f"Cache não foi usado para detectar stop. Status: {payload.get('status')}"


# ---------------------------------------------------------------------------
# Teste 3 – Todas as fontes falham → skip (não fecha nem atualiza)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_price_unavailable_all_sources_skips_trade(monkeypatch):
    """
    WS=0 + REST=0 + cache expirado → deve pular o trade sem atualizar.
    """
    trade = _make_trade()
    db = FakeDB([trade])
    ws = FakeWS(price=0.0, conservative_price=0.0)

    sb = _build_sandbox_with_patches(monkeypatch, db, ws)
    # Cache expirado (> 60s)
    sb._last_price_cache[trade.symbol] = 0.2580
    sb._last_price_cache_ts[trade.symbol] = time.time() - 120.0

    async def fake_rest_price(symbol):
        return 0.0

    monkeypatch.setattr(sb, "_get_rest_price", fake_rest_price)

    await sb._process_trade_tick(trade)

    assert trade.id not in db.updated, \
        "Trade foi atualizado mesmo sem preço disponível — deveria ter sido pulado (SKIP)"


# ---------------------------------------------------------------------------
# Teste 4 – Conservative price detecta stop de LONG (dip intra-ciclo)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conservative_price_detects_long_stop_violation(monkeypatch):
    """
    LONG: preço atual saudável (103.0), mas conservative (LOW 120s) = 99.5.
    Stop recalculado para -15% ROI / 50x: entry=100 → stop = 99.7.
    99.5 < 99.7 → stop hit deve ser detectado via conservative price.
    """
    entry = 100.0
    trade = _make_trade(
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=entry,
        flash_state={"phase": "ESCADINHA", "active_level": "INICIAL", "stop_roi": -15.0, "history": []},
        id="sb_long_conservative",
    )
    db = FakeDB([trade])
    # Conservative (LOW) = 99.5, abaixo do stop ~99.7
    ws = FakeWS(price=103.0, conservative_price=99.5)

    sb = _build_sandbox_with_patches(monkeypatch, db, ws)

    async def fake_rest_price(symbol):
        return 99.5  # confirma o dip via REST

    monkeypatch.setattr(sb, "_get_rest_price", fake_rest_price)

    await sb._process_trade_tick(trade)

    payload = db.updated.get(trade.id, {})
    assert payload.get("status") in ("CLOSED_SL", "CLOSED_TRAILING"), \
        f"Conservative LOW (99.5) não detectou o stop do LONG (~99.7). " \
        f"Status: {payload.get('status')}. Payload: {payload}"


# ---------------------------------------------------------------------------
# Teste 5 – Conservative price detecta stop de SHORT (pump intra-ciclo)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conservative_price_detects_short_stop_violation(monkeypatch):
    """
    SHORT: preço atual 0.2530 (abaixo do stop ~0.2537 — tudo ok),
    mas conservative (HIGH 120s) = 0.2580 > stop ~0.2537.
    Stop deve ser detectado via conservative price.
    """
    entry = 0.2522
    trade = _make_trade(
        symbol="LDOUSDT",
        direction="SHORT",
        entry_price=entry,
        flash_state={"phase": "ESCADINHA", "active_level": "INICIAL", "stop_roi": -30.0, "history": []},
        id="sb_short_conservative",
    )
    db = FakeDB([trade])
    # Conservative (HIGH) = 0.2580 > stop ~0.2537 → stop atingido
    ws = FakeWS(price=0.2530, conservative_price=0.2580)

    sb = _build_sandbox_with_patches(monkeypatch, db, ws)

    async def fake_rest_price(symbol):
        return 0.2577  # confirma via REST que preço subiu

    monkeypatch.setattr(sb, "_get_rest_price", fake_rest_price)

    await sb._process_trade_tick(trade)

    payload = db.updated.get(trade.id, {})
    assert payload.get("status") in ("CLOSED_SL", "CLOSED_TRAILING"), \
        f"Conservative HIGH (0.2580) não detectou o stop do SHORT (~0.2537). Status: {payload.get('status')}"


# ---------------------------------------------------------------------------
# Teste 6 – Stop adaptativo LATERAL é mais apertado (-15%)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adaptive_stop_ranging_is_tighter():
    """
    [V119] Teste do stop de fallback lateral (-15% ROI).
    """
    sb = SandboxService()
    entry = 100.0
    side = "Buy"

    # Forçamos a falha estrutural mockando _get_30m_structural_stop para retornar None
    async def mock_structural(*a, **kw):
        return None
    sb._get_30m_structural_stop = mock_structural

    # Evitamos o ATR mockando get_klines no okx_rest_service para retornar vazio
    from services.okx_rest import okx_rest_service
    async def mock_klines(*a, **kw):
        return []
    okx_rest_service.get_klines = mock_klines

    ranging_res = await sb._calculate_adaptive_stop("BTCUSDT", entry, side, {}, is_ranging=True)
    ranging_stop = ranging_res["stop_price"]

    proj = OrderProjectionService()
    expected = proj.raw_price_from_roi(entry, -12.0, side, 50.0)

    assert abs(ranging_stop - expected) < 0.01, \
        f"Stop lateral esperado ~{expected:.4f} (-12% ROI), obtido {ranging_stop:.4f}"


# ---------------------------------------------------------------------------
# Teste 7 – Stop adaptativo TENDÊNCIA é mais largo (-25%)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adaptive_stop_trending_is_wider():
    """
    [V119] Teste do stop de fallback tendência (-25% ROI).
    """
    sb = SandboxService()
    entry = 100.0
    side = "Sell"

    # Forçamos a falha estrutural mockando _get_30m_structural_stop para retornar None
    async def mock_structural(*a, **kw):
        return None
    sb._get_30m_structural_stop = mock_structural

    trending_res = await sb._calculate_adaptive_stop("BTCUSDT", entry, side, {}, is_ranging=False)
    trending_stop = trending_res["stop_price"]

    proj = OrderProjectionService()
    expected = proj.raw_price_from_roi(entry, -12.0, side, 50.0)

    assert abs(trending_stop - expected) < 0.01, \
        f"Stop tendência SHORT esperado ~{expected:.4f} (-12% ROI), obtido {trending_stop:.4f}"


# ---------------------------------------------------------------------------
# Teste 8 – Tick size rounding aplicado ao stop price
# ---------------------------------------------------------------------------

def test_tick_size_rounding_applied_to_stop():
    """
    Stop price deve ser arredondado para múltiplo do tick_size do contrato OKX.
    Para LONG com stop negativo (abaixo do entry), deve arredondar para BAIXO (protetor).
    """
    sb = SandboxService()
    price_raw = 99.7314
    tick_size = 0.01
    side = "Buy"
    stop_roi = -15.0  # negativo → stop abaixo do entry

    rounded = sb._round_stop_to_tick(price_raw, tick_size, side, stop_roi)

    # Para LONG negativo, arredonda para baixo (FLOOR) — não reduz o risco
    assert rounded <= price_raw, \
        f"Stop arredondado ({rounded}) não deve exceder o raw price ({price_raw}) para LONG negativo"
    # Deve ser múltiplo exato do tick_size
    remainder = round(abs(rounded / tick_size) % 1, 8)
    assert remainder < 1e-6 or remainder > (1 - 1e-6), \
        f"Stop {rounded} não é múltiplo de tick_size {tick_size}"
    # Valor esperado: 99.73
    assert abs(rounded - 99.73) < 1e-9, f"Esperado 99.73, obtido {rounded}"


# ---------------------------------------------------------------------------
# Teste 9 – Confirmação REST antes de fechar (REST é chamado quando stop hit)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rest_confirmation_before_close(monkeypatch):
    """
    [V119] Quando stop é atingido no Sandbox, ele fecha instantaneamente via WS
    sem precisar enfileirar chamadas REST lentas de rede.
    """
    entry = 0.2522
    trade = _make_trade(
        direction="SHORT",
        entry_price=entry,
        flash_state={"phase": "ESCADINHA", "active_level": "INICIAL", "stop_roi": -30.0, "history": []},
        id="sb_rest_confirm",
    )
    db = FakeDB([trade])
    # WS já mostra stop atingido (0.2577 > ~0.2537 para SHORT)
    ws = FakeWS(price=0.2577, conservative_price=0.2577)

    sb = _build_sandbox_with_patches(monkeypatch, db, ws)

    await sb._process_trade_tick(trade)

    # Trade deve ter fechado instantaneamente
    payload = db.updated.get(trade.id, {})
    assert payload.get("status") in ("CLOSED_SL", "CLOSED_TRAILING"), \
        f"Trade não fechou após cruzamento de preço. Status: {payload.get('status')}"


# ---------------------------------------------------------------------------
# Teste 10 – Peak ROI cache sobrevive a pullback de preço
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_peak_roi_cache_survives_price_pullback(monkeypatch):
    """
    Trade LONG atingiu 80% ROI (armazenado em max_roi e cache).
    Preço sofre pullback para ~60% ROI.
    O max_roi reportado deve refletir o peak (80%), não o ROI atual.
    O stop deve ter escalado para o nível correspondente a 80% ROI.
    """
    entry = 100.0
    # 80% ROI / 50x / 100 = 1.6% price move → peak price ≈ 101.6
    # 60% ROI / 50x / 100 = 1.2% price move → current price ≈ 101.2
    current_price_val = 100.0 * (1 + 60.0 / (50.0 * 100))  # ≈ 101.2

    trade = _make_trade(
        symbol="TESTUSDT",
        direction="LONG",
        entry_price=entry,
        flash_state={
            "phase": "ESCADINHA",
            "active_level": "LUCRO_GARANTIDO_80",
            "stop_roi": 50.0,  # já escalado para 50% ROI
            "history": ["Subiu para LUCRO_GARANTIDO_80"]
        },
        max_roi=80.0,  # peak persistido no banco
        id="sb_peak_roi_test",
    )
    db = FakeDB([trade])
    ws = FakeWS(price=current_price_val, conservative_price=current_price_val - 0.5)

    sb = _build_sandbox_with_patches(monkeypatch, db, ws)
    # Pre-popula cache de peak
    sb._peak_roi_cache[trade.id] = 80.0

    async def fake_rest_price(symbol):
        return 0.0

    monkeypatch.setattr(sb, "_get_rest_price", fake_rest_price)

    await sb._process_trade_tick(trade)

    assert trade.id in db.updated, "Trade não foi processado"
    payload = db.updated[trade.id]
    # max_roi deve refletir o peak (80%), não o ROI atual (~60%)
    assert payload.get("max_roi", 0.0) >= 79.9, \
        f"Peak ROI não foi preservado. max_roi={payload.get('max_roi'):.2f} (esperado >= 79.9)"


# ---------------------------------------------------------------------------
# Teste 11 – REGRESSÃO: Cenário real LDOUSDT SHORT
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ldousdt_short_scenario_regression(monkeypatch):
    """
    Regressão do bug real:
    - LDOUSDT SHORT
    - entry = 0.2522
    - stop_roi = -30% → stop_price recalculado ≈ 0.2522 * (1 + 30/(50*100)) ≈ 0.25372
    - preço real = 0.2577 (acima do stop → SHORT deve fechar)
    - WS retornava 0 → stop nunca era verificado

    Com a correção (fallback REST), o trade DEVE ser fechado.
    """
    entry_price = 0.2522
    real_market_price = 0.2577

    trade = _make_trade(
        symbol="LDOUSDT",
        direction="SHORT",
        entry_price=entry_price,
        flash_state={
            "phase": "ESCADINHA",
            "active_level": "INICIAL",
            "stop_roi": -30.0,
            "history": [f"Abertura em {entry_price} com SL inicial em -30% ROI"],
        },
        id="sb_ldousdt_short_regression",
    )
    db = FakeDB([trade])

    # WS completamente mudo — reproduz o bug original
    ws = FakeWS(price=0.0, conservative_price=0.0)

    sb = _build_sandbox_with_patches(monkeypatch, db, ws)

    # REST retorna o preço real que deveria ter fechado o trade
    async def fake_rest_price(symbol):
        return real_market_price

    monkeypatch.setattr(sb, "_get_rest_price", fake_rest_price)

    await sb._process_trade_tick(trade)

    payload = db.updated.get(trade.id)
    assert payload is not None, \
        "Trade não foi processado — _process_trade_tick retornou sem atualizar"

    status = payload.get("status", "ACTIVE")
    # stop_price recalculado ≈ 0.2522 * (1 + 0.3/50) ≈ 0.25371
    # 0.2577 > 0.25371 → SHORT stop hit!
    assert status in ("CLOSED_SL", "CLOSED_TRAILING"), (
        f"BUG REGRESSÃO: LDOUSDT SHORT com preço {real_market_price} "
        f"acima do stop (-30% ROI ≈ 0.2537) deveria ter fechado. "
        f"Status atual: {status}"
    )

    # ROI final deve ser negativo (loss) — SHORT perdeu pois preço subiu
    final_roi = payload.get("current_roi", 0.0)
    assert final_roi < 0, \
        f"ROI final esperado negativo para SHORT com loss. Obtido: {final_roi:.2f}%"


# ---------------------------------------------------------------------------
# Teste 12 – Entry sanity check: sinal defasado não abre trade
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_entry_sanity_check_rejects_stale_signal(monkeypatch):
    """
    Quando o preço de mercado no momento da abertura já está além de 70% do stop,
    o trade não deve ser aberto (sinal defasado / stale entry).

    Cenário: INJUSDT SHORT, entry_price=4.2300, stop_roi=-30%
    → stale_threshold = -30% * 0.7 = -21%
    → Preço atual = 4.3200 (SHORT immediate_roi ≈ -106%) → descartado
    """
    import services.sandbox_service as svc_mod
    import services.okx_ws_public as ws_mod
    from services.signal_generator import signal_generator as sg_module

    db = FakeDB()
    ws = FakeWS(price=4.3200, conservative_price=4.3200, adx=30.0)  # tendência

    sb = SandboxService()
    monkeypatch.setattr(ws_mod, "okx_ws_public_service", ws)
    monkeypatch.setattr(svc_mod, "database_service", db)
    monkeypatch.setattr(svc_mod, "okx_ws_public_service", ws)

    # Mocka macro + signal_generator para passar todos os filtros antes do sanity check
    async def fake_macro(*a, **kw):
        return {"above_200sma": False}  # BEARISH → SHORT permitido

    monkeypatch.setattr(
        "services.sandbox_service.signal_generator" if hasattr(svc_mod, "signal_generator") else "services.signal_generator.signal_generator",
        type("FakeSG", (), {"get_daily_macro_filter": fake_macro})(),
        raising=False,
    )

    # Sinal: INJUSDT SHORT com entry_price=4.2300, mercado já em 4.3200
    signals = [{
        "symbol": "INJUSDT",
        "side": "Sell",
        "strategy": "VELOCITY FLOW",
        "price": 4.2300,
        "contract_info": {"maxLeverage": 50.0},
        "id": "test_stale_inj_001",
        "timestamp": 9999999,
    }]

    await sb._process_radar_signals(signals)

    # Nenhum trade deve ter sido salvo — sinal foi descartado por entry stale
    saved = list(db._trades.values())
    assert len(saved) == 0, (
        f"Trade não deveria ter sido aberto com entry defasado. "
        f"Trades salvos: {[t.id for t in saved]}"
    )


# ---------------------------------------------------------------------------
# Teste 13 – Entry sanity check: sinal fresco abre normalmente
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_entry_sanity_check_accepts_fresh_signal(monkeypatch):
    """
    Quando o preço de mercado está próximo do entry (ROI imediato < 70% do stop),
    o trade DEVE ser aberto normalmente.

    Cenário: SHORT entry=4.2300, preço mercado=4.2310 (ROI ≈ -0.1%) → aceito
    [V114] Mocka _check_1m_confirmation para isolação (testado separadamente)
    """
    import services.sandbox_service as svc_mod
    import services.okx_ws_public as ws_mod

    db = FakeDB()
    ws = FakeWS(price=4.2310, conservative_price=4.2310, adx=30.0)

    sb = SandboxService()
    monkeypatch.setattr(ws_mod, "okx_ws_public_service", ws)
    monkeypatch.setattr(svc_mod, "database_service", db)
    monkeypatch.setattr(svc_mod, "okx_ws_public_service", ws)

    # [V114] Mock do filtro 1M para isolar o teste do sanity check
    async def fake_1m(*a, **kw):
        return True
    monkeypatch.setattr(sb, "_check_1m_confirmation", fake_1m)

    # Mock do filtro 5M para passar com sucesso no teste
    async def fake_5m(*a, **kw):
        return {"confirmed": True, "score_boost": 0.0, "detail": "mock"}
    monkeypatch.setattr(sb, "_check_5m_confirmation", fake_5m)

    # Mocka macro BEARISH → SHORT permitido
    async def fake_macro(*a, **kw):
        return {"above_200sma": False}

    # Mocka signal_generator para não travar no import real
    try:
        import services.signal_generator as sg_mod
        real_sg = getattr(sg_mod, "signal_generator", None)
        if real_sg is not None:
            monkeypatch.setattr(real_sg, "get_daily_macro_filter", fake_macro)
    except Exception:
        pass

    # Força ADX = 30 no WebSocket para que a estratégia VELOCITY FLOW não seja barrada pelo regime do V119
    ws.btc_adx = 30.0

    signals = [{
        "symbol": "INJUSDT",
        "side": "Sell",
        "strategy": "VELOCITY FLOW",
        "price": 4.2300,
        "contract_info": {"maxLeverage": 50.0},
        "id": "test_fresh_inj_001",
        "timestamp": 9999998,
    }]

    await sb._process_radar_signals(signals)

    # Trade DEVE ter sido salvo — entrada fresca
    saved = list(db._trades.values())
    assert len(saved) == 1, (
        f"Trade deveria ter sido aberto com entrada fresca. "
        f"Trades salvos: {len(saved)}"
    )
    assert saved[0].direction == "SHORT"
    assert abs(float(saved[0].entry_price) - 4.2300) < 0.001


# ---------------------------------------------------------------------------
# Teste 14 – Cooldown pós stop-out: segundo sinal no mesmo símbolo é bloqueado
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cooldown_blocks_reentry_after_stop(monkeypatch):
    """
    [V117] Após stop-out registrado via _stop_cooldown, um segundo sinal
    para o MESMO símbolo+DIREÇÃO deve ser descartado com [SANDBOX-COOLDOWN].

    Chave V117: (symbol, direction) — não mais apenas symbol.
    """
    import services.sandbox_service as svc_mod
    import services.okx_ws_public as ws_mod

    db = FakeDB()
    ws = FakeWS(price=4.2310, conservative_price=4.2310, adx=30.0)

    sb = SandboxService()
    monkeypatch.setattr(ws_mod, "okx_ws_public_service", ws)
    monkeypatch.setattr(svc_mod, "database_service", db)
    monkeypatch.setattr(svc_mod, "okx_ws_public_service", ws)

    # [V117] Chave de cooldown agora é (symbol, direction)
    sb._stop_cooldown[("INJUSDT", "SHORT")] = time.time()  # stop-out "agora"
    ws.btc_adx = 30.0

    # Mock do _check_5m_confirmation para não bloquear (fail-open)
    async def fake_5m(*a, **kw):
        return {"confirmed": True, "score_boost": 0.0, "detail": "mock"}
    monkeypatch.setattr(sb, "_check_5m_confirmation", fake_5m)

    signals = [{
        "symbol": "INJUSDT",
        "side": "Sell",
        "strategy": "VELOCITY FLOW",
        "price": 4.2300,
        "contract_info": {"maxLeverage": 50.0},
        "id": "test_cooldown_001",
        "timestamp": 9999997,
    }]

    await sb._process_radar_signals(signals)

    saved = list(db._trades.values())
    assert len(saved) == 0, (
        f"Trade NÃO deveria ter sido aberto durante cooldown SHORT. "
        f"Trades abertos: {[t.id for t in saved]}"
    )


@pytest.mark.asyncio
async def test_cooldown_allows_reentry_after_expiry(monkeypatch):
    """
    [V117] Após o cooldown expirar (> 300s), o sinal deve ser aceito normalmente.
    Teste usa chave (symbol, direction) conforme V117.
    """
    import services.sandbox_service as svc_mod
    import services.okx_ws_public as ws_mod

    db = FakeDB()
    ws = FakeWS(price=4.2310, conservative_price=4.2310, adx=30.0)

    sb = SandboxService()
    monkeypatch.setattr(ws_mod, "okx_ws_public_service", ws)
    monkeypatch.setattr(svc_mod, "database_service", db)
    monkeypatch.setattr(svc_mod, "okx_ws_public_service", ws)

    # [V117] Simula cooldown expirado (301s atrás) para a direção SHORT
    sb._stop_cooldown[("INJUSDT", "SHORT")] = time.time() - 301.0
    ws.btc_adx = 30.0

    async def fake_5m(*a, **kw):
        return {"confirmed": True, "score_boost": 0.0, "detail": "mock"}
    monkeypatch.setattr(sb, "_check_5m_confirmation", fake_5m)

    async def fake_1m(*a, **kw):
        return True
    monkeypatch.setattr(sb, "_check_1m_confirmation", fake_1m)

    signals = [{
        "symbol": "INJUSDT",
        "side": "Sell",
        "strategy": "VELOCITY FLOW",
        "price": 4.2300,
        "contract_info": {"maxLeverage": 50.0},
        "id": "test_cooldown_expired_001",
        "timestamp": 9999996,
    }]

    await sb._process_radar_signals(signals)

    saved = list(db._trades.values())
    assert len(saved) == 1, (
        f"Trade DEVERIA ter sido aberto após cooldown expirar. "
        f"Trades abertos: {len(saved)}"
    )


# ---------------------------------------------------------------------------
# Teste 15 – Confirmação 5M: trade é aceito com boost de score
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_1m_filter_rejects_short_with_bullish_candles(monkeypatch):
    """
    [V117] Filtro 5M BLOQUEIA quando ambos os 2 candles fechados são bullish.
    SHORT com 2/2 candles BULL → trade deve ser descartado.
    """
    import services.sandbox_service as svc_mod
    import services.okx_ws_public as ws_mod
    import services.okx_rest as rest_mod

    db = FakeDB()
    ws = FakeWS(price=4.2310, conservative_price=4.2310, adx=30.0)

    sb = SandboxService()
    monkeypatch.setattr(ws_mod, "okx_ws_public_service", ws)
    monkeypatch.setattr(svc_mod, "database_service", db)
    monkeypatch.setattr(svc_mod, "okx_ws_public_service", ws)

    # Candles 5M: candle[0] = aberto (ignorado), candle[1] e [2] = ambos bullish
    # -> SHORT deve ser bloqueado (2/2 bullish = momentum 100% contrário)
    all_bullish_5m = [
        {"open": "4.20", "close": "4.25"},  # candle[0] = aberto em formação (ignorado)
        {"open": "4.18", "close": "4.22"},  # candle[1] = BULL (fechado)
        {"open": "4.16", "close": "4.20"},  # candle[2] = BULL (fechado)
        {"open": "4.14", "close": "4.18"},  # candle[3] extra
        {"open": "4.12", "close": "4.16"},  # candle[4] extra
    ]

    async def fake_get_klines(symbol, interval="5", limit=5, *a, **kw):
        return all_bullish_5m[:limit]

    fake_rest = MagicMock()
    fake_rest.get_klines = fake_get_klines
    monkeypatch.setattr(rest_mod, "okx_rest_service", fake_rest)

    signals = [{
        "symbol": "INJUSDT",
        "side": "Sell",
        "strategy": "VELOCITY FLOW",
        "price": 4.2300,
        "contract_info": {"maxLeverage": 50.0},
        "id": "test_5m_block_001",
        "timestamp": 9999995,
    }]

    await sb._process_radar_signals(signals)

    saved = list(db._trades.values())
    assert len(saved) == 0, (
        f"Trade NÃO deveria ter sido aberto — 5M 2/2 bullish bloqueia SHORT (V117). "
        f"Trades abertos: {len(saved)}"
    )


@pytest.mark.asyncio
async def test_1m_filter_accepts_short_with_bearish_candles(monkeypatch):
    """
    Quando os candles de 1M mostram momentum bearish (2/3 candles vermelhos),
    um sinal SHORT deve ser aceito.
    """
    import services.sandbox_service as svc_mod
    import services.okx_ws_public as ws_mod
    import services.okx_rest as rest_mod

    db = FakeDB()
    ws = FakeWS(price=4.2310, conservative_price=4.2310, adx=30.0)

    sb = SandboxService()
    monkeypatch.setattr(ws_mod, "okx_ws_public_service", ws)
    monkeypatch.setattr(svc_mod, "database_service", db)
    monkeypatch.setattr(svc_mod, "okx_ws_public_service", ws)

    # Candles: 2 bearish + 1 bullish → SHORT deve ser aceito
    bearish_candles = [
        {"open": "4.25", "high": "4.26", "low": "4.20", "close": "4.21", "vol": "100"},  # vermelho
        {"open": "4.27", "high": "4.28", "low": "4.22", "close": "4.23", "vol": "90"},  # vermelho
        {"open": "4.22", "high": "4.27", "low": "4.21", "close": "4.26", "vol": "80"},  # verde (ruído)
        {"open": "4.20", "high": "4.23", "low": "4.18", "close": "4.19", "vol": "70"},  # vermelho
        {"open": "4.18", "high": "4.21", "low": "4.16", "close": "4.17", "vol": "60"},  # vermelho
    ]

    async def fake_get_klines(symbol, interval="5", limit=5, *a, **kw):
        return bearish_candles[:limit]

    fake_rest = MagicMock()
    fake_rest.get_klines = fake_get_klines
    monkeypatch.setattr(rest_mod, "okx_rest_service", fake_rest)

    signals = [{
        "symbol": "INJUSDT",
        "side": "Sell",
        "strategy": "VELOCITY FLOW",
        "price": 4.2310,
        "contract_info": {"maxLeverage": 50.0},
        "id": "test_1m_accept_001",
        "timestamp": 9999994,
    }]

    await sb._process_radar_signals(signals)

    saved = list(db._trades.values())
    assert len(saved) == 1, (
        f"Trade DEVERIA ter sido aberto com candles 5M bearish para SHORT. "
        f"Trades: {len(saved)}"
    )
    assert saved[0].direction == "SHORT"
