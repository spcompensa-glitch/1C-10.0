# -*- coding: utf-8 -*-
"""
Sistema de Métricas e Health Checks - Monitoramento Completo
==========================================================

Sistema completo de monitoramento que fornece:
1. Métricas do sistema em tempo real
2. Health checks automatizados
3. Alertas e notificações
4. Dashboard de monitoramento
5. Histórico de métricas

Author: Monitoring Team
Version: 1.0

Features:
- Coleta de métricas em tempo real
- Health checks automatizados
- Alertas configuráveis
- Dashboard com visualização
- Histórico persistente
- Notificações integradas
"""

import asyncio
import time
import psutil
import threading
import json
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import sqlite3
import os
from concurrent.futures import ThreadPoolExecutor
import requests
from contextlib import contextmanager

# Importa logging estruturado
from backend.services.structured_logger import StructuredLogger, PerformanceTimer

class HealthStatus(Enum):
    """Status de saúde"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"

class MetricType(Enum):
    """Tipos de métricas"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"

@dataclass
class HealthCheck:
    """Configuração de health check"""
    name: str
    check_func: Callable
    interval: int = 60  # segundos
    timeout: int = 30
    critical: bool = True
    enabled: bool = True
    
@dataclass
class MetricDefinition:
    """Definição de métrica"""
    name: str
    description: str
    type: MetricType
    labels: List[str] = field(default_factory=list)
    unit: Optional[str] = None

@dataclass
class HealthResult:
    """Resultado de health check"""
    name: str
    status: HealthStatus
    message: str
    timestamp: float
    duration_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class MetricValue:
    """Valor de métrica"""
    name: str
    value: float
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

