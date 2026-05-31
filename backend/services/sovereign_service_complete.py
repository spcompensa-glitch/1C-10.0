# -*- coding: utf-8 -*-
"""
Sovereign Service - Sistema Completo de Governança e Orquestração
=================================================================

Sistema centralizado de governança que gerencia todos os serviços do 1Cryptem,
coordena operações, fornece visão unificada e implementa padrões de segurança.

Author: Architecture Team  
Version: 1.0

Core Features:
- Orquestração de serviços
- Gestão de estado global
- Monitoramento de saúde
- Padrões de segurança
- Configuração centralizada
- Auditoria e logging
"""

import asyncio
import logging
import time
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import threading
from concurrent.futures import ThreadPoolExecutor

from services.secrets import secrets_manager
from services.safe_cache import get_cache
from services.database_service import DatabaseService
from services.okx_service import OKXService
from services.auth_service import auth_service

logger = logging.getLogger("SovereignService")

class ServiceStatus(Enum):
    """Status dos serviços do sistema"""
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"
    MAINTENANCE = "MAINTENANCE"

class SystemHealth(Enum):
    """Saúde do sistema"""
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    DOWN = "DOWN"

@dataclass
class ServiceInfo:
    """Informações de um serviço"""
    name: str
    status: ServiceStatus
    health: SystemHealth
    last_check: float
    error_count: int = 0
    restart_count: int = 0
    memory_usage: float = 0.0
    cpu_usage: float = 0.0
    uptime: float = 0.0
    
@dataclass
class SystemMetrics:
    """Métricas do sistema"""
    timestamp: float
    total_services: int
    healthy_services: int
    unhealthy_services: int
    error_rate: float
    avg_response_time: float
    total_memory_usage: float
    total_cpu_usage: float
    active_connections: int
    
@dataclass
class SecurityEvent:
    """Eventos de segurança"""
    timestamp: float
    service: str
    event_type: str
    severity: str
    message: str
    details: Dict[str, Any]

