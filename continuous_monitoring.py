#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitoramento Contínuo Hermes
===============================

Sistema de monitoramento contínuo do Hermes integrado com testes de regressão,
fornecendo alertas em tempo real e validação contínua.

Author: QA Team
Version: 1.0
"""

import asyncio
import json
import logging
import os
import sys
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

# Adiciona backend ao path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

# Configura logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ContinuousMonitoring")

class ContinuousMonitor:
    """Monitoramento contínuo do sistema Hermes"""
    
    def __init__(self):
        self.monitoring_active = False
        self.session = None
        self.railway_url = "https://1crypten-hermes-agent-production.up.railway.app"
        self.check_interval = 30  # segundos
        self.alert_threshold = 3  # falhas consecutivas
        self.failure_counts = {}
        self.health_history = []
        self.max_history = 100
        
    async def initialize(self):
        """Inicializa o monitoramento"""
        self.session = aiohttp.ClientSession()
        self.monitoring_active = True
        logger.info("🔍 Monitoramento Contínuo Iniciado")
        
    async def start_monitoring(self):
        """Inicia o ciclo de monitoramento"""
        logger.info("🚀 Iniciando ciclo de monitoramento...")
        
        while self.monitoring_active:
            try:
                # Executar verificação completa
                health_report = await self.run_health_check()
                
                # Registrar histórico
                self.health_history.append({
                    "timestamp": time.time(),
                    "health": health_report
                })
                
                # Manter histórico limitado
                if len(self.health_history) > self.max_history:
                    self.health_history.pop(0)
                
                # Verificar alertas
                await self.check_alerts(health_report)
                
                # Log status
                logger.info(f"📊 Ciclo concluído - Saúde: {health_report['overall_status']}")
                
                # Aguardar próximo ciclo
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"❌ Erro no ciclo de monitoramento: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def run_health_check(self) -> Dict[str, Any]:
        """Executa verificação completa de saúde"""
        health_report = {
            "timestamp": time.time(),
            "overall_status": "healthy",
            "services": {},
            "regression_tests": {},
            "railway": {},
            "recommendations": []
        }
        
        # Verificar serviços backend
        services_health = await self.check_services()
        health_report["services"] = services_health
        
        # Verificar Railway
        railway_health = await self.check_railway()
        health_report["railway"] = railway_health
        
        # Verificar testes de regressão
        regression_health = await self.check_regression_tests()
        health_report["regression_tests"] = regression_health
        
        # Determinar status geral
        all_services_healthy = all(service.get("healthy", False) for service in services_health.values())
        railway_healthy = railway_health.get("connected", False)
        regression_healthy = regression_health.get("success_rate", 0) >= 0.8
        
        if all_services_healthy and railway_healthy and regression_healthy:
            health_report["overall_status"] = "healthy"
        else:
            health_report["overall_status"] = "degraded"
        
        # Gerar recomendações
        health_report["recommendations"] = self.generate_health_recommendations(
            services_health, railway_health, regression_health
        )
        
        return health_report
    
    async def check_services(self) -> Dict[str, Any]:
        """Verifica serviços backend"""
        services = {}
        
        try:
            # Secrets Manager
            from backend.services.secrets import secrets_manager
            services["secrets"] = {
                "healthy": True,
                "environment": secrets_manager.environment.value,
                "production_ready": secrets_manager.validate_production_readiness()
            }
            
            # WebSocket
            from backend.services.websocket_service import websocket_service
            services["websocket"] = {
                "healthy": True,
                "connections": len(websocket_service.active_connections)
            }
            
            # Telegram
            from backend.services.telegram_service import telegram_service
            services["telegram"] = {
                "healthy": telegram_service.is_active,
                "configured": bool(os.getenv("TELEGRAM_BOT_TOKEN"))
            }
            
            # Hermes Broker
            from backend.services.hermes_broker import hermes_broker
            services["hermes_broker"] = {
                "healthy": True,
                "mqtt_available": hermes_broker._check_mqtt_availability()
            }
            
            # Portfolio Guardian
            from backend.services.portfolio_guardian import portfolio_guardian
            services["guardian"] = {
                "healthy": True,
                "state": portfolio_guardian.state,
                "max_roi": portfolio_guardian.max_roi_registered
            }
            
            # Sentinel Auditor
            from backend.services.sentinel_auditor import sentinel_auditor
            services["auditor"] = {
                "healthy": True,
                "auto_healing": sentinel_auditor.auto_healing_active
            }
            
        except Exception as e:
            logger.error(f"❌ Erro ao verificar serviços: {e}")
            services["error"] = str(e)
        
        return services
    
    async def check_railway(self) -> Dict[str, Any]:
        """Verifica Railway"""
        try:
            async with self.session.get(f"{self.railway_url}/health", timeout=10) as response:
                return {
                    "connected": response.status == 200,
                    "status_code": response.status,
                    "response_time": 0  # Simplificado para este exemplo
                }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e)
            }
    
    async def check_regression_tests(self) -> Dict[str, Any]:
        """Verifica testes de regressão"""
        try:
            # Carregar resultados FASE 7
            phase7_path = os.path.join(os.path.dirname(__file__), 'FASE7_FINAL_REPORT_FIXED.json')
            if os.path.exists(phase7_path):
                with open(phase7_path, 'r', encoding='utf-8') as f:
                    phase7_data = json.load(f)
                
                return {
                    "phase7_available": True,
                    "phase7_success": phase7_data.get("overall_status") == "success",
                    "total_tests": phase7_data.get("total_tests", 0),
                    "success_rate": 1.0 if phase7_data.get("overall_status") == "success" else 0.0
                }
            else:
                return {
                    "phase7_available": False,
                    "success_rate": 0.5  # Valor padrão
                }
        except Exception as e:
            logger.error(f"❌ Erro ao verificar testes: {e}")
            return {"success_rate": 0.0}
    
    async def check_alerts(self, health_report: Dict[str, Any]):
        """Verifica e gera alertas"""
        service_name = "overall"
        
        # Atualizar contador de falhas
        current_status = health_report["overall_status"]
        if current_status != "healthy":
            self.failure_counts[service_name] = self.failure_counts.get(service_name, 0) + 1
        else:
            self.failure_counts[service_name] = 0
        
        # Verificar threshold de alerta
        if self.failure_counts[service_name] >= self.alert_threshold:
            await self.send_alert(service_name, health_report)
    
    async def send_alert(self, service_name: str, health_report: Dict[str, Any]):
        """Envia alerta"""
        alert_message = f"🚨 ALERTA: Serviço {service_name} com falhas consecutivas"
        alert_details = f"Status: {health_report['overall_status']}"
        
        logger.warning(f"🚨 {alert_message} - {alert_details}")
        
        # Enviar alerta para Telegram (se configurado)
        try:
            from backend.services.telegram_service import telegram_service
            if telegram_service.is_active:
                await telegram_service.send_alert(alert_message, alert_details)
        except Exception as e:
            logger.error(f"❌ Falha ao enviar alerta para Telegram: {e}")
    
    def generate_health_recommendations(self, services: Dict, railway: Dict, regression: Dict) -> List[str]:
        """Gera recomendações baseadas na saúde do sistema"""
        recommendations = []
        
        # Verificar serviços
        unhealthy_services = [name for name, service in services.items() if not service.get("healthy", True)]
        if unhealthy_services:
            recommendations.append(f"🔧 CORRIGIR SERVIÇOS: {', '.join(unhealthy_services)}")
        
        # Verificar Railway
        if not railway.get("connected", False):
            recommendations.append("🚂 VERIFICAR CONEXÃO RAILWAY")
        
        # Verificar testes de regressão
        if regression.get("success_rate", 0) < 0.8:
            recommendations.append("🧪 MELHORAR COBERTURA DE TESTES")
        
        # Recomendações gerais
        if len(recommendations) == 0:
            recommendations.append("✅ SISTEMA SAUDÁVEL - MANTER MONITORAMENTO")
        
        return recommendations
    
    async def get_health_trend(self) -> Dict[str, Any]:
        """Obtém tendência de saúde"""
        if len(self.health_history) < 2:
            return {"trend": "unknown", "period": "insufficient_data"}
        
        recent_health = [h["health"]["overall_status"] for h in self.health_history[-10:]]
        healthy_count = recent_health.count("healthy")
        
        if healthy_count >= 8:
            trend = "improving"
        elif healthy_count <= 2:
            trend = "declining"
        else:
            trend = "stable"
        
        return {
            "trend": trend,
            "period": f"{len(recent_health)} cycles",
            "healthy_percentage": (healthy_count / len(recent_health)) * 100
        }
    
    async def stop_monitoring(self):
        """Para o monitoramento"""
        self.monitoring_active = False
        if self.session:
            await self.session.close()
        logger.info("🛑 Monitoramento Contínuo Parado")
    
    async def generate_monitoring_report(self) -> str:
        """Gera relatório de monitoramento"""
        trend = await self.get_health_trend()
        
        report = {
            "timestamp": time.time(),
            "monitoring_duration": len(self.health_history) * self.check_interval,
            "total_cycles": len(self.health_history),
            "current_trend": trend,
            "health_history": self.health_history[-10:],  # Últimos 10 ciclos
            "recommendations": self.generate_health_recommendations({}, {}, {}),
            "alert_threshold": self.alert_threshold,
            "check_interval": self.check_interval
        }
        
        # Salvar relatório
        report_path = os.path.join(os.path.dirname(__file__), 'continuous_monitoring_report.json')
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"📋 Relatório de monitoramento salvo em: {report_path}")
        return report_path

async def main():
    """Função principal"""
    logger.info("🚀 Iniciando Monitoramento Contínuo Hermes...")
    
    monitor = ContinuousMonitor()
    await monitor.initialize()
    
    try:
        # Iniciar monitoramento em segundo plano
        monitoring_task = asyncio.create_task(monitor.start_monitoring())
        
        # Rodar por 5 minutos (10 ciclos de 30 segundos)
        await asyncio.sleep(300)
        
        # Parar monitoramento
        await monitor.stop_monitoring()
        
        # Gerar relatório final
        report_path = await monitor.generate_monitoring_report()
        logger.info(f"✅ Monitoramento concluído. Relatório: {report_path}")
        
    except KeyboardInterrupt:
        logger.info("⏹️ Monitoramento interrompido pelo usuário")
        await monitor.stop_monitoring()
    except Exception as e:
        logger.error(f"❌ Erro no monitoramento: {e}")
        await monitor.stop_monitoring()

if __name__ == "__main__":
    asyncio.run(main())