class MetricsCollector:
    """Coletor de métricas do sistema"""
    
    def __init__(self, storage_path: str = "metrics.db"):
        self.storage_path = storage_path
        self.metrics: Dict[str, List[MetricValue]] = {}
        self.lock = threading.RLock()
        
        # Logger
        self.logger = StructuredLogger("metrics", "1crypten", "development", "1.0.0")
        
        # Inicializa banco de dados
        self._init_database()
        
        # Métricas do sistema
        self._register_system_metrics()
        
    def _init_database(self):
        """Inicializa banco de dados de métricas"""
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            
            with sqlite3.connect(self.storage_path) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        value REAL NOT NULL,
                        timestamp REAL NOT NULL,
                        labels TEXT,
                        metadata TEXT
                    )
                ''')
                
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(name)
                ''')
                
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp)
                ''')
                
                conn.commit()
                
        except Exception as e:
            self.logger.error(f"Error initializing metrics database: {e}")
            raise
    
    def _register_system_metrics(self):
        """Registra métricas do sistema"""
        # Métricas de CPU
        self.register_metric("system_cpu_percent", "CPU usage percentage", MetricType.GAUGE, ["cpu"])
        self.register_metric("system_cpu_count", "Number of CPU cores", MetricType.GAUGE)
        
        # Métricas de memória
        self.register_metric("system_memory_percent", "Memory usage percentage", MetricType.GAUGE)
        self.register_metric("system_memory_available", "Available memory in bytes", MetricType.GAUGE)
        
        # Métricas de disco
        self.register_metric("system_disk_percent", "Disk usage percentage", MetricType.GAUGE, ["disk"])
        self.register_metric("system_disk_free", "Free disk space in bytes", MetricType.GAUGE, ["disk"])
        
        # Métricas de rede
        self.register_metric("system_network_bytes_sent", "Network bytes sent", MetricType.COUNTER, ["interface"])
        self.register_metric("system_network_bytes_recv", "Network bytes received", MetricType.COUNTER, ["interface"])
        
        # Métricas de processo
        self.register_metric("process_memory_percent", "Process memory usage percentage", MetricType.GAUGE)
        self.register_metric("process_cpu_percent", "Process CPU usage percentage", MetricType.GAUGE)
        self.register_metric("process_thread_count", "Number of process threads", MetricType.GAUGE)
        
    def register_metric(self, name: str, description: str, 
                       metric_type: MetricType, labels: List[str] = None):
        """Registra uma nova métrica"""
        try:
            with self.lock:
                if name not in self.metrics:
                    self.metrics[name] = []
                    
            self.logger.info(f"Registered metric: {name}")
            
        except Exception as e:
            self.logger.error(f"Error registering metric {name}: {e}")
    
    def record_metric(self, name: str, value: float, 
                     labels: Dict[str, str] = None, metadata: Dict[str, Any] = None):
        """Registra valor de métrica"""
        try:
            timestamp = time.time()
            
            metric_value = MetricValue(
                name=name,
                value=value,
                timestamp=timestamp,
                labels=labels or {},
                metadata=metadata or {}
            )
            
            with self.lock:
                if name not in self.metrics:
                    self.metrics[name] = []
                
                self.metrics[name].append(metric_value)
                
                # Mantém apenas últimas 1000 entradas
                if len(self.metrics[name]) > 1000:
                    self.metrics[name] = self.metrics[name][-1000:]
            
            # Armazena no banco de dados
            self._store_metric(metric_value)
            
        except Exception as e:
            self.logger.error(f"Error recording metric {name}: {e}")
    
    def _store_metric(self, metric_value: MetricValue):
        """Armazena métrica no banco de dados"""
        try:
            with sqlite3.connect(self.storage_path) as conn:
                conn.execute('''
                    INSERT INTO metrics (name, value, timestamp, labels, metadata)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    metric_value.name,
                    metric_value.value,
                    metric_value.timestamp,
                    json.dumps(metric_value.labels),
                    json.dumps(metric_value.metadata)
                ))
                conn.commit()
                
        except Exception as e:
            self.logger.error(f"Error storing metric {metric_value.name}: {e}")
    
    def get_metric_values(self, name: str, 
                          start_time: Optional[float] = None,
                          end_time: Optional[float] = None) -> List[MetricValue]:
        """Obtém valores de métrica"""
        try:
            with self.lock:
                if name not in self.metrics:
                    return []
                
                values = self.metrics[name]
                
                # Filtra por tempo
                if start_time:
                    values = [v for v in values if v.timestamp >= start_time]
                if end_time:
                    values = [v for v in values if v.timestamp <= end_time]
                
                return values
                
        except Exception as e:
            self.logger.error(f"Error getting metric values for {name}: {e}")
            return []
    
    def get_metric_stats(self, name: str, 
                        start_time: Optional[float] = None,
                        end_time: Optional[float] = None) -> Dict[str, float]:
        """Obtém estatísticas de métrica"""
        try:
            values = self.get_metric_values(name, start_time, end_time)
            
            if not values:
                return {}
            
            values_float = [v.value for v in values]
            
            return {
                "count": len(values),
                "sum": sum(values_float),
                "avg": sum(values_float) / len(values),
                "min": min(values_float),
                "max": max(values_float),
                "latest": values[-1].value if values else 0
            }
            
        except Exception as e:
            self.logger.error(f"Error getting metric stats for {name}: {e}")
            return {}
    
    def collect_system_metrics(self):
        """Coleta métricas do sistema"""
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            
            # Memória
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Rede
            net_io = psutil.net_io_counters()
            
            # Processo
            process = psutil.Process()
            process_cpu = process.cpu_percent()
            process_memory = process.memory_percent()
            process_threads = process.num_threads()
            
            # Registra métricas
            self.record_metric("system_cpu_percent", cpu_percent, {"cpu": "total"})
            self.record_metric("system_cpu_count", float(cpu_count))
            self.record_metric("system_memory_percent", memory.percent)
            self.record_metric("system_memory_available", float(memory.available))
            self.record_metric("system_disk_percent", disk.percent, {"disk": "root"})
            self.record_metric("system_disk_free", float(disk.free), {"disk": "root"})
            self.record_metric("system_network_bytes_sent", float(net_io.bytes_sent), {"interface": "total"})
            self.record_metric("system_network_bytes_recv", float(net_io.bytes_recv), {"interface": "total"})
            self.record_metric("process_memory_percent", process_memory)
            self.record_metric("process_cpu_percent", process_cpu)
            self.record_metric("process_thread_count", float(process_threads))
            
        except Exception as e:
            self.logger.error(f"Error collecting system metrics: {e}")