class SovereignService:
    """
    Serviço soberano central do 1Cryptem.
    
    Responsável por:
    1. Orquestrar todos os serviços do sistema
    2. Monitorar saúde e desempenho
    3. Implementar padrões de segurança
    4. Gerenciar configuração centralizada
    5. Prover visão unificada do sistema
    """
    
    def __init__(self):
        self.services: Dict[str, ServiceInfo] = {}
        self.metrics_history: List[SystemMetrics] = []
        self.security_events: List[SecurityEvent] = []
        self.config: Dict[str, Any] = {}
        self.running = False
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.monitor_task: Optional[asyncio.Task] = None
        self.cache = get_cache()
        
        # Serviços essenciais
        self.essential_services = [
            "auth_service",
            "database_service", 
            "okx_service",
            "signal_generator",
            "captain_agent"
        ]
        
        # Inicialização
        self._initialize_config()
        
    def _initialize_config(self):
        """Configuração inicial do serviço"""
        try:
            self.config = {
                "security": {
                    "jwt_expiration_minutes": 60 * 24 * 7,
                    "max_login_attempts": 5,
                    "session_timeout": 3600,
                    "audit_log_enabled": True
                },
                "performance": {
                    "cache_ttl": 300,
                    "max_concurrent_requests": 100,
                    "request_timeout": 30,
                    "health_check_interval": 60
                },
                "monitoring": {
                    "metrics_retention_days": 7,
                    "alert_thresholds": {
                        "cpu_usage": 80.0,
                        "memory_usage": 85.0,
                        "error_rate": 5.0,
                        "response_time": 1000.0
                    }
                },
                "orchestration": {
                    "service_restart_attempts": 3,
                    "service_start_timeout": 30,
                    "graceful_shutdown_timeout": 60
                }
            }
            
            logger.info("🏛️ [SOVEREIGN] Configuração inicializada")
            
        except Exception as e:
            logger.error(f"❌ [SOVEREIGN] Erro na inicialização: {e}")
            raise
    
    def register_service(self, name: str, service: Any) -> bool:
        """
        Registra um serviço no sistema soberano
        
        Args:
            name: Nome do serviço
            service: Instância do serviço
        
        Returns:
            bool: True se registrado com sucesso
        """
        try:
            with self.lock:
                service_info = ServiceInfo(
                    name=name,
                    status=ServiceStatus.INITIALIZING,
                    health=SystemHealth.GOOD,
                    last_check=time.time()
                )
                
                self.services[name] = service_info
                
                # Inicializa o serviço
                if hasattr(service, 'initialize'):
                    asyncio.create_task(service.initialize())
                
                logger.info(f"📋 [SOVEREIGN] Serviço registrado: {name}")
                return True
                
        except Exception as e:
            logger.error(f"❌ [SOVEREIGN] Erro ao registrar {name}: {e}")
            return False
    
    async def start_service(self, name: str) -> bool:
        """
        Inicia um serviço
        
        Args:
            name: Nome do serviço
        
        Returns:
            bool: True se iniciado com sucesso
        """
        try:
            with self.lock:
                if name not in self.services:
                    logger.error(f"❌ [SOVEREIGN] Serviço não encontrado: {name}")
                    return False
                
                service_info = self.services[name]
                
                # Verifica se é essencial
                is_essential = name in self.essential_services
                
                # Tenta iniciar o serviço
                if hasattr(self.services[name], 'start'):
                    await self.services[name].start()
                
                # Atualiza status
                service_info.status = ServiceStatus.RUNNING
                service_info.last_check = time.time()
                
                logger.info(f"🚀 [SOVEREIGN] Serviço iniciado: {name} ({'ESSENCIAL' if is_essential else 'REGULAR'})")
                return True
                
        except Exception as e:
            logger.error(f"❌ [SOVEREIGN] Erro ao iniciar {name}: {e}")
            
            with self.lock:
                if name in self.services:
                    self.services[name].status = ServiceStatus.ERROR
                    self.services[name].error_count += 1
            
            return False
    
    async def stop_service(self, name: str) -> bool:
        """
        Para um serviço
        
        Args:
            name: Nome do serviço
        
        Returns:
            bool: True se parado com sucesso
        """
        try:
            with self.lock:
                if name not in self.services:
                    logger.error(f"❌ [SOVEREIGN] Serviço não encontrado: {name}")
                    return False
                
                service_info = self.services[name]
                
                # Tenta parar o serviço
                if hasattr(self.services[name], 'stop'):
                    await self.services[name].stop()
                
                # Atualiza status
                service_info.status = ServiceStatus.STOPPED
                service_info.last_check = time.time()
                
                logger.info(f"🛑 [SOVEREIGN] Serviço parado: {name}")
                return True
                
        except Exception as e:
            logger.error(f"❌ [SOVEREIGN] Erro ao parar {name}: {e}")
            return False
    
    async def restart_service(self, name: str) -> bool:
        """
        Reinicia um serviço
        
        Args:
            name: Nome do serviço
        
        Returns:
            bool: True se reiniciado com sucesso
        """
        try:
            logger.info(f"🔄 [SOVEREIGN] Reiniciando serviço: {name}")
            
            # Para o serviço
            await self.stop_service(name)
            
            # Inicia o serviço
            if await self.start_service(name):
                with self.lock:
                    if name in self.services:
                        self.services[name].restart_count += 1
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ [SOVEREIGN] Erro ao reiniciar {name}: {e}")
            return False
    
    async def check_service_health(self, name: str) -> SystemHealth:
        """
        Verifica a saúde de um serviço
        
        Args:
            name: Nome do serviço
        
        Returns:
            SystemHealth: Saúde do serviço
        """
        try:
            if name not in self.services:
                return SystemHealth.DOWN
            
            service_info = self.services[name]
            
            # Verifica se o serviço está respondendo
            if hasattr(self.services[name], 'health_check'):
                is_healthy = await self.services[name].health_check()
            else:
                is_healthy = True  # Assume saudável se não tiver health_check
            
            # Atualiza status
            if is_healthy:
                service_info.health = SystemHealth.GOOD
                service_info.error_count = 0
            else:
                service_info.health = SystemHealth.WARNING
                service_info.error_count += 1
            
            service_info.last_check = time.time()
            
            return service_info.health
            
        except Exception as e:
            logger.error(f"❌ [SOVEREIGN] Erro ao verificar saúde de {name}: {e}")
            
            with self.lock:
                if name in self.services:
                    self.services[name].health = SystemHealth.CRITICAL
            
            return SystemHealth.CRITICAL
    
    async def get_system_health(self) -> SystemHealth:
        """
        Verifica a saúde geral do sistema
        
        Returns:
            SystemHealth: Saúde do sistema
        """
        try:
            healthy_count = 0
            total_count = len(self.services)
            
            # Verifica saúde de todos os serviços
            health_checks = []
            for name in self.services:
                check_task = self.check_service_health(name)
                health_checks.append(check_task)
            
            # Executa todas as verificações
            results = await asyncio.gather(*health_checks, return_exceptions=True)
            
            # Processa resultados
            for result in results:
                if isinstance(result, Exception):
                    continue
                if result == SystemHealth.GOOD:
                    healthy_count += 1
            
            # Calcula saúde do sistema
            if total_count == 0:
                return SystemHealth.DOWN
            
            health_ratio = healthy_count / total_count
            
            if health_ratio == 1.0:
                return SystemHealth.EXCELLENT
            elif health_ratio >= 0.8:
                return SystemHealth.GOOD
            elif health_ratio >= 0.6:
                return SystemHealth.WARNING
            else:
                return SystemHealth.CRITICAL
                
        except Exception as e:
            logger.error(f"❌ [SOVEREIGN] Erro ao verificar saúde do sistema: {e}")
            return SystemHealth.CRITICAL
    
    async def collect_system_metrics(self) -> SystemMetrics:
        """
        Coleta métricas do sistema
        
        Returns:
            SystemMetrics: Métricas coletadas
        """
        try:
            timestamp = time.time()
            healthy_count = 0
            unhealthy_count = 0
            total_memory = 0.0
            total_cpu = 0.0
            
            # Coleta métricas de cada serviço
            for name, service_info in self.services.items():
                if service_info.health == SystemHealth.GOOD:
                    healthy_count += 1
                else:
                    unhealthy_count += 1
                
                total_memory += service_info.memory_usage
                total_cpu += service_info.cpu_usage
            
            # Calcula métricas
            total_services = len(self.services)
            error_rate = (unhealthy_count / total_services * 100) if total_services > 0 else 0
            
            metrics = SystemMetrics(
                timestamp=timestamp,
                total_services=total_services,
                healthy_services=healthy_count,
                unhealthy_services=unhealthy_count,
                error_rate=error_rate,
                avg_response_time=0.0,  # Implementar conforme necessário
                total_memory_usage=total_memory,
                total_cpu_usage=total_cpu,
                active_connections=0  # Implementar conforme necessário
            )
            
            # Armazena histórico
            self.metrics_history.append(metrics)
            
            # Limpa histórico antigo (7 dias)
            cutoff_time = timestamp - (7 * 24 * 60 * 60)
            self.metrics_history = [
                m for m in self.metrics_history 
                if m.timestamp > cutoff_time
            ]
            
            logger.debug(f"📊 [SOVEREIGN] Métricas coletadas: {healthy_count}/{total_services} serviços saudáveis")
            return metrics
            
        except Exception as e:
            logger.error(f"❌ [SOVEREIGN] Erro ao coletar métricas: {e}")
            return SystemMetrics(
                timestamp=time.time(),
                total_services=0,
                healthy_services=0,
                unhealthy_services=0,
                error_rate=100.0,
                avg_response_time=0.0,
                total_memory_usage=0.0,
                total_cpu_usage=0.0,
                active_connections=0
            )
    
    def log_security_event(self, service: str, event_type: str, severity: str, 
                          message: str, details: Dict[str, Any] = None):
        """
        Registra evento de segurança
        
        Args:
            service: Serviço relacionado
            event_type: Tipo de evento
            severity: Severidade
            message: Mensagem do evento
            details: Detalhes adicionais
        """
        try:
            event = SecurityEvent(
                timestamp=time.time(),
                service=service,
                event_type=event_type,
                severity=severity,
                message=message,
                details=details or {}
            )
            
            self.security_events.append(event)
            
            # Limita histórico de eventos (1000 eventos)
            if len(self.security_events) > 1000:
                self.security_events = self.security_events[-1000:]
            
            # Loga evento
            logger.warning(f"🔒 [SECURITY] {severity}: {service} - {message}")
            
        except Exception as e:
            logger.error(f"❌ [SOVEREIGN] Erro ao registrar evento de segurança: {e}")
    
    async def start_monitoring(self):
        """Inicia monitoramento contínuo do sistema"""
        try:
            self.running = True
            
            # Tarefa de monitoramento
            self.monitor_task = asyncio.create_task(self._monitoring_loop())
            
            logger.info("📊 [SOVEREIGN] Monitoramento iniciado")
            
        except Exception as e:
            logger.error(f"❌ [SOVEREIGN] Erro ao iniciar monitoramento: {e}")
    
    async def _monitoring_loop(self):
        """Loop principal de monitoramento"""
        while self.running:
            try:
                # Verifica saúde do sistema
                system_health = await self.get_system_health()
                
                # Coleta métricas
                metrics = await self.collect_system_metrics()
                
                # Verifica alertas
                await self._check_alerts(metrics)
                
                # Verifica serviços essenciais
                await self._check_essential_services()
                
                # Aguarda próximo ciclo
                await asyncio.sleep(60)  # Monitora a cada minuto
                
            except Exception as e:
                logger.error(f"❌ [SOVEREIGN] Erro no loop de monitoramento: {e}")
                await asyncio.sleep(10)  # Espera em caso de erro
    
    async def _check_alerts(self, metrics: SystemMetrics):
        """Verifica e dispara alertas"""
        try:
            thresholds = self.config["monitoring"]["alert_thresholds"]
            
            # Verifica CPU usage
            if metrics.total_cpu_usage > thresholds["cpu_usage"]:
                self.log_security_event(
                    "system", 
                    "high_cpu_usage", 
                    "WARNING", 
                    f"CPU usage: {metrics.total_cpu_usage:.1f}%"
                )
            
            # Verifica memory usage
            if metrics.total_memory_usage > thresholds["memory_usage"]:
                self.log_security_event(
                    "system",
                    "high_memory_usage", 
                    "WARNING", 
                    f"Memory usage: {metrics.total_memory_usage:.1f}%"
                )
            
            # Verifica error rate
            if metrics.error_rate > thresholds["error_rate"]:
                self.log_security_event(
                    "system",
                    "high_error_rate", 
                    "CRITICAL", 
                    f"Error rate: {metrics.error_rate:.1f}%"
                )
                
        except Exception as e:
            logger.error(f"❌ [SOVEREIGN] Erro ao verificar alertas: {e}")
    
    async def _check_essential_services(self):
        """Verifica serviços essenciais"""
        try:
            for service_name in self.essential_services:
                if service_name in self.services:
                    service_info = self.services[service_name]
                    
                    if service_info.status != ServiceStatus.RUNNING:
                        logger.warning(f"🚨 [SOVEREIGN] Serviço essencial parado: {service_name}")
                        self.log_security_event(
                            service_name,
                            "service_down",
                            "CRITICAL",
                            f"Essential service stopped: {service_name}"
                        )
                        
                        # Tenta reiniciar
                        await self.restart_service(service_name)
                        
        except Exception as e:
            logger.error(f"❌ [SOVEREIGN] Erro ao verificar serviços essenciais: {e}")
    
    async def shutdown(self):
        """Desliga o serviço soberano de forma segura"""
        try:
            logger.info("🛑 [SOVEREIGN] Iniciando desligamento seguro")
            
            self.running = False
            
            # Para tarefa de monitoramento
            if self.monitor_task and not self.monitor_task.done():
                self.monitor_task.cancel()
            
            # Para todos os serviços
            for service_name in list(self.services.keys()):
                await self.stop_service(service_name)
            
            # Limpa recursos
            if self.executor:
                self.executor.shutdown(wait=True)
            
            logger.info("🏁 [SOVEREIGN] Desligamento concluído")
            
        except Exception as e:
            logger.error(f"❌ [SOVEREIGN] Erro no desligamento: {e}")
    
    def get_system_status(self) -> Dict[str, Any]:
        """Obtém status geral do sistema"""
        try:
            with self.lock:
                return {
                    "running": self.running,
                    "services": {
                        name: {
                            "status": service_info.status.value,
                            "health": service_info.health.value,
                            "last_check": service_info.last_check,
                            "error_count": service_info.error_count,
                            "restart_count": service_info.restart_count
                        }
                        for name, service_info in self.services.items()
                    },
                    "total_services": len(self.services),
                    "essential_services": {
                        name: service_info.status.value
                        for name, service_info in self.services.items()
                        if name in self.essential_services
                    },
                    "config": self.config
                }
                
        except Exception as e:
            logger.error(f"❌ [SOVEREIGN] Erro ao obter status: {e}")
            return {"error": str(e)}
    
    def get_security_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Obtém eventos de segurança"""
        try:
            events = self.security_events[-limit:]
            
            return [
                {
                    "timestamp": event.timestamp,
                    "service": event.service,
                    "event_type": event.event_type,
                    "severity": event.severity,
                    "message": event.message,
                    "details": event.details
                }
                for event in events
            ]
            
        except Exception as e:
            logger.error(f"❌ [SOVEREIGN] Erro ao obter eventos de segurança: {e}")
            return []

# Instância global do Sovereign Service
sovereign_service = SovereignService()