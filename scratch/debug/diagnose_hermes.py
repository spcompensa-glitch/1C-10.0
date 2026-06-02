#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnóstico do Sistema Hermes Agent
===================================

Script para identificar problemas no sistema Hermes e verificar
a integridade entre os componentes principais.

Author: QA Team
Version: 1.0
"""

import asyncio
import json
import logging
import os
import sys
import time
from typing import Dict, Any, List

# Adiciona backend ao path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

# Configura logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("HermesDiagnose")

class HermesDiagnoser:
    """Diagnóstico do sistema Hermes"""
    
    def __init__(self):
        self.results = {}
        self.issues = []
        self.recommendations = []
        
    async def diagnose_all(self):
        """Executa todos os diagnósticos"""
        logger.info("🔍 Iniciando diagnóstico completo do sistema Hermes...")
        
        # 1. Verificar serviços backend
        await self.diagnose_backend_services()
        
        # 2. Verificar integração WebSocket
        await self.diagnose_websocket_integration()
        
        # 3. Verificar integração Telegram
        await self.diagnose_telegram_integration()
        
        # 4. Verificar Hermes Agent
        await self.diagnose_hermes_agent()
        
        # 5. Verificar Kanban UI
        await self.diagnose_kanban_ui()
        
        # 6. Verificar Railway
        await self.diagnose_railway_connection()
        
        # 7. Gerar relatório
        self.generate_report()
        
    async def diagnose_backend_services(self):
        """Diagnóstico dos serviços backend"""
        logger.info("📋 Verificando serviços backend...")
        
        try:
            # Verificar secrets manager
            from backend.services.secrets import secrets_manager
            secrets_status = {
                "environment": secrets_manager.environment.value,
                "production_ready": secrets_manager.validate_production_readiness(),
                "available_secrets": len([k for k in [
                    os.getenv("JWT_SECRET_KEY"), os.getenv("OKX_API_KEY_MASTER"),
                    os.getenv("OKX_API_SECRET_MASTER"), os.getenv("OKX_PASSPHRASE_MASTER"),
                    os.getenv("DATABASE_URL"), os.getenv("ADMIN_API_KEY")
                ] if k is not None])
            }
            self.results["secrets_manager"] = secrets_status
            
            # Verificar se serviços podem ser importados
            services_to_check = [
                "telegram_service",
                "hermes_broker", 
                "websocket_service",
                "portfolio_guardian",
                "sentinel_auditor"
            ]
            
            for service_name in services_to_check:
                try:
                    module = __import__(f"backend.services.{service_name}", fromlist=[service_name])
                    service = getattr(module, f"{service_name.split('_')[0]}_service" if service_name.endswith("_service") else service_name)
                    self.results[f"{service_name}_status"] = "OK"
                except Exception as e:
                    self.results[f"{service_name}_status"] = f"ERROR: {str(e)}"
                    self.issues.append(f"❌ Falha ao carregar {service_name}: {str(e)}")
                    
        except Exception as e:
            self.issues.append(f"❌ Erro crítico nos serviços backend: {str(e)}")
            
    async def diagnose_websocket_integration(self):
        """Diagnóstico da integração WebSocket"""
        logger.info("🔌 Verificando integração WebSocket...")
        
        try:
            from backend.services.websocket_service import websocket_service
            
            # Verificar estado do WebSocket
            ws_status = {
                "active_connections": len(websocket_service.active_connections),
                "last_slots_snapshot": len(websocket_service._last_slots_snapshot),
                "last_radar_snapshot": bool(websocket_service._last_radar_snapshot)
            }
            self.results["websocket_status"] = ws_status
            
            # Testar emissão de mensagem
            test_message = {
                "type": "test",
                "data": {"message": "Diagnóstico Hermes", "timestamp": time.time()},
                "timestamp": time.time()
            }
            
            # Simular envio (não realmente enviar para não causar problemas)
            logger.info("✅ WebSocket service está ativo e configurado")
            
        except Exception as e:
            self.results["websocket_status"] = f"ERROR: {str(e)}"
            self.issues.append(f"❌ Erro na integração WebSocket: {str(e)}")
            
    async def diagnose_telegram_integration(self):
        """Diagnóstico da integração Telegram"""
        logger.info("📱 Verificando integração Telegram...")
        
        try:
            from backend.services.telegram_service import telegram_service
            
            tg_status = {
                "is_active": telegram_service.is_active,
                "bot_token_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
                "chat_id_configured": bool(os.getenv("TELEGRAM_CHAT_ID"))
            }
            self.results["telegram_status"] = tg_status
            
            if telegram_service.is_active:
                logger.info("✅ Telegram service está ativo")
            else:
                self.issues.append("⚠️ Telegram service inativo - configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID")
                
        except Exception as e:
            self.results["telegram_status"] = f"ERROR: {str(e)}"
            self.issues.append(f"❌ Erro na integração Telegram: {str(e)}")
            
    async def diagnose_hermes_agent(self):
        """Diagnóstico do Hermes Agent"""
        logger.info("🤖 Verificando Hermes Agent...")
        
        try:
            # Verificar se o diretório do hermes-agent existe
            hermes_path = os.path.join(os.path.dirname(__file__), 'hermes-agent')
            hermes_exists = os.path.exists(hermes_path)
            
            hermes_status = {
                "directory_exists": hermes_exists,
                "bootstrap_exists": os.path.exists(os.path.join(hermes_path, 'hermes_bootstrap.py')),
                "mcp_server_exists": os.path.exists(os.path.join(hermes_path, 'agent', 'transports', 'hermes_tools_mcp_server.py'))
            }
            self.results["hermes_agent_status"] = hermes_status
            
            if hermes_exists:
                logger.info("✅ Diretório do Hermes Agent encontrado")
                # Verificar se pode ser executado
                if os.path.exists(os.path.join(hermes_path, 'hermes')):
                    logger.info("✅ Executável do Hermes encontrado")
                else:
                    self.issues.append("⚠️ Executável do Hermes não encontrado")
            else:
                self.issues.append("❌ Diretório do Hermes Agent não encontrado")
                
        except Exception as e:
            self.results["hermes_agent_status"] = f"ERROR: {str(e)}"
            self.issues.append(f"❌ Erro no diagnóstico do Hermes Agent: {str(e)}")
            
    async def diagnose_kanban_ui(self):
        """Diagnóstico da UI Kanban"""
        logger.info("📊 Verificando UI Kanban...")
        
        try:
            kanban_path = os.path.join(os.path.dirname(__file__), 'frontend', 'kanban-hermes.html')
            kanban_exists = os.path.exists(kanban_path)
            
            kanban_status = {
                "file_exists": kanban_exists,
                "railway_url": "https://1crypten-hermes-agent-production.up.railway.app"
            }
            self.results["kanban_ui_status"] = kanban_status
            
            if kanban_exists:
                logger.info("✅ Arquivo HTML do Kanban encontrado")
                
                # Verificar se a URL do Railway está configurada
                railway_url = os.getenv("RAILWAY_URL") or "https://1crypten-hermes-agent-production.up.railway.app"
                if railway_url:
                    logger.info(f"✅ URL do Railway configurada: {railway_url}")
                else:
                    self.issues.append("⚠️ URL do Railway não configurada")
            else:
                self.issues.append("❌ Arquivo HTML do Kanban não encontrado")
                
        except Exception as e:
            self.results["kanban_ui_status"] = f"ERROR: {str(e)}"
            self.issues.append(f"❌ Erro no diagnóstico da UI Kanban: {str(e)}")
            
    async def diagnose_railway_connection(self):
        """Diagnóstico da conexão Railway"""
        logger.info("🚂 Verificando conexão Railway...")
        
        try:
            import aiohttp
            
            railway_token = os.getenv("RAILWAY_TOKEN")
            railway_url = os.getenv("RAILWAY_URL") or "https://1crypten-hermes-agent-production.up.railway.app"
            
            railway_status = {
                "token_configured": bool(railway_token),
                "url_configured": bool(railway_url),
                "connection_test": "PENDING"
            }
            
            # Testar conexão com Railway
            try:
                async with aiohttp.ClientSession(timeout=10) as session:
                    async with session.get(f"{railway_url}/health") as response:
                        if response.status == 200:
                            railway_status["connection_test"] = "OK"
                            logger.info("✅ Conexão com Railway bem-sucedida")
                        else:
                            railway_status["connection_test"] = f"ERROR: HTTP {response.status}"
                            self.issues.append(f"⚠️ Railway respondeu com status {response.status}")
            except Exception as e:
                railway_status["connection_test"] = f"ERROR: {str(e)}"
                self.issues.append(f"❌ Falha ao conectar com Railway: {str(e)}")
                
            self.results["railway_status"] = railway_status
            
        except Exception as e:
            self.results["railway_status"] = f"ERROR: {str(e)}"
            self.issues.append(f"❌ Erro no diagnóstico da conexão Railway: {str(e)}")
            
    def generate_report(self):
        """Gera relatório de diagnóstico"""
        logger.info("📄 Gerando relatório de diagnóstico...")
        
        # Contadores
        total_checks = len(self.results)
        failed_checks = len([r for r in self.results.values() if isinstance(r, str) and r.startswith("ERROR")])
        
        # Status geral
        if failed_checks == 0 and len(self.issues) == 0:
            overall_status = "✅ SAUDÁVEL"
        elif failed_checks < total_checks * 0.5:
            overall_status = "⚠️ ATENÇÃO"
        else:
            overall_status = "❌ CRÍTICO"
            
        # Relatório
        report = {
            "timestamp": time.time(),
            "overall_status": overall_status,
            "total_checks": total_checks,
            "failed_checks": failed_checks,
            "issues_count": len(self.issues),
            "results": self.results,
            "issues": self.issues,
            "recommendations": self.generate_recommendations()
        }
        
        # Salvar relatório
        report_path = os.path.join(os.path.dirname(__file__), 'hermes_diagnosis_report.json')
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            
        logger.info(f"📋 Relatório salvo em: {report_path}")
        logger.info(f"📊 Status geral: {overall_status}")
        
        return report
        
    def generate_recommendations(self):
        """Gera recomendações baseadas nos problemas identificados"""
        recommendations = []
        
        # Verificar issues específicas
        if any("❌" in issue for issue in self.issues):
            recommendations.append("🔧 CORRIGIR ERROS CRÍTICOS priorizando serviços fundamentais")
            
        if any("⚠️" in issue for issue in self.issues):
            recommendations.append("🔍 INVESTIGAR ALERTAS que podem indicar problemas futuros")
            
        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            recommendations.append("📅 CONFIGURAR TELEGRAM_BOT_TOKEN para integração completa")
            
        if not os.getenv("RAILWAY_TOKEN"):
            recommendations.append("🚂 CONFIGURAR RAILWAY_TOKEN para deploy automatizado")
            
        if "WebSocket" in str(self.results):
            recommendations.append("🔄 IMPLEMENTAR RECONEXÃO AUTOMÁTICA no WebSocket")
            
        if len(self.issues) == 0:
            recommendations.append("🚀 IMPLEMENTAR ENHANCEMENTS para aumentar autonomia do agente")
            
        return recommendations

async def main():
    """Função principal"""
    logger.info("🚀 Iniciando diagnóstico do sistema Hermes...")
    
    diagnoser = HermesDiagnoser()
    await diagnoser.diagnose_all()
    
    logger.info("✅ Diagnóstico concluído!")
    logger.info(f"📊 Total de issues: {len(diagnoser.issues)}")
    logger.info(f"💡 Recomendações: {len(diagnoser.recommendations)}")

if __name__ == "__main__":
    asyncio.run(main())