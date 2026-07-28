# -*- coding: utf-8 -*-
"""
Fixtures de teste para o sistema 1C-7.0.
Fornece dados mockados e configuração para testes unitários.
"""
import pytest
import time
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, List, Any

# Adiciona backend ao sys.path para importar os módulos do projeto
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


# =========================================================================
# DADOS MOCKADOS
# =========================================================================

@pytest.fixture
def mock_klines() -> List[List]:
    """
    Retorna 100 candles mockados (formato OKX).
    São candles sintéticos de 5 minutos gerando uma tendência de alta suave.
    Cada candle: [timestamp, open, high, low, close, volume, turnover]
    """
    klines = []
    base_ts = int(time.time() * 1000) - (100 * 300000)  # 100 candles atrás
    base_price = 100.0
    
    for i in range(100):
        ts = base_ts + (i * 300000)  # 5 min intervals
        # Tendência de alta suave + ruído
        trend = i * 0.05  # +5% no total
        noise = (hash(f"noise_{i}") % 200 - 100) / 1000  # -0.1 a +0.1
        open_price = base_price + trend + noise
        close_price = open_price + 0.02 + (hash(f"close_{i}") % 100 - 50) / 500
        high_price = max(open_price, close_price) + abs(hash(f"high_{i}") % 100) / 300
        low_price = min(open_price, close_price) - abs(hash(f"low_{i}") % 100) / 300
        volume = 1000 + (hash(f"vol_{i}") % 500)
        
        klines.append([
            str(ts),                # timestamp
            str(round(open_price, 2)),   # open
            str(round(high_price, 2)),   # high
            str(round(low_price, 2)),    # low
            str(round(close_price, 2)),  # close
            str(round(volume, 2)),       # volume
            str(round(volume * close_price, 2))  # turnover
        ])
    
    return klines


@pytest.fixture
def mock_klines_downtrend() -> List[List]:
    """
    Retorna 100 candles mockados em tendência de queda.
    """
    klines = []
    base_ts = int(time.time() * 1000) - (100 * 300000)
    base_price = 100.0
    
    for i in range(100):
        ts = base_ts + (i * 300000)
        trend = -i * 0.05  # -5% no total
        noise = (hash(f"noise_{i}") % 200 - 100) / 1000
        open_price = base_price + trend + noise
        close_price = open_price - 0.02 + (hash(f"close_{i}_d") % 100 - 50) / 500
        high_price = max(open_price, close_price) + abs(hash(f"high_{i}_d") % 100) / 300
        low_price = min(open_price, close_price) - abs(hash(f"low_{i}_d") % 100) / 300
        volume = 1000 + (hash(f"vol_{i}_d") % 500)
        
        klines.append([
            str(ts),
            str(round(open_price, 2)),
            str(round(high_price, 2)),
            str(round(low_price, 2)),
            str(round(close_price, 2)),
            str(round(volume, 2)),
            str(round(volume * close_price, 2))
        ])
    
    return klines


@pytest.fixture
def mock_klines_sideways() -> List[List]:
    """
    Retorna 100 candles mockados sem tendência clara (sideways).
    """
    klines = []
    base_ts = int(time.time() * 1000) - (100 * 300000)
    base_price = 100.0
    
    for i in range(100):
        ts = base_ts + (i * 300000)
        noise = (hash(f"noise_{i}_s") % 200 - 100) / 500  # -0.2 a +0.2
        open_price = base_price + noise
        close_price = open_price + (hash(f"close_{i}_s") % 100 - 50) / 300
        high_price = max(open_price, close_price) + abs(hash(f"high_{i}_s") % 100) / 400
        low_price = min(open_price, close_price) - abs(hash(f"low_{i}_s") % 100) / 400
        volume = 500 + (hash(f"vol_{i}_s") % 300)
        
        klines.append([
            str(ts),
            str(round(open_price, 2)),
            str(round(high_price, 2)),
            str(round(low_price, 2)),
            str(round(close_price, 2)),
            str(round(volume, 2)),
            str(round(volume * close_price, 2))
        ])
    
    return klines


# =========================================================================
# FIXXTURES DE CONFIGURAÇÃO
# =========================================================================

@pytest.fixture
def mock_settings():
    """Config mockada para testes."""
    with patch('config.settings') as mock:
        mock.KRONOS_ENABLED = True
        mock.KRONOS_FALLBACK_SCORE = 50
        mock.KRONOS_SCORE_WEIGHT = 0.18
        mock.KRONOS_INTERVAL = "5"
        mock.KRONOS_CACHE_TTL = 60
        mock.KRONOS_TIMEOUT = 5.0
        yield mock


# =========================================================================
# FIXXTURES DE SERVIÇO
# =========================================================================

@pytest.fixture
async def kronos_scorer_instance():
    """Instância do KronosScorer para testes."""
    from services.kronos_scorer import KronosScorer
    scorer = KronosScorer()
    scorer.is_available = False  # Força modo fallback para não depender de PyTorch
    return scorer


@pytest.fixture
def mock_okx_rest(mock_klines):
    """Mock do okx_rest_service para testes."""
    with patch('services.kronos_scorer.okx_rest_service') as mock:
        mock.get_klines = AsyncMock(return_value=mock_klines)
        yield mock


@pytest.fixture
def mock_okx_rest_downtrend(mock_klines_downtrend):
    """Mock do okx_rest_service com tendência de queda."""
    with patch('services.kronos_scorer.okx_rest_service') as mock:
        mock.get_klines = AsyncMock(return_value=mock_klines_downtrend)
        yield mock


@pytest.fixture
def mock_okx_rest_sideways(mock_klines_sideways):
    """Mock do okx_rest_service sem tendência."""
    with patch('services.kronos_scorer.okx_rest_service') as mock:
        mock.get_klines = AsyncMock(return_value=mock_klines_sideways)
        yield mock


@pytest.fixture
def mock_okx_rest_empty():
    """Mock do okx_rest_service retornando dados vazios."""
    with patch('services.kronos_scorer.okx_rest_service') as mock:
        mock.get_klines = AsyncMock(return_value=[])
        yield mock
