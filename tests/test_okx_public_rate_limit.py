import asyncio
import sys
import time
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import services.okx_rest as okx_rest_module
from services.okx_rest import OKXRest


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_concurrent_klines_share_one_public_request(monkeypatch):
    okx_rest_module._GLOBAL_KLINES_CACHE.clear()
    if hasattr(okx_rest_module, "_GLOBAL_KLINES_LOCKS"):
        okx_rest_module._GLOBAL_KLINES_LOCKS.clear()

    calls = {"count": 0}
    payload = {
        "code": "0",
        "data": [
            [str(1780000000000 + i), "1.0", "1.1", "0.9", "1.05", "100", "100"]
            for i in range(144)
        ],
    }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            calls["count"] += 1
            await asyncio.sleep(0.01)
            return _FakeResponse(200, payload)

    monkeypatch.setattr(okx_rest_module.httpx, "AsyncClient", FakeClient)

    service = OKXRest()
    service._public_min_interval = 0.0
    service._public_http_semaphore = asyncio.Semaphore(20)

    results = await asyncio.gather(*[
        service.get_klines("BTCUSDT.P", interval="30", limit=10)
        for _ in range(10)
    ])

    assert calls["count"] == 1
    assert all(len(result) == 10 for result in results)


@pytest.mark.asyncio
async def test_public_rate_limiter_sets_global_cooldown_on_429(monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            return _FakeResponse(429, headers={"Retry-After": "3"})

    monkeypatch.setattr(okx_rest_module.httpx, "AsyncClient", FakeClient)

    service = OKXRest()
    service._public_min_interval = 0.0
    before = time.time()

    response = await service._public_rate_limited_get("https://www.okx.com/test", label="test")

    assert response.status_code == 429
    assert service._public_429_streak == 1
    assert service._public_cooldown_until > before


@pytest.mark.asyncio
async def test_concurrent_account_ratio_shares_one_rubik_request(monkeypatch):
    calls = {"count": 0}
    payload = {"code": "0", "data": [{"ratio": "1.42"}]}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            calls["count"] += 1
            await asyncio.sleep(0.01)
            return _FakeResponse(200, payload)

    monkeypatch.setattr(okx_rest_module.httpx, "AsyncClient", FakeClient)

    service = OKXRest()
    service._public_min_interval = 0.0
    service._rubik_min_interval = 0.0
    service._public_http_semaphore = asyncio.Semaphore(20)

    results = await asyncio.gather(*[
        service.get_account_ratio("BTCUSDT.P")
        for _ in range(10)
    ])

    assert calls["count"] == 1
    assert results == [1.42] * 10


@pytest.mark.asyncio
async def test_account_ratio_uses_public_cooldown_on_429(monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            return _FakeResponse(429, headers={"Retry-After": "4"})

    monkeypatch.setattr(okx_rest_module.httpx, "AsyncClient", FakeClient)

    service = OKXRest()
    service._public_min_interval = 0.0
    service._rubik_min_interval = 0.0
    before = time.time()

    ratio = await service.get_account_ratio("BTCUSDT.P")

    assert ratio == 1.0
    assert service._public_429_streak == 1
    assert service._public_cooldown_until > before
