import asyncio
import time
import logging
from typing import Callable, Any, Dict, Optional
from functools import wraps

logger = logging.getLogger("CircuitBreaker")
logger.setLevel(logging.INFO)

class BreakerState:
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: float = 30.0, max_retries: int = 3, backoff_base: float = 1.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        
        self.state = BreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        logger.warning(f"[CIRCUIT BREAKER - {self.name}] Falha registrada. Contagem: {self.failure_count}/{self.failure_threshold}")
        if self.state == BreakerState.HALF_OPEN or self.failure_count >= self.failure_threshold:
            self._transition_to(BreakerState.OPEN)

    def record_success(self):
        if self.state != BreakerState.CLOSED:
            if self.state == BreakerState.HALF_OPEN:
                logger.info(f"✅ [CIRCUIT BREAKER - {self.name}] Sucesso no teste em Half-Open. Circuito restaurado (CLOSED).")
            self._transition_to(BreakerState.CLOSED)
        # Even if CLOSED, reset failures on success
        self.failure_count = 0

    def _transition_to(self, new_state: str):
        if self.state == new_state:
            return
        
        old_state = self.state
        self.state = new_state
        logger.warning(f"🚨 [CIRCUIT BREAKER - {self.name}] Transição de Estado: {old_state} -> {new_state}")
        
        if new_state == BreakerState.OPEN:
            logger.error(f"🛑 [CIRCUIT BREAKER - {self.name}] CIRCUITO ABERTO. Chamadas bloqueadas pelas próximas {self.recovery_timeout}s.")

    def can_execute(self) -> bool:
        if self.state == BreakerState.CLOSED:
            return True
        
        if self.state == BreakerState.OPEN:
            # Check if it's time to try half-open
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self._transition_to(BreakerState.HALF_OPEN)
                return True
            return False
            
        if self.state == BreakerState.HALF_OPEN:
            # In half open, we allow the next request to try
            return True
            
        return False

# Global Registry
_breakers: Dict[str, CircuitBreaker] = {}

def get_breaker(name: str, **kwargs) -> CircuitBreaker:
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name, **kwargs)
    return _breakers[name]

class CircuitBreakerOpenException(Exception):
    pass

def with_circuit_breaker(breaker_name: str, fallback_return: Any = None, is_critical: bool = False, **breaker_kwargs):
    """
    Decorador asssíncrono para blindar funções com Circuit Breaker e Exponential Backoff.
    
    Args:
        breaker_name: Nome do disjuntor (ex: "okx_rest", "firestore")
        fallback_return: O valor a retornar se o circuito estiver aberto ou as tentativas esgotarem.
        is_critical: Se True, tenta forçar execução ignorando limitador de tentativas (Emergency Bypass).
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cb = get_breaker(breaker_name, **breaker_kwargs)
            
            # 1. Verifica se o circuito permite execução
            if not cb.can_execute() and not is_critical:
                logger.warning(f"🚫 [CIRCUIT BREAKER - {cb.name}] Prevenção ativa. Chamada a {func.__name__} bloqueada. Retornando fallback.")
                return fallback_return
            
            retries = 0
            while retries <= cb.max_retries:
                try:
                    result = await func(*args, **kwargs)
                    
                    # Verificação customizada para Bybit REST (RetCodes com Rate Limits)
                    # Ex: 429 via HTTP retorna exception. Mas às vezes a Pybit retorna retCode customizado na payload
                    if isinstance(result, dict) and result.get("retCode") in [10006, 10002]: # Exemplo de retCodes da Bybit
                        raise Exception(f"Bybit API Rate Limit retCode {result.get('retCode')} detected na payload.")

                    cb.record_success()
                    return result

                except Exception as e:
                    error_msg = str(e).lower()
                    
                    # Identificar erros passíveis de retry (ex: 429 Rate Limit, 504 Gateway Timeout, Timeout do Asyncio, etc)
                    is_transient = any(x in error_msg for x in ["timeout", "429", "504", "502", "rate limit", "too many requests", "connection reset"])
                    
                    if not is_transient and not is_critical:
                        # Erro definitivo (ex: param inválido, auth error). O Circuit Breaker não precisa bater "Rate Limit"
                        logger.error(f"❌ [CIRCUIT BREAKER - {cb.name}] Erro definitivo em {func.__name__}: {e}")
                        cb.record_failure()
                        return fallback_return
                    
                    # Exponential Backoff
                    if retries < cb.max_retries:
                        sleep_time = cb.backoff_base * (2 ** retries)
                        logger.warning(f"⏳ [CIRCUIT BREAKER - {cb.name}] Falha transiente detectada ({e}). Exponential Backoff ativado. Tentando novamente em {sleep_time}s ({retries + 1}/{cb.max_retries})...")
                        await asyncio.sleep(sleep_time)
                        retries += 1
                        continue
                    else:
                        logger.error(f"💥 [CIRCUIT BREAKER - {cb.name}] Tentativas esgotadas para {func.__name__}. Registrando falha severa.")
                        cb.record_failure()
                        
                        if is_critical:
                            # Se for crítico (ex: Fechamento de Stop Loss), não retornamos o fallback, relançamos o erro para ser tratado
                            raise Exception(f"CRITICAL FAILURE AFTER MAX RETRIES in {func.__name__}: {e}")
                            
                        return fallback_return
                        
            return fallback_return
        return wrapper
    return decorator
