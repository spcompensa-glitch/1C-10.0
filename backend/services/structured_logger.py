# -*- coding: utf-8 -*-
"""
Structured Logger - Sistema de Logging Estruturado JSON
=======================================================

Sistema de logging estruturado que gera logs em formato JSON
padronizado, com tracing, metadados e facilidade de análise.

Author: Logging Team
Version: 1.0

Features:
- Logs em formato JSON estruturado
- Trace ID e correlation ID
- Níveis de log personalizados
- Formatação padronizada
- Suporte a contexto e metadados
- Rotacionamento de arquivos
- Filtros por ambiente e serviço
"""

import json
import logging
import logging.handlers
import time
import uuid
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum
import os
from contextlib import contextmanager

class LogLevel(Enum):
    """Níveis de log personalizados"""
    TRACE = 5
    DEBUG = 10
    INFO = 20
    WARN = 30
    ERROR = 40
    FATAL = 50

@dataclass
class LogContext:
    """Contexto de log com metadados"""
    trace_id: str
    correlation_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    service: Optional[str] = None
    component: Optional[str] = None
    environment: Optional[str] = None
    version: Optional[str] = None
    
@dataclass
class LogEntry:
    """Entrada de log estruturada"""
    timestamp: str
    level: str
    message: str
    trace_id: str
    correlation_id: str
    service: str
    component: str
    environment: str
    version: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    duration_ms: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    stack_trace: Optional[str] = None

