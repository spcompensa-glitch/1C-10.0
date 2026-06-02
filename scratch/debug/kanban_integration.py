#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integração do Kanban Hermes com Backend Services
================================================

Script para monitorar e integrar o Kanban Hermes com os serviços backend,
fornecendo atualizações em tempo real e status do sistema.

Author: QA Team
Version: 1.0
"""

import asyncio
import json
import logging
import os
import time
from typing import Dict, Any, List
import aiohttp

# Configura logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("KanbanIntegration")

class KanbanIntegration:
    """Integração entre Kanban Hermes e Backend Services"""
    
    def __init__(self):
        self.railway_url = "https://1crypten-hermes-agent-production.up.railway.app"
        self.session = None
        self.last_status = {}
        self.is_connected = False
        
    async def initialize(self):
        """Inicializa a integração"""
        self.session = aiohttp.ClientSession()
        logger.info("🔗 Kanban Integration Inicializada")
        
    async def check_railway_connection(self) -> Dict[str, Any]:
        """Verifica conexão com Railway"""
        try:
            async with self.session.get(f"{self.railway_url}/health", timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "connected": True,
                        "status": "ok",
                        "response": data
                    }
                else:
                    return {
                        "connected": False,
                        "status": f"HTTP {response.status}",
                        "error": "Não OK"
                    }
        except Exception as e:
            return {
                "connected": False,
                "status": "error",
                "error": str(e)
            }
    
    async def get_hermes_status(self) -> Dict[str, Any]:
        """Obtém status do Hermes Agent"""
        try:
            async with self.session.get(f"{self.railway_url}/status", timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "available": True,
                        "data": data
                    }
                else:
                    return {
                        "available": False,
                        "error": f"HTTP {response.status}"
                    }
        except Exception as e:
            return {
                "available": False,
                "error": str(e)
            }
    
    async def get_kanban_data(self) -> Dict[str, Any]:
        """Obtém dados do Kanban"""
        try:
            async with self.session.get(f"{self.railway_url}/kanban", timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "available": True,
                        "data": data
                    }
                else:
                    return {
                        "available": False,
                        "error": f"HTTP {response.status}"
                    }
        except Exception as e:
            return {
                "available": False,
                "error": str(e)
            }
    
    async def check_backend_services(self) -> Dict[str, Any]:
        """Verifica serviços backend"""
        try:
            # Verificar WebSocket
            from backend.services.websocket_service import websocket_service
            
            backend_status = {
                "websocket": {
                    "active_connections": len(websocket_service.active_connections),
                    "slots_available": len(websocket_service._last_slots_snapshot),
                    "radar_available": bool(websocket_service._last_radar_snapshot)
                }
            }
            
            # Verificar Telegram
            from backend.services.telegram_service import telegram_service
            backend_status["telegram"] = {
                "is_active": telegram_service.is_active,
                "configured": bool(os.getenv("TELEGRAM_BOT_TOKEN"))
            }
            
            # Verificar Hermes Broker
            from backend.services.hermes_broker import hermes_broker
            backend_status["hermes_broker"] = {
                "mqtt_available": hermes_broker._check_mqtt_availability(),
                "grpc_ready": hermes_broker.grpc_server is not None
            }
            
            return {
                "available": True,
                "data": backend_status
            }
            
        except Exception as e:
            return {
                "available": False,
                "error": str(e)
            }
    
    async def get_system_overview(self) -> Dict[str, Any]:
        """Obtém visão geral do sistema"""
        overview = {
            "timestamp": time.time(),
            "railway": await self.check_railway_connection(),
            "hermes": await self.get_hermes_status(),
            "backend": await self.check_backend_services(),
            "kanban": await self.get_kanban_data()
        }
        
        # Determinar status geral
        total_services = 4
        healthy_services = sum(1 for service in [overview["railway"], overview["hermes"], overview["backend"], overview["kanban"]] if service.get("available", False))
        
        overview["overall_status"] = {
            "health_percentage": (healthy_services / total_services) * 100,
            "healthy_services": healthy_services,
            "total_services": total_services,
            "status": "healthy" if healthy_services >= 3 else "degraded"
        }
        
        return overview
    
    async def generate_integration_report(self) -> str:
        """Gera relatório de integração"""
        overview = await self.get_system_overview()
        
        # Gerar HTML report
        html_report = f"""
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="utf-8">
            <title>Relatório de Integração Hermes</title>
            <style>
                body {{ font-family: monospace; background: #000; color: #06b6d4; padding: 20px; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .status-box {{ border: 1px solid #06b6d4; padding: 15px; margin: 10px 0; border-radius: 8px; }}
                .healthy {{ border-color: #10b981; background: rgba(16, 185, 129, 0.1); }}
                .degraded {{ border-color: #f59e0b; background: rgba(245, 158, 11, 0.1); }}
                .critical {{ border-color: #ef4444; background: rgba(239, 68, 68, 0.1); }}
                .metric {{ margin: 5px 0; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🤖 Relatório de Integração Hermes</h1>
                <p>Gerado em: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div class="status-box {'healthy' if overview['overall_status']['status'] == 'healthy' else 'degraded'}">
                <h2>📊 Visão Geral</h2>
                <div class="metric">Saúde do Sistema: {overview['overall_status']['health_percentage']:.1f}%</div>
                <div class="metric">Serviços Saudáveis: {overview['overall_status']['healthy_services']}/{overview['overall_status']['total_services']}</div>
                <div class="metric">Status: {overview['overall_status']['status'].upper()}</div>
            </div>
            
            <div class="status-box">
                <h2>🚂 Railway</h2>
                <div class="metric">Conectado: {'✅' if overview['railway']['connected'] else '❌'}</div>
                <div class="metric">Status: {overview['railway'].get('status', 'N/A')}</div>
            </div>
            
            <div class="status-box">
                <h2>🤖 Hermes Agent</h2>
                <div class="metric">Disponível: {'✅' if overview['hermes']['available'] else '❌'}</div>
                <div class="metric">Status: {overview['hermes'].get('error', 'OK')}</div>
            </div>
            
            <div class="status-box">
                <h2>🔌 Backend Services</h2>
                <div class="metric">WebSocket: {overview['backend']['data']['websocket']['active_connections']} conexões</div>
                <div class="metric">Telegram: {'✅' if overview['backend']['data']['telegram']['is_active'] else '⚠️'}</div>
                <div class="metric">Hermes Broker: {'✅' if overview['backend']['data']['hermes_broker']['mqtt_available'] else '❌'}</div>
            </div>
            
            <div class="status-box">
                <h2>📊 Kanban</h2>
                <div class="metric">Disponível: {'✅' if overview['kanban']['available'] else '❌'}</div>
                <div class="metric">Status: {overview['kanban'].get('error', 'OK')}</div>
            </div>
        </body>
        </html>
        """
        
        # Salvar relatório
        report_path = os.path.join(os.path.dirname(__file__), 'kanban_integration_report.html')
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_report)
            
        logger.info(f"📋 Relatório salvo em: {report_path}")
        return report_path
    
    async def cleanup(self):
        """Limpeza da integração"""
        if self.session:
            await self.session.close()
        logger.info("🔌 Kanban Integration Desconectada")

async def main():
    """Função principal"""
    logger.info("🚀 Iniciando integração Kanban Hermes...")
    
    integration = KanbanIntegration()
    await integration.initialize()
    
    try:
        # Gerar relatório de integração
        report_path = await integration.generate_integration_report()
        logger.info(f"✅ Relatório de integração gerado: {report_path}")
        
        # Monitorar continuamente (por 1 minuto)
        for i in range(6):
            overview = await integration.get_system_overview()
            logger.info(f"📊 Ciclo {i+1}: {overview['overall_status']['health_percentage']:.1f}% saúde")
            await asyncio.sleep(10)
            
    except Exception as e:
        logger.error(f"❌ Erro na integração: {e}")
    finally:
        await integration.cleanup()

if __name__ == "__main__":
    asyncio.run(main())