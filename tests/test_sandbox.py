import sys
import time
import asyncio
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.database_service import database_service
from services.sandbox_service import SandboxService
from services.okx_ws_public import okx_ws_public_service

@pytest.mark.asyncio
async def test_sandbox_trade_flow(monkeypatch):
    # Inicializar banco de dados do teste
    await database_service.initialize()
    await database_service.clear_sandbox_trades()

    sandbox = SandboxService()

    # Mock de sinais do radar
    mock_signals = [
        {
            "symbol": "BTC-USDT-TEST",
            "side": "Buy",
            "strategy": "TEST_STRAT",
            "price": 100.0,
            "contract_info": {
                "maxLeverage": 50.0
            }
        }
    ]

    # Mock sync_topics e get_current_price
    sync_called = []
    async def fake_sync(symbols):
        sync_called.append(symbols)

    monkeypatch.setattr(okx_ws_public_service, "sync_topics", fake_sync)
    monkeypatch.setattr(okx_ws_public_service, "get_current_price", lambda sym: 100.0)

    # 1. Teste de criação da ordem simulada via hook
    await sandbox.on_radar_pulse(mock_signals)

    # Verificar se foi salvo no Postgres
    trades = await database_service.get_sandbox_trades()
    assert len(trades) == 1
    trade = trades[0]
    assert trade.symbol == "BTC-USDT-TEST"
    assert trade.entry_price == 100.0
    assert trade.status == "ACTIVE"
    assert "BTC-USDT-TEST" in sync_called[0]

    # 2. Simular evolução de preços (Lucro - bater 80% ROI para subir SL)
    # 80% ROI com leverage 50 = subida de 1.6% no preço (Preço = 101.6)
    monkeypatch.setattr(okx_ws_public_service, "get_current_price", lambda sym: 101.6)

    # Rodar um ciclo manual do loop de atualização de preços
    sandbox.is_running = True
    task1 = asyncio.create_task(sandbox._price_update_loop())
    await asyncio.sleep(0.1)
    sandbox.is_running = False
    await task1

    # Verificar se subiu o stop
    trade_updated = await database_service.get_sandbox_trade(trade.id)
    assert trade_updated.current_roi >= 79.9
    assert trade_updated.flash_state.get("active_level") == "RISCO_ZERO"
    assert trade_updated.flash_state.get("stop_roi") == 15.0 # SL movido para +15% ROI

    # 3. Simular queda para bater no Stop Loss de +15% ROI
    # +15% ROI com leverage 50 = subida de 0.3% no preço (Preço = 100.3).
    # Se cair para 100.1, viola o stop de 100.3
    monkeypatch.setattr(okx_ws_public_service, "get_current_price", lambda sym: 100.1)

    sandbox.is_running = True
    task2 = asyncio.create_task(sandbox._price_update_loop())
    await asyncio.sleep(0.1)
    sandbox.is_running = False
    await task2

    # Verificar fechamento
    trade_closed = await database_service.get_sandbox_trade(trade.id)
    assert trade_closed.status == "CLOSED_SL"
    assert trade_closed.closed_at is not None

    await database_service.clear_sandbox_trades()
