# -*- coding: utf-8 -*-
"""
Safe Cache - Sistema de Cache com TTL e Gerenciamento de Memória
===============================================================

Sistema de cache em memória seguro com TTL automático, limpeza de 
expirados, e monitoramento de uso de memória para prevenir memory leaks.

Author: Performance Team
Version: 1.0

Performance Features:
- TTL automático com limpeza periódica
- Monitoramento de uso de memória
- Cache hit/miss tracking
- Thread-safe operations
- Memory leak prevention
"""

import asyncio
import time
import threading
import logging
from typing import Any, Optional, Dict, List, Callable
from dataclasses import dataclass, field
from functools import wraps
import weakref
import psutil

logger = logging.getLogger("SafeCache")

@dataclass
class CacheEntry:
    """Entrada no cache com timestamp e TTL"""
    value: Any
    created_at: float = field(default_factory=time.time)
    ttl: float = 300.0  # 5 minutos padrão
    access_count: int = field(default_factory=int)
    last_accessed: float = field(default_factory=time.time)
    size: int = field(default_factory=int)
    
    def is_expired(self) -> bool:
        """Verifica se a entrada expirou"""
        return time.time() - self.created_at > self.ttl
    
    def touch(self):
        """Atualiza timestamp de acesso"""
        self.access_count += 1
        self.last_accessed = time.time()