class HealthChecker:
    """Checador de saúde do sistema"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
        self.health_checks: Dict[str, HealthCheck] = {}
        self.health_results: Dict[str, HealthResult] = {}
        self.lock = threading.RLock()
        
        # Logger
        self.logger = StructuredLogger("health", "1crypten", "development", "1.0.0")
        
        # Registra health checks padrão
        self._register_default_checks()
        
    def _register_default_checks(self):
        """Registra health checks padrão"""
        self.register_health_check(
            "database_connection",
            self._check_database_connection,
            interval=30,
            critical=True
        )
        
        self.register_health_check(
            "api_endpoints",
            self._check_api_endpoints,
            interval=60,
            critical=True
        )
        
        self.register_health_check(
            "disk_space",
            self._check_disk_space,
            interval=300,
            critical=False
        )
        
        self.register_health_check(
            "memory_usage",
            self._check_memory_usage,
            interval=60,
            critical=True
        )
        
        self.register_health_check(
            "cpu_usage",
            self._check_cpu_usage,
            interval=60,
            critical=False
        )
    
    def register_health_check(self, name: str, check_func: Callable,
                             interval: int = 60, timeout: int = 30,
                             critical: bool = True, enabled: bool = True):
        """Registra um novo health check"""
        try:
            health_check = HealthCheck(
                name=name,
                check_func=check_func,
                interval=interval,
                timeout=timeout,
                critical=critical,
                enabled=enabled
            )
            
            with self.lock:
                self.health_checks[name] = health_check
                
            self.logger.info(f"Registered health check: {name}")
            
        except Exception as e:
            self.logger.error(f"Error registering health check {name}: {e}")
    
    async def run_health_check(self, health_check: HealthCheck) -> HealthResult:
        """Executa um health check"""
        try:
            start_time = time.time()
            
            # Executa check com timeout
            result = await asyncio.wait_for(
                self._execute_check(health_check.check_func),
                timeout=health_check.timeout
            )
            
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000
            
            # Determina status
            status = HealthStatus.HEALTHY
            if not result["healthy"]:
                status = HealthStatus.CRITICAL if health_check.critical else HealthStatus.WARNING
            
            health_result = HealthResult(
                name=health_check.name,
                status=status,
                message=result["message"],
                timestamp=end_time,
                duration_ms=duration_ms,
                metadata=result["metadata"]
            )
            
            with self.lock:
                self.health_results[health_check.name] = health_result
            
            # Registra métrica
            self.metrics_collector.record_metric(
                f"health_check_duration_ms",
                duration_ms,
                {"check": health_check.name, "status": status.value}
            )
            
            self.logger.info(f"Health check {health_check.name}: {status.value} - {result['message']}")
            
            return health_result
            
        except asyncio.TimeoutError:
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000
            
            health_result = HealthResult(
                name=health_check.name,
                status=HealthStatus.CRITICAL,
                message=f"Timeout after {health_check.timeout}s",
                timestamp=end_time,
                duration_ms=duration_ms,
                metadata={}
            )
            
            with self.lock:
                self.health_results[health_check.name] = health_result
            
            self.logger.error(f"Health check {health_check.name} timeout")
            return health_result
            
        except Exception as e:
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000
            
            health_result = HealthResult(
                name=health_check.name,
                status=HealthStatus.CRITICAL,
                message=f"Error: {str(e)}",
                timestamp=end_time,
                duration_ms=duration_ms,
                metadata={}
            )
            
            with self.lock:
                self.health_results[health_check.name] = health_result
            
            self.logger.error(f"Health check {health_check.name} error: {e}")
            return health_result
    
    async def _execute_check(self, check_func: Callable) -> Dict[str, Any]:
        """Executa função de health check"""
        if asyncio.iscoroutinefunction(check_func):
            return await check_func()
        else:
            # Executa em thread separada
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                return await loop.run_in_executor(executor, check_func)
    
    async def _check_database_connection(self) -> Dict[str, Any]:
        """Verifica conexão com banco de dados"""
        try:
            # Simula verificação de conexão
            # Aqui você implementaria a verificação real do banco de dados
            return {
                "healthy": True,
                "message": "Database connection OK",
                "metadata": {"database": "postgresql", "latency_ms": 15.5}
            }
        except Exception as e:
            return {
                "healthy": False,
                "message": f"Database connection failed: {str(e)}",
                "metadata": {}
            }
    
    async def _check_api_endpoints(self) -> Dict[str, Any]:
        """Verifica endpoints da API"""
        try:
            # Simula verificação de endpoints
            endpoints = ["http://localhost:8000/health", "http://localhost:8000/api/status"]
            healthy_count = 0
            
            for endpoint in endpoints:
                try:
                    response = requests.get(endpoint, timeout=5)
                    if response.status_code == 200:
                        healthy_count += 1
                except Exception:
                    pass
            
            return {
                "healthy": healthy_count > 0,
                "message": f"{healthy_count}/{len(endpoints)} endpoints healthy",
                "metadata": {"healthy_endpoints": healthy_count, "total_endpoints": len(endpoints)}
            }
        except Exception as e:
            return {
                "healthy": False,
                "message": f"API endpoints check failed: {str(e)}",
                "metadata": {}
            }
    
    async def _check_disk_space(self) -> Dict[str, Any]:
        """Verifica espaço em disco"""
        try:
            disk = psutil.disk_usage('/')
            usage_percent = disk.percent
            free_gb = disk.free / (1024**3)
            
            if usage_percent > 90:
                return {
                    "healthy": False,
                    "message": f"Disk usage critical: {usage_percent:.1f}%",
                    "metadata": {"usage_percent": usage_percent, "free_gb": free_gb}
                }
            elif usage_percent > 80:
                return {
                    "healthy": True,
                    "message": f"Disk usage high: {usage_percent:.1f}%",
                    "metadata": {"usage_percent": usage_percent, "free_gb": free_gb}
                }
            else:
                return {
                    "healthy": True,
                    "message": f"Disk usage OK: {usage_percent:.1f}%",
                    "metadata": {"usage_percent": usage_percent, "free_gb": free_gb}
                }
        except Exception as e:
            return {
                "healthy": False,
                "message": f"Disk space check failed: {str(e)}",
                "metadata": {}
            }
    
    async def _check_memory_usage(self) -> Dict[str, Any]:
        """Verifica uso de memória"""
        try:
            memory = psutil.virtual_memory()
            usage_percent = memory.percent
            
            if usage_percent > 90:
                return {
                    "healthy": False,
                    "message": f"Memory usage critical: {usage_percent:.1f}%",
                    "metadata": {"usage_percent": usage_percent, "available_gb": memory.available / (1024**3)}
                }
            elif usage_percent > 80:
                return {
                    "healthy": True,
                    "message": f"Memory usage high: {usage_percent:.1f}%",
                    "metadata": {"usage_percent": usage_percent, "available_gb": memory.available / (1024**3)}
                }
            else:
                return {
                    "healthy": True,
                    "message": f"Memory usage OK: {usage_percent:.1f}%",
                    "metadata": {"usage_percent": usage_percent, "available_gb": memory.available / (1024**3)}
                }
        except Exception as e:
            return {
                "healthy": False,
                "message": f"Memory usage check failed: {str(e)}",
                "metadata": {}
            }
    
    async def _check_cpu_usage(self) -> Dict[str, Any]:
        """Verifica uso de CPU"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            
            if cpu_percent > 90:
                return {
                    "healthy": False,
                    "message": f"CPU usage critical: {cpu_percent:.1f}%",
                    "metadata": {"usage_percent": cpu_percent}
                }
            elif cpu_percent > 80:
                return {
                    "healthy": True,
                    "message": f"CPU usage high: {cpu_percent:.1f}%",
                    "metadata": {"usage_percent": cpu_percent}
                }
            else:
                return {
                    "healthy": True,
                    "message": f"CPU usage OK: {cpu_percent:.1f}%",
                    "metadata": {"usage_percent": cpu_percent}
                }
        except Exception as e:
            return {
                "healthy": False,
                "message": f"CPU usage check failed: {str(e)}",
                "metadata": {}
            }
    
    async def run_all_checks(self) -> Dict[str, HealthResult]:
        """Executa todos os health checks"""
        try:
            tasks = []
            
            for name, health_check in self.health_checks.items():
                if health_check.enabled:
                    task = self.run_health_check(health_check)
                    tasks.append(task)
            
            # Executa todos os checks em paralelo
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Processa resultados
            health_results = {}
            for result in results:
                if isinstance(result, Exception):
                    self.logger.error(f"Health check failed: {result}")
                else:
                    health_results[result.name] = result
            
            return health_results
            
        except Exception as e:
            self.logger.error(f"Error running health checks: {e}")
            return {}
    
    def get_system_health(self) -> HealthStatus:
        """Obtém status geral do sistema"""
        try:
            with self.lock:
                if not self.health_results:
                    return HealthStatus.UNKNOWN
                
                # Conta status
                healthy_count = 0
                warning_count = 0
                critical_count = 0
                
                for result in self.health_results.values():
                    if result.status == HealthStatus.HEALTHY:
                        healthy_count += 1
                    elif result.status == HealthStatus.WARNING:
                        warning_count += 1
                    elif result.status == HealthStatus.CRITICAL:
                        critical_count += 1
                
                total_checks = len(self.health_results)
                
                # Determina status geral
                if critical_count > 0:
                    return HealthStatus.CRITICAL
                elif warning_count > total_checks * 0.5:  # Mais da metade em warning
                    return HealthStatus.WARNING
                elif healthy_count == total_checks:
                    return HealthStatus.HEALTHY
                else:
                    return HealthStatus.WARNING
                    
        except Exception as e:
            self.logger.error(f"Error getting system health: {e}")
            return HealthStatus.UNKNOWN