class StructuredLogger:
    """
    Logger estruturado que gera logs em formato JSON.
    
    Features:
    - Logs em formato JSON padronizado
    - Trace ID e correlation ID automáticos
    - Contexto de log global e local
    - Metadados estruturados
    - Formatação consistente
    """
    
    def __init__(self, name: str, service: str = "1crypten", 
                 environment: str = "development", version: str = "1.0.0"):
        self.name = name
        self.service = service
        self.environment = environment
        self.version = version
        
        # Configura logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # Handler para console
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        
        # Handler para arquivo
        file_handler = logging.handlers.RotatingFileHandler(
            f"logs/{name}.log",
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.INFO)
        
        # Formato JSON
        json_formatter = StructuredFormatter()
        console_handler.setFormatter(json_formatter)
        file_handler.setFormatter(json_formatter)
        
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
        
        # Contexto global
        self._global_context = LogContext(
            trace_id=str(uuid.uuid4()),
            correlation_id=str(uuid.uuid4()),
            service=service,
            component=name,
            environment=environment,
            version=version
        )
        
        # Lock para thread safety
        self._lock = threading.RLock()
        
        # Cria diretório de logs
        os.makedirs("logs", exist_ok=True)
    
    def _create_log_entry(self, level: LogLevel, message: str, 
                         context: Optional[LogContext] = None,
                         metadata: Optional[Dict[str, Any]] = None,
                         error: Optional[Exception] = None,
                         duration_ms: Optional[float] = None) -> LogEntry:
        """Cria entrada de log estruturada"""
        
        # Mescla contexto global com contexto local
        final_context = context or self._global_context
        if context:
            # Sobrescreve valores do contexto global
            final_context = LogContext(
                trace_id=context.trace_id or final_context.trace_id,
                correlation_id=context.correlation_id or final_context.correlation_id,
                user_id=context.user_id or final_context.user_id,
                session_id=context.session_id or final_context.session_id,
                request_id=context.request_id or final_context.request_id,
                service=context.service or final_context.service,
                component=context.component or final_context.component,
                environment=context.environment or final_context.environment,
                version=context.version or final_context.version
            )
        
        # Formata timestamp
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        # Formata error
        error_dict = None
        stack_trace = None
        if error:
            error_dict = {
                "type": type(error).__name__,
                "message": str(error),
                "code": getattr(error, 'code', None),
                "details": getattr(error, 'details', None)
            }
            
            # Captura stack trace apenas para ERROR e FATAL
            if level in [LogLevel.ERROR, LogLevel.FATAL]:
                import traceback
                stack_trace = traceback.format_exc()
        
        # Cria entrada
        entry = LogEntry(
            timestamp=timestamp,
            level=level.name,
            message=message,
            trace_id=final_context.trace_id,
            correlation_id=final_context.correlation_id,
            service=final_context.service,
            component=final_context.component,
            environment=final_context.environment,
            version=final_context.version,
            user_id=final_context.user_id,
            session_id=final_context.session_id,
            request_id=final_context.request_id,
            duration_ms=duration_ms,
            metadata=metadata,
            error=error_dict,
            stack_trace=stack_trace
        )
        
        return entry
    
    def _log_entry(self, entry: LogEntry):
        """Registra entrada de log"""
        try:
            with self._lock:
                # Converte para JSON
                log_json = json.dumps(asdict(entry), ensure_ascii=False)
                
                # Envia para logger
                level_value = LogLevel[entry.level].value
                self.logger.log(level_value, log_json)
                
        except Exception as e:
            # Fallback para log normal
            self.logger.error(f"Error structured logging: {e}")
            self.logger.error(f"Original entry: {entry}")
    
    def trace(self, message: str, context: Optional[LogContext] = None,
              metadata: Optional[Dict[str, Any]] = None):
        """Log de nível TRACE"""
        entry = self._create_log_entry(LogLevel.TRACE, message, context, metadata)
        self._log_entry(entry)
    
    def debug(self, message: str, context: Optional[LogContext] = None,
              metadata: Optional[Dict[str, Any]] = None):
        """Log de nível DEBUG"""
        entry = self._create_log_entry(LogLevel.DEBUG, message, context, metadata)
        self._log_entry(entry)
    
    def info(self, message: str, context: Optional[LogContext] = None,
             metadata: Optional[Dict[str, Any]] = None):
        """Log de nível INFO"""
        entry = self._create_log_entry(LogLevel.INFO, message, context, metadata)
        self._log_entry(entry)
    
    def warn(self, message: str, context: Optional[LogContext] = None,
             metadata: Optional[Dict[str, Any]] = None):
        """Log de nível WARN"""
        entry = self._create_log_entry(LogLevel.WARN, message, context, metadata)
        self._log_entry(entry)
    
    def error(self, message: str, error: Optional[Exception] = None,
              context: Optional[LogContext] = None,
              metadata: Optional[Dict[str, Any]] = None):
        """Log de nível ERROR"""
        entry = self._create_log_entry(LogLevel.ERROR, message, context, metadata, error)
        self._log_entry(entry)
    
    def fatal(self, message: str, error: Optional[Exception] = None,
              context: Optional[LogContext] = None,
              metadata: Optional[Dict[str, Any]] = None):
        """Log de nível FATAL"""
        entry = self._create_log_entry(LogLevel.FATAL, message, context, metadata, error)
        self._log_entry(entry)
    
    @contextmanager
    def context(self, **kwargs):
        """Context manager para log context"""
        # Salva contexto atual
        old_context = self._global_context
        
        # Cria novo contexto
        new_context = LogContext(
            trace_id=kwargs.get('trace_id', old_context.trace_id),
            correlation_id=kwargs.get('correlation_id', old_context.correlation_id),
            user_id=kwargs.get('user_id', old_context.user_id),
            session_id=kwargs.get('session_id', old_context.session_id),
            request_id=kwargs.get('request_id', old_context.request_id),
            service=kwargs.get('service', old_context.service),
            component=kwargs.get('component', old_context.component),
            environment=kwargs.get('environment', old_context.environment),
            version=kwargs.get('version', old_context.version)
        )
        
        # Atualiza contexto global
        self._global_context = new_context
        
        try:
            yield new_context
        finally:
            # Restaura contexto original
            self._global_context = old_context
    
    def log_performance(self, operation: str, duration_ms: float, 
                       metadata: Optional[Dict[str, Any]] = None):
        """Log de performance"""
        entry = self._create_log_entry(
            LogLevel.INFO,
            f"Performance: {operation} took {duration_ms:.2f}ms",
            metadata={**(metadata or {}), "operation": operation, "duration_ms": duration_ms}
        )
        self._log_entry(entry)
    
    def log_security_event(self, event_type: str, severity: str, 
                          message: str, metadata: Optional[Dict[str, Any]] = None):
        """Log de evento de segurança"""
        entry = self._create_log_entry(
            LogLevel.WARN if severity == "WARNING" else LogLevel.ERROR,
            f"Security Event: {event_type} - {message}",
            metadata={**(metadata or {}), "event_type": event_type, "severity": severity}
        )
        self._log_entry(entry)