class SafeCache:
    """
    Sistema de cache seguro com TTL e gerenciamento de memória.
    
    Features:
    - Cache com TTL automático
    - Limpeza periódica de expirados
    - Monitoramento de uso de memória
    - Thread-safe operations
    - Cache hit/miss tracking
    - Memory leak prevention
    """
    
    def __init__(self, max_size_mb: int = 100, default_ttl: float = 300.0):
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.default_ttl = default_ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'cleanup_count': 0
        }
        
        # Inicia limpeza periódica
        self._start_cleanup_task()
        
    def _start_cleanup_task(self):
        """Inicia task de limpeza periódica"""
        try:
            # Verifica se há um loop de eventos em execução
            loop = asyncio.get_event_loop()
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = loop.create_task(self._periodic_cleanup())
        except RuntimeError:
            # Se não houver loop de eventos, cria um novo ou inicia em modo seguro
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
    
    async def _periodic_cleanup(self):
        """Limpeza periódica de entradas expiradas"""
        while True:
            try:
                await asyncio.sleep(60)  # Limpa a cada 60 segundos
                await self._clean_expired_entries()
                await self._check_memory_usage()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [CACHE-CLEANUP] Erro na limpeza: {e}")
    
    async def _clean_expired_entries(self):
        """Remove entradas expiradas"""
        with self._lock:
            expired_keys = []
            for key, entry in self._cache.items():
                if entry.is_expired():
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._cache[key]
                self._stats['evictions'] += 1
            
            if expired_keys:
                logger.debug(f"🧹 [CACHE-CLEANUP] Removidas {len(expired_keys)} entradas expiradas")
                self._stats['cleanup_count'] += 1
    
    async def _check_memory_usage(self):
        """Verifica e gerencia uso de memória"""
        with self._lock:
            current_size = self._get_cache_size()
            
            if current_size > self.max_size_bytes:
                # Remove entradas menos acessadas primeiro
                sorted_entries = sorted(
                    self._cache.items(),
                    key=lambda x: x[1].last_accessed
                )
                
                removed_count = 0
                target_size = int(self.max_size_bytes * 0.8)  # Volta para 80% do limite
                
                for key, entry in sorted_entries:
                    if current_size <= target_size:
                        break
                    
                    del self._cache[key]
                    current_size -= entry.size
                    removed_count += 1
                
                if removed_count > 0:
                    logger.warning(f"📉 [CACHE-MEMORY] Removidas {removed_count} entradas por uso de memória")
                    self._stats['evictions'] += removed_count
    
    def _get_cache_size(self) -> int:
        """Calcula tamanho total do cache"""
        return sum(entry.size for entry in self._cache.values())
    
    def _get_memory_usage_mb(self) -> float:
        """Obtém uso de memória do processo em MB"""
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024
    
    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> bool:
        """
        Armazena valor no cache
        
        Args:
            key: Chave do cache
            value: Valor a armazenar
            ttl: Time to live em segundos (padrão: 300s)
        
        Returns:
            bool: True se armazenado com sucesso
        """
        try:
            with self._lock:
                # Calcula tamanho do valor
                size = len(str(value).encode('utf-8'))
                
                # Verifica se cabe no cache
                current_size = self._get_cache_size()
                if current_size + size > self.max_size_bytes:
                    logger.warning(f"📊 [CACHE-FULL] Cache cheio ao tentar adicionar {key}")
                    return False
                
                # Cria entrada
                entry = CacheEntry(
                    value=value,
                    ttl=ttl or self.default_ttl,
                    size=size
                )
                
                self._cache[key] = entry
                logger.debug(f"💾 [CACHE-SET] Armazenado: {key} ({size} bytes)")
                return True
                
        except Exception as e:
            logger.error(f"❌ [CACHE-ERROR] Erro ao armazenar {key}: {e}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """
        Obtém valor do cache
        
        Args:
            key: Chave do cache
        
        Returns:
            Valor armazenado ou None se não existir/expirado
        """
        try:
            with self._lock:
                entry = self._cache.get(key)
                
                if entry is None:
                    self._stats['misses'] += 1
                    return None
                
                if entry.is_expired():
                    del self._cache[key]
                    self._stats['evictions'] += 1
                    self._stats['misses'] += 1
                    return None
                
                # Atualiza timestamp de acesso
                entry.touch()
                self._stats['hits'] += 1
                
                logger.debug(f"🎯 [CACHE-HIT] Hit: {key} (acessos: {entry.access_count})")
                return entry.value
                
        except Exception as e:
            logger.error(f"❌ [CACHE-ERROR] Erro ao obter {key}: {e}")
            self._stats['misses'] += 1
            return None
    
    def delete(self, key: str) -> bool:
        """
        Remove valor do cache
        
        Args:
            key: Chave do cache
        
        Returns:
            bool: True se removido com sucesso
        """
        try:
            with self._lock:
                if key in self._cache:
                    del self._cache[key]
                    logger.debug(f"🗑️ [CACHE-DELETE] Removido: {key}")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"❌ [CACHE-ERROR] Erro ao remover {key}: {e}")
            return False
    
    def clear(self):
        """Limpa todo o cache"""
        with self._lock:
            size = len(self._cache)
            self._cache.clear()
            logger.info(f"🧹 [CACHE-CLEAR] Cache limpo ({size} entradas removidas)")
    
    def exists(self, key: str) -> bool:
        """Verifica se chave existe e não está expirada"""
        return self.get(key) is not None
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtém estatísticas do cache"""
        with self._lock:
            total_requests = self._stats['hits'] + self._stats['misses']
            hit_rate = (self._stats['hits'] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'hit_rate': round(hit_rate, 2),
                'evictions': self._stats['evictions'],
                'cleanup_count': self._stats['cleanup_count'],
                'total_entries': len(self._cache),
                'cache_size_bytes': self._get_cache_size(),
                'memory_usage_mb': self._get_memory_usage_mb(),
                'max_size_bytes': self.max_size_bytes
            }
    
    def get_all_keys(self) -> List[str]:
        """Obtém todas as chaves não expiradas"""
        with self._lock:
            return [key for key in self._cache.keys() if not self._cache[key].is_expired()]
    
    def stop(self):
        """Para a task de limpeza"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
    
    def __del__(self):
        """Garante limpeza ao destruir"""
        self.stop()

# Cache global para o sistema
_cache_instance = None

def get_cache() -> SafeCache:
    """Obtém instância global do cache"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = SafeCache()
    return _cache_instance

def cached(ttl: Optional[float] = None, key_func: Optional[Callable] = None):
    """
    Decorator para cache de funções
    
    Args:
        ttl: Time to live em segundos
        key_func: Função para gerar chave personalizada
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            cache = get_cache()
            
            # Gera chave
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{args}:{kwargs}"
            
            # Tenta obter do cache
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Executa função e armazena resultado
            result = await func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            cache = get_cache()
            
            # Gera chave
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{args}:{kwargs}"
            
            # Tenta obter do cache
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Executa função e armazena resultado
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator

# Cache específico para diferentes tipos de dados
_signal_cache = SafeCache(max_size_mb=50, default_ttl=60)  # 1 minuto para sinais
_price_cache = SafeCache(max_size_mb=100, default_ttl=30)   # 30 segundos para preços
_user_cache = SafeCache(max_size_mb=20, default_ttl=300)   # 5 minutos para usuários

def get_signal_cache() -> SafeCache:
    """Cache para sinais de trading"""
    return _signal_cache

def get_price_cache() -> SafeCache:
    """Cache para dados de preço"""
    return _price_cache

def get_user_cache() -> SafeCache:
    """Cache para dados de usuário"""
    return _user_cache