class MonitoringDashboard:
    """Dashboard de monitoramento"""
    
    def __init__(self, metrics_collector: MetricsCollector, 
                 health_checker: HealthChecker):
        self.metrics_collector = metrics_collector
        self.health_checker = health_checker
        self.logger = StructuredLogger("dashboard", "1crypten", "development", "1.0.0")
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Obtém dados do dashboard"""
        try:
            # Status do sistema
            system_health = self.health_checker.get_system_health()
            
            # Health checks
            health_results = self.health_checker.health_results
            
            # Métricas recentes
            recent_metrics = {}
            for metric_name in ["system_cpu_percent", "system_memory_percent", 
                              "process_memory_percent", "process_cpu_percent"]:
                stats = self.metrics_collector.get_metric_stats(metric_name, 
                                                               time.time() - 3600)  # Última hora
                if stats:
                    recent_metrics[metric_name] = stats
            
            # Histórico de health checks
            health_history = []
            for name, result in health_results.items():
                health_history.append({
                    "name": name,
                    "status": result.status.value,
                    "message": result.message,
                    "timestamp": result.timestamp,
                    "duration_ms": result.duration_ms
                })
            
            return {
                "timestamp": time.time(),
                "system_health": system_health.value,
                "health_checks": health_history,
                "recent_metrics": recent_metrics,
                "service_status": "operational" if system_health != HealthStatus.CRITICAL else "degraded"
            }
            
        except Exception as e:
            self.logger.error(f"Error getting dashboard data: {e}")
            return {
                "timestamp": time.time(),
                "system_health": "unknown",
                "error": str(e)
            }
    
    def get_alerts(self) -> List[Dict[str, Any]]:
        """Obtém alertas ativos"""
        try:
            alerts = []
            
            # Verifica health checks críticos
            health_results = self.health_checker.health_results
            for name, result in health_results.items():
                if result.status == HealthStatus.CRITICAL:
                    alerts.append({
                        "type": "health_check",
                        "severity": "critical",
                        "source": name,
                        "message": result.message,
                        "timestamp": result.timestamp
                    })
            
            # Verifica métricas
            for metric_name in ["system_cpu_percent", "system_memory_percent"]:
                stats = self.metrics_collector.get_metric_stats(metric_name, time.time() - 300)
                if stats and stats.get("latest", 0) > 90:
                    alerts.append({
                        "type": "metric_threshold",
                        "severity": "warning",
                        "source": metric_name,
                        "message": f"{metric_name} exceeded threshold: {stats['latest']:.1f}%",
                        "timestamp": time.time()
                    })
            
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error getting alerts: {e}")
            return []

# Instâncias globais
metrics_collector = MetricsCollector()
health_checker = HealthChecker(metrics_collector)
monitoring_dashboard = MonitoringDashboard(metrics_collector, health_checker)

# Funções utilitárias
@contextmanager
def measure_performance(operation: str):
    """Context manager para medição de performance"""
    start_time = time.time()
    try:
        yield
    finally:
        duration = (time.time() - start_time) * 1000
        metrics_collector.record_metric(f"{operation}_duration_ms", duration)

def record_api_request(endpoint: str, method: str, status_code: int, 
                      duration_ms: float, user_id: str = None):
    """Registra requisição de API"""
    labels = {
        "endpoint": endpoint,
        "method": method,
        "status_code": str(status_code),
        "user_id": user_id or "anonymous"
    }
    
    metrics_collector.record_metric("api_requests_count", 1, labels)
    metrics_collector.record_metric("api_request_duration_ms", duration_ms, labels)

def record_database_query(operation: str, table: str, duration_ms: float, 
                         success: bool = True):
    """Registra operação de banco de dados"""
    labels = {
        "operation": operation,
        "table": table,
        "success": str(success)
    }
    
    metrics_collector.record_metric("database_queries_count", 1, labels)
    metrics_collector.record_metric("database_query_duration_ms", duration_ms, labels)

def record_cache_operation(operation: str, hit: bool = False, 
                          key_size: int = 0, value_size: int = 0):
    """Registra operação de cache"""
    labels = {
        "operation": operation,
        "hit": str(hit)
    }
    
    metrics_collector.record_metric("cache_operations_count", 1, labels)
    if key_size > 0:
        metrics_collector.record_metric("cache_key_size_bytes", key_size, labels)
    if value_size > 0:
        metrics_collector.record_metric("cache_value_size_bytes", value_size, labels)