class StructuredFormatter(logging.Formatter):
    """Formatação JSON para logs"""
    
    def format(self, record):
        """Formata record em JSON"""
        try:
            # Converte record para dicionário
            log_data = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat() + "Z",
                "level": record.levelname,
                "message": record.getMessage(),
                "logger": record.name,
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
                "thread": record.thread,
                "thread_name": record.threadName
            }
            
            # Adiciona campos extras
            if hasattr(record, 'trace_id'):
                log_data["trace_id"] = record.trace_id
            if hasattr(record, 'correlation_id'):
                log_data["correlation_id"] = record.correlation_id
            if hasattr(record, 'user_id'):
                log_data["user_id"] = record.user_id
            if hasattr(record, 'service'):
                log_data["service"] = record.service
            if hasattr(record, 'component'):
                log_data["component"] = record.component
                
            # Adiciona extras como metadados
            if hasattr(record, 'metadata'):
                log_data["metadata"] = record.metadata
            if hasattr(record, 'error'):
                log_data["error"] = record.error
            
            return json.dumps(log_data, ensure_ascii=False)
            
        except Exception as e:
            # Fallback para log normal
            return super().format(record)

class PerformanceTimer:
    """Timer para medição de performance"""
    
    def __init__(self, logger: StructuredLogger, operation: str, 
                 metadata: Optional[Dict[str, Any]] = None):
        self.logger = logger
        self.operation = operation
        self.metadata = metadata or {}
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration_ms = (self.end_time - self.start_time) * 1000
        
        if exc_type:
            self.logger.error(
                f"Error in {self.operation}",
                error=exc_val,
                metadata={**self.metadata, "operation": self.operation, "duration_ms": duration_ms}
            )
        else:
            self.logger.log_performance(
                self.operation,
                duration_ms,
                self.metadata
            )

# Instâncias globais de loggers
app_logger = StructuredLogger("app", "1crypten", "development", "1.0.0")
auth_logger = StructuredLogger("auth", "1crypten", "development", "1.0.0")
database_logger = StructuredLogger("database", "1crypten", "development", "1.0.0")
security_logger = StructuredLogger("security", "1crypten", "development", "1.0.0")
performance_logger = StructuredLogger("performance", "1crypten", "development", "1.0.0")

# Funções utilitárias
def get_logger(name: str, service: str = "1crypten", 
               environment: str = "development", version: str = "1.0.0") -> StructuredLogger:
    """Obtém logger estruturado"""
    return StructuredLogger(name, service, environment, version)

def log_transaction(transaction_id: str, amount: float, currency: str, 
                   user_id: str, status: str, metadata: Optional[Dict[str, Any]] = None):
    """Log de transação"""
    app_logger.info(
        f"Transaction: {transaction_id} - {amount} {currency} - {status}",
        metadata={**(metadata or {}), "transaction_id": transaction_id, "amount": amount, 
                 "currency": currency, "user_id": user_id, "status": status}
    )

def log_user_action(user_id: str, action: str, resource: str, 
                   result: str, metadata: Optional[Dict[str, Any]] = None):
    """Log de ação de usuário"""
    app_logger.info(
        f"User Action: {user_id} - {action} {resource} - {result}",
        metadata={**(metadata or {}), "user_id": user_id, "action": action, 
                 "resource": resource, "result": result}
    )

def log_api_request(endpoint: str, method: str, status_code: int, 
                   duration_ms: float, user_id: str, metadata: Optional[Dict[str, Any]] = None):
    """Log de requisição API"""
    app_logger.info(
        f"API Request: {method} {endpoint} - {status_code} - {duration_ms}ms",
        metadata={**(metadata or {}), "endpoint": endpoint, "method": method, 
                 "status_code": status_code, "duration_ms": duration_ms, "user_id": user_id}
    )

def log_security_event(event_type: str, severity: str, message: str, 
                      user_id: str, ip_address: str, metadata: Optional[Dict[str, Any]] = None):
    """Log de evento de segurança"""
    security_logger.log_security_event(
        event_type,
        severity,
        message,
        {**(metadata or {}), "user_id": user_id, "ip_address": ip_address}
    )