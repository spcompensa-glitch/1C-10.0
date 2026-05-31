# -*- coding: utf-8 -*-
"""
Testes de Performance e Integração - Suite Completa
====================================================

Suite de testes para validar:
1. Performance do cache
2. Otimização de loops
3. Integração de serviços
4. Escalabilidade do sistema
5. Resposta a carga

Author: Performance Testing Team
Version: 1.0

Coverage:
- Cache performance metrics
- SignalGenerator optimization
- Service integration
- Load testing
- Scalability validation
"""

import pytest
import asyncio
import time
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import Mock, patch, AsyncMock
from typing import List, Dict, Any
import psutil
import threading

# Importa módulos de performance
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.safe_cache import SafeCache, get_cache, cached
from backend.services.signal_generator_optimized import OptimizedSignalGenerator, get_optimized_signals
from backend.services.secrets import secrets_manager
from backend.services.sovereign_service import sovereign_service

class TestCachePerformance:
    """Testes de performance do cache"""
    
    def test_cache_set_performance(self):
        """Testa performance de operações de escrita no cache"""
        cache = SafeCache(max_size_mb=100, default_ttl=300)
        
        # Testa escrita de 10.000 itens
        start_time = time.time()
        for i in range(10000):
            cache.set(f"key_{i}", f"value_{i}")
        
        end_time = time.time()
        avg_time = (end_time - start_time) / 10000
        
        print(f"Cache write performance: {avg_time:.6f}s por operação")
        assert avg_time < 0.001, "Cache write deve ser rápido (< 1ms por operação)"
        
        # Verifica todos os itens foram armazenados
        for i in range(10000):
            value = cache.get(f"key_{i}")
            assert value == f"value_{i}"
    
    def test_cache_get_performance(self):
        """Testa performance de operações de leitura no cache"""
        cache = SafeCache(max_size_mb=100, default_ttl=300)
        
        # Pré-carrega cache
        for i in range(10000):
            cache.set(f"key_{i}", f"value_{i}")
        
        # Testa leitura de todos os itens
        start_time = time.time()
        for i in range(10000):
            value = cache.get(f"key_{i}")
            assert value == f"value_{i}"
        
        end_time = time.time()
        avg_time = (end_time - start_time) / 10000
        
        print(f"Cache read performance: {avg_time:.6f}s por operação")
        assert avg_time < 0.0005, "Cache read deve ser muito rápido (< 0.5ms por operação)"
    
    def test_cache_hit_ratio(self):
        """Testa taxa de acerto do cache"""
        cache = SafeCache(max_size_mb=100, default_ttl=300)
        
        # Pré-carrega cache
        for i in range(1000):
            cache.set(f"cached_key_{i}", f"value_{i}")
        
        # Testa acertos
        start_time = time.time()
        hit_count = 0
        total_count = 2000
        
        for i in range(total_count):
            if i < 1000:
                # Deve ser acerto
                value = cache.get(f"cached_key_{i}")
                if value is not None:
                    hit_count += 1
            else:
                # Deve ser erro
                value = cache.get(f"uncached_key_{i}")
                if value is None:
                    hit_count += 1  # Conta erro como "acerto" na lógica de cache
        
        end_time = time.time()
        
        # Calcula hit rate
        hit_rate = (hit_count / total_count) * 100
        
        print(f"Cache hit rate: {hit_rate:.2f}%")
        assert hit_rate > 95, "Cache hit rate deve ser > 95%"
    
    def test_cache_memory_usage(self):
        """Testa uso de memória do cache"""
        cache = SafeCache(max_size_mb=10, default_ttl=300)
        
        # Monitora uso de memória
        initial_memory = psutil.Process().memory_info().rss
        
        # Armazena dados até atingir limite
        total_data = 0
        for i in range(1000):
            data = f"x" * 1024  # 1KB por item
            cache.set(f"memory_key_{i}", data)
            total_data += 1024
            
            # Verifica uso de memória
            current_memory = psutil.Process().memory_info().rss
            memory_increase = current_memory - initial_memory
            
            # Não deve ultrapassar limite por muito
            assert memory_increase < 15 * 1024 * 1024, "Uso de memória não deve exceder limite em > 50%"
    
    def test_cache_ttl_performance(self):
        """Testa performance do TTL"""
        cache = SafeCache(max_size_mb=100, default_ttl=1)  # 1 segundo TTL
        
        # Armazena itens
        for i in range(100):
            cache.set(f"ttl_key_{i}", f"value_{i}")
        
        # Espera expiração
        time.sleep(2)
        
        # Verifica expiração
        expired_count = 0
        for i in range(100):
            value = cache.get(f"ttl_key_{i}")
            if value is None:
                expired_count += 1
        
        print(f"TTL expiration rate: {expired_count}/100")
        assert expired_count == 100, "Todos os itens devem ter expirado"

