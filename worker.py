#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Worker Process - Railway Deployment
===================================

Worker process para Railway deployment do sistema Hermes Guardian,
executa serviços em segundo plano.

Author: DevOps Team
Version: 1.0
"""

import os
import sys
import time
import logging
import asyncio
from datetime import datetime

# Adicionar backend ao path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

# Importar serviços
from backend.services.secrets import secrets_manager
from backend.services.websocket_service import websocket_service
from backend.services.telegram_service import telegram_service
from backend.services.hermes_broker import hermes_broker
from backend.services.portfolio_guardian import portfolio_guardian
from backend.services.sentinel_auditor import sentinel_auditor

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("HermesWorker")

class HermesWorker:
    """Worker para Railway"""
    
    def __init__(self):
        self.running = False
        self.start_time = time.time()
        
    async def start_services(self):
        """Iniciar todos os serviços"""
        logger.info("🚀 Iniciando serviços Hermes Worker...")
        
        try:
            # Iniciar WebSocket Service
            logger.info("🔌 Iniciando WebSocket Service...")
            await websocket_service.start()
            
            # Iniciar Telegram Service
            if telegram_service.is_active:
                logger.info("📱 Telegram Service ativo")
            
            # Iniciar Hermes Broker
            logger.info("🛰️ Iniciando Hermes Broker...")
            await hermes_broker.start_mqtt()
            
            # Iniciar Portfolio Guardian
            logger.info("🛡️ Iniciando Portfolio Guardian...")
            portfolio_guardian.start()
            
            # Iniciar Sentinel Auditor
            logger.info("🔍 Iniciando Sentinel Auditor...")
            
            logger.info("✅ Todos os serviços iniciados com sucesso!")
            
        except Exception as e:
            logger.error(f"❌ Erro ao iniciar serviços: {e}")
            raise
    
    async def monitor_services(self):
        """Monitorar serviços em tempo real"""
        logger.info("📊 Iniciando monitoramento de serviços...")
        
        while self.running:
            try:
                # Verificar status dos serviços
                services_status = {
                    "timestamp": time.time(),
                    "uptime": time.time() - self.start_time,
                    "services": {}
                }
                
                # WebSocket Service
                services_status["services"]["websocket"] = {
                    "healthy": len(websocket_service.active_connections) > 0,
                    "connections": len(websocket_service.active_connections),
                    "slots_available": len(websocket_service._last_slots_snapshot),
                    "radar_available": bool(websocket_service._last_radar_snapshot)
                }
                
                # Telegram Service
                services_status["services"]["telegram"] = {
                    "healthy": telegram_service.is_active,
                    "configured": bool(os.getenv("TELEGRAM_BOT_TOKEN"))
                }
                
                # Hermes Broker
                services_status["services"]["hermes_broker"] = {
                    "healthy": hermes_broker._check_mqtt_availability(),
                    "grpc_ready": hermes_broker.grpc_server is not None
                }
                
                # Portfolio Guardian
                services_status["services"]["portfolio_guardian"] = {
                    "healthy": True,
                    "state": portfolio_guardian.state,
                    "max_roi_registered": portfolio_guardian.max_roi_registered,
                    "current_roi": portfolio_guardian.current_roi
                }
                
                # Sentinel Auditor
                services_status["services"]["sentinel_auditor"] = {
                    "healthy": True,
                    "auto_healing_active": sentinel_auditor.auto_healing_active,
                    "last_check": sentinel_auditor.last_check_time
                }
                
                # Log status
                logger.info(f"📊 Monitoramento: {len(services_status['services'])} serviços saudáveis")
                
                # Esperar próximo ciclo
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"❌ Erro no monitoramento: {e}")
                await asyncio.sleep(5)
    
    async def run(self):
        """Executar worker"""
        logger.info("🚀 Hermes Worker iniciado...")
        
        try:
            # Iniciar serviços
            await self.start_services()
            
            # Iniciar monitoramento
            self.running = True
            await self.monitor_services()
            
        except KeyboardInterrupt:
            logger.info("🛑 Worker interrompido pelo usuário...")
        except Exception as e:
            logger.error(f"❌ Erro no worker: {e}")
            raise
        finally:
            self.running = False
            logger.info("🏁 Worker finalizado")

async def main():
    """Função principal"""
    logger.info("🚀 Iniciando Hermes Worker Railway...")
    
    worker = HermesWorker()
    
    try:
        await worker.run()
    except Exception as e:
        logger.error(f"❌ Erro na execução: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Configurar Railway
    port = int(os.getenv("PORT", 8081))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"🚀 Worker iniciado na porta {port}")
    
    # Executar worker
    asyncio.run(main())