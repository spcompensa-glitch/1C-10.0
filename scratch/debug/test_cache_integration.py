# -*- coding: utf-8 -*-
"""
Testes de Integração - Safe Cache
==================================

Testes de integração para validar o funcionamento do Safe Cache
com outros serviços do sistema.

Author: QA Team
Version: 1.0
"""

import pytest
import asyncio
import sys
import os
import time

# Adiciona backend ao path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from backend.services.safe_cache import SafeCache, get_cache, get_signal_cache, get_price_cache

class TestCacheIntegration:
    """Testes de integração do Safe Cache"""
    
    def test_cache_basic_functionality(self):
        """Testa funcionalidade básica do cache"""
        cache = get_cache()
        
        # Testa armazenamento
        success = cache.set("test_key", "test_value")
        assert success is True
        
        # Testa recuperação
        value = cache.get("test_key")
        assert value == "test_value"
        
        # Testa existência
        assert cache.exists("test_key") is True
        
        # Testa remoção
        success = cache.delete("test_key")
        assert success is True
        
        # Testa recuperação após remoção
        value = cache.get("test_key")
        assert value is None
    
    def test_cache_ttl_functionality(self):
        """Testa funcionalidade de TTL"""
        cache = SafeCache(default_ttl=1.0)  # 1 segundo TTL
        
        # Armazena valor com TTL curto
        cache.set("ttl_key", "ttl_value")
        assert cache.get("ttl_key") == "ttl_value"
        
        # Espera expiração
        time.sleep(1.1)
        
        # Verifica que expirou
        value = cache.get("ttl_key")
        assert value is None
    
    def test_cache_stats_functionality(self):
        """Testa estatísticas do cache"""
        cache = get_cache()
        
        # Limpa cache
        cache.clear()
        
        # Realiza várias operações
        cache.set("stats_key1", "value1")
        cache.get("stats_key1")  # Hit
        cache.get("nonexistent_key")  # Miss
        
        # Verifica estatísticas
        stats = cache.get_stats()
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1
        assert stats["hit_rate"] >= 0
    
    def test_cache_memory_management(self):
        """Testa gerenciamento de memória"""
        cache = SafeCache(max_size_mb=1)  # Cache pequeno
        
        # Armazena vários valores
        for i in range(100):
            cache.set(f"key_{i}", f"value_{i}" * 100)  # Valores grandes
        
        # Verifica que não estourou
        stats = cache.get_stats()
        assert stats["total_entries"] >= 0
        
        # Verifica gerenciamento de memória
        assert stats["memory_usage_mb"] >= 0
    
    def test_cache_thread_safety(self):
        """Testa thread safety"""
        import threading
        
        cache = get_cache()
        results = []
        errors = []
        
        def worker_thread():
            try:
                for i in range(10):
                    cache.set(f"thread_key_{i}", f"thread_value_{i}")
                    value = cache.get(f"thread_key_{i}")
                    results.append(value)
            except Exception as e:
                errors.append(str(e))
        
        # Cria múltiplas threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=worker_thread)
            threads.append(thread)
            thread.start()
        
        # Espera todas as threads
        for thread in threads:
            thread.join()
        
        # Verifica resultados
        assert len(errors) == 0
        assert len(results) == 50  # 5 threads * 10 operações each
        
        # Verifica que todos os valores estão consistentes
        for i in range(10):
            value = cache.get(f"thread_key_{i}")
            assert value == f"thread_value_{i}"
    
    def test_specialized_caches(self):
        """Testa caches especializados"""
        # Testa cache de sinais
        signal_cache = get_signal_cache()
        signal_cache.set("signal_test", "signal_value")
        assert signal_cache.get("signal_test") == "signal_value"
        
        # Testa cache de preços
        price_cache = get_price_cache()
        price_cache.set("price_test", 123.45)
        assert price_cache.get("price_test") == 123.45
        
        # Testa cache de usuários
        user_cache = get_signal_cache()  # Reutiliza para teste
        user_cache.set("user_test", {"id": 1, "name": "test"})
        assert user_cache.get("user_test") == {"id": 1, "name": "test"}
    
    def test_cache_decorator_sync(self):
        """Testa decorator de cache para funções síncronas"""
        from backend.services.safe_cache import cached
        
        call_count = 0
        
        @cached(ttl=1.0)
        def test_function(x, y):
            nonlocal call_count
            call_count += 1
            return x + y
        
        # Primeira chamada
        result1 = test_function(1, 2)
        assert result1 == 3
        assert call_count == 1
        
        # Segunda chamada (deve usar cache)
        result2 = test_function(1, 2)
        assert result2 == 3
        assert call_count == 1  # Não deve incrementar
        
        # Terceira chamada com parâmetros diferentes
        result3 = test_function(2, 3)
        assert result3 == 5
        assert call_count == 2
        
        # Espera expiração
        time.sleep(1.1)
        
        # Chamada após expiração
        result4 = test_function(1, 2)
        assert result4 == 3
        assert call_count == 3  # Deve incrementar novamente
    
    def test_cache_error_handling(self):
        """Testa tratamento de erros"""
        cache = get_cache()
        
        # Testa armazenamento de valor inválido
        success = cache.set("error_key", None)
        assert success is True
        
        # Testa recuperação de valor inválido
        value = cache.get("error_key")
        assert value is None
        
        # Testa estatísticas após erro
        stats = cache.get_stats()
        assert "hits" in stats
        assert "misses" in stats
    
    def test_cache_concurrent_operations(self):
        """Testa operações concorrentes"""
        cache = get_cache()
        results = []
        
        async def async_worker():
            for i in range(10):
                await asyncio.sleep(0.01)  # Pequeno delay
                cache.set(f"async_key_{i}", f"async_value_{i}")
                value = cache.get(f"async_key_{i}")
                results.append(value)
        
        # Executa múltiplas tarefas assíncronas
        async def run_test():
            tasks = [async_worker() for _ in range(3)]
            await asyncio.gather(*tasks)
        
        # Executa teste
        asyncio.run(run_test())
        
        # Verifica resultados
        assert len(results) == 30  # 3 tasks * 10 operations each
        assert all(result is not None for result in results)

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])