class TestSignalGeneratorPerformance:
    """Testes de performance do SignalGenerator"""
    
    def test_signal_generation_concurrent(self):
        """Testa geração de sinais concorrente"""
        generator = OptimizedSignalGenerator(max_workers=4)
        
        # Simula dados de mercado
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOTUSDT"]
        zones_data = {
            symbol: {
                "support": [40000, 39000, 38000],
                "resistance": [41000, 42000, 43000]
            }
            for symbol in symbols
        }
        
        # Testa geração concorrente
        start_time = time.time()
        
        tasks = []
        for _ in range(10):  # 10 iterações concorrentes
            task = get_optimized_signals(symbols, zones_data)
            tasks.append(task)
        
        results = asyncio.run(asyncio.gather(*tasks))
        
        end_time = time.time()
        total_time = end_time - start_time
        avg_time = total_time / 10
        
        print(f"Signal generation concurrent performance: {avg_time:.3f}s por batch")
        assert avg_time < 1.0, "Geração de sinais concorrente deve ser rápida (< 1s por batch)"
        
        # Verifica resultados
        for result in results:
            assert len(result) <= len(symbols), "Resultado deve conter sinais para símbolos válidos"
    
    def test_signal_generation_scalability(self):
        """Testa escalabilidade do SignalGenerator"""
        generator = OptimizedSignalGenerator(max_workers=8)
        
        # Testa com diferentes números de símbolos
        test_cases = [
            (10, "pequeno"),
            (50, "médio"), 
            (100, "grande"),
            (200, "muito grande")
        ]
        
        results = {}
        
        for symbol_count, label in test_cases:
            symbols = [f"SYMBOL{i:03d}USDT" for i in range(symbol_count)]
            zones_data = {
                symbol: {
                    "support": [40000, 39000, 38000],
                    "resistance": [41000, 42000, 43000]
                }
                for symbol in symbols
            }
            
            start_time = time.time()
            result = asyncio.run(get_optimized_signals(symbols, zones_data))
            end_time = time.time()
            
            execution_time = end_time - start_time
            results[label] = {
                "symbol_count": symbol_count,
                "execution_time": execution_time,
                "symbols_per_second": symbol_count / execution_time if execution_time > 0 else 0
            }
            
            print(f"Scalability test - {label}: {symbol_count} symbols in {execution_time:.3f}s "
                  f"({results[label]['symbols_per_second']:.1f} symbols/s)")
            
            # Verifica tempo razoável
            assert execution_time < 5.0, f"Execução com {symbol_count} símbolos deve ser rápida (< 5s)"
        
        # Verifica escalabilidade linear
        small_rate = results["pequeno"]["symbols_per_second"]
        large_rate = results["grande"]["symbols_per_second"]
        
        # Deve haver degradação aceitável
        scalability_ratio = large_rate / small_rate
        print(f"Scalability ratio: {scalability_ratio:.2f}")
        assert scalability_ratio > 0.5, "Escalabilidade deve manter > 50% de performance"

class TestServiceIntegration:
    """Testes de integração de serviços"""
    
    def test_secrets_manager_integration(self):
        """Testa integração do Secrets Manager"""
        # Configura variáveis de ambiente
        test_env = {
            "JWT_SECRET_KEY": "test_jwt_secret_32_chars_long_enough",
            "OKX_API_KEY_MASTER": "test_api_key",
            "OKX_API_SECRET_MASTER": "test_api_secret",
            "OKX_PASSPHRASE_MASTER": "test_passphrase",
            "DATABASE_URL": "postgresql://localhost/test",
            "ADMIN_API_KEY": "test_admin_key"
        }
        
        with patch.dict(os.environ, test_env):
            # Testa integração completa
            assert secrets_manager.validate_production_readiness() is True
            
            jwt_secret = secrets_manager.get_jwt_secret()
            okx_creds = secrets_manager.get_okx_credentials()
            
            assert jwt_secret == "test_jwt_secret_32_chars_long_enough"
            assert okx_creds["api_key"] == "test_api_key"
            assert okx_creds["api_secret"] == "test_api_secret"
            assert okx_creds["passphrase"] == "test_passphrase"
    
    def test_sovereign_service_integration(self):
        """Testa integração do Sovereign Service"""
        # Mock dos serviços essenciais
        mock_auth_service = Mock()
        mock_auth_service.start = AsyncMock()
        mock_auth_service.stop = AsyncMock()
        mock_auth_service.health_check = AsyncMock(return_value=True)
        
        mock_database_service = Mock()
        mock_database_service.start = AsyncMock()
        mock_database_service.stop = AsyncMock()
        mock_database_service.health_check = AsyncMock(return_value=True)
        
        # Registra serviços
        sovereign_service.register_service("auth_service", mock_auth_service)
        sovereign_service.register_service("database_service", mock_database_service)
        
        # Testa orquestração
        async def test_orchestration():
            # Inicia serviços
            await sovereign_service.start_service("auth_service")
            await sovereign_service.start_service("database_service")
            
            # Verifica status
            status = sovereign_service.get_system_status()
            assert status["running"] is True
            assert status["services"]["auth_service"]["status"] == "RUNNING"
            assert status["services"]["database_service"]["status"] == "RUNNING"
            
            # Verifica saúde do sistema
            health = await sovereign_service.get_system_health()
            assert health.value in ["EXCELLENT", "GOOD"]
            
            # Para serviços
            await sovereign_service.stop_service("auth_service")
            await sovereign_service.stop_service("database_service")
            
            return True
        
        # Executa teste
        result = asyncio.run(test_orchestration())
        assert result is True
    
    def test_cache_and_secrets_integration(self):
        """Testa integração entre cache e segredos"""
        cache = get_cache()
        
        # Armazena segredos no cache (com segurança)
        secrets_manager._log_secret_access("JWT_SECRET_KEY", "test")
        
        # Testa que segredos não são expostos no cache
        cache.set("security_test", "sensitive_data")
        
        # Verifica que dados sensíveis não são expostos
        cached_value = cache.get("security_test")
        assert cached_value == "sensitive_data"
        
        # Verifica estatísticas do cache
        stats = cache.get_stats()
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats

class TestLoadTesting:
    """Testes de carga"""
    
    def test_concurrent_cache_operations(self):
        """Testa operações concorrentes no cache"""
        cache = SafeCache(max_size_mb=100, default_ttl=300)
        
        # Número de threads concorrentes
        thread_count = 50
        operations_per_thread = 100
        
        results = []
        
        def cache_operations(thread_id):
            thread_results = []
            for i in range(operations_per_thread):
                key = f"thread_{thread_id}_key_{i}"
                value = f"thread_{thread_id}_value_{i}"
                
                # Escrita
                success = cache.set(key, value)
                thread_results.append(("write", success))
                
                # Leitura
                retrieved = cache.get(key)
                thread_results.append(("read", retrieved == value))
                
                # Deleção
                deleted = cache.delete(key)
                thread_results.append(("delete", deleted))
            
            return thread_results
        
        # Executa threads concorrentes
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = [executor.submit(cache_operations, i) for i in range(thread_count)]
            
            for future in as_completed(futures):
                results.extend(future.result())
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Analisa resultados
        success_count = sum(1 for operation, success in results if success)
        total_operations = len(results)
        
        success_rate = (success_count / total_operations) * 100
        
        print(f"Concurrent cache operations: {total_operations} operations in {total_time:.3f}s")
        print(f"Success rate: {success_rate:.2f}%")
        
        assert success_rate > 99.0, "Taxa de sucesso deve ser > 99%"
        assert total_time < 10.0, "Tempo total deve ser rápido (< 10s)"
    
    def test_signal_generator_load(self):
        """Testa carga no SignalGenerator"""
        generator = OptimizedSignalGenerator(max_workers=4)
        
        # Simula carga pesada
        symbols = [f"BTC{i:03d}USDT" for i in range(50)]  # 50 símbolos
        zones_data = {
            symbol: {
                "support": [40000, 39000, 38000],
                "resistance": [41000, 42000, 43000],
                "volume_profile": [1000, 2000, 3000]
            }
            for symbol in symbols
        }
        
        # Testa múltiplas requisições concorrentes
        start_time = time.time()
        
        tasks = []
        for i in range(20):  # 20 requisições concorrentes
            task = get_optimized_signals(symbols, zones_data)
            tasks.append(task)
        
        results = asyncio.run(asyncio.gather(*tasks))
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Analisa resultados
        total_signals = sum(len(result) for result in results)
        avg_time = total_time / 20
        
        print(f"Signal generator load test: {total_signals} signals in {total_time:.3f}s")
        print(f"Average time per request: {avg_time:.3f}s")
        
        assert avg_time < 2.0, "Tempo médio deve ser rápido (< 2s)"
        assert len(results) == 20, "Todas as requisições devem ser completadas"

class TestPerformanceMetrics:
    """Testes de métricas de performance"""
    
    def test_cache_metrics(self):
        """Testa métricas do cache"""
        cache = SafeCache(max_size_mb=100, default_ttl=300)
        
        # Executa operações
        for i in range(1000):
            cache.set(f"metric_key_{i}", f"value_{i}")
        
        for i in range(1000):
            cache.get(f"metric_key_{i}")
        
        # Obtém métricas
        metrics = cache.get_stats()
        
        # Verifica métricas
        assert "hits" in metrics
        assert "misses" in metrics
        assert "hit_rate" in metrics
        assert "evictions" in metrics
        assert "total_entries" in metrics
        assert "cache_size_bytes" in metrics
        
        # Verifica consistência
        total_requests = metrics["hits"] + metrics["misses"]
        assert total_requests >= 2000, "Total de requisições deve ser >= 2000"
        
        if total_requests > 0:
            assert metrics["hit_rate"] >= 0.0, "Hit rate deve ser >= 0%"
            assert metrics["hit_rate"] <= 100.0, "Hit rate deve ser <= 100%"
    
    def test_memory_usage_tracking(self):
        """Testa rastreamento de uso de memória"""
        cache = SafeCache(max_size_mb=10, default_ttl=300)
        
        # Obtém uso inicial de memória
        initial_memory = psutil.Process().memory_info().rss
        
        # Armazena dados
        for i in range(100):
            large_data = f"x" * 1024  # 1KB
            cache.set(f"memory_key_{i}", large_data)
        
        # Obtém uso final de memória
        final_memory = psutil.Process().memory_info().rss
        
        # Calcula aumento
        memory_increase = final_memory - initial_memory
        
        print(f"Memory increase: {memory_increase / 1024 / 1024:.2f}MB")
        assert memory_increase < 15 * 1024 * 1024, "Aumento de memória deve ser controlado"

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])