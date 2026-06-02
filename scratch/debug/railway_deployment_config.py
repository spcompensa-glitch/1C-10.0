#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuração de Railway Deployment para Hermes-Kanban-Telegram
================================================================

Script completo para configuração e deploy do sistema Hermes-Kanban-Telegram
no Railway, incluindo setup de ambiente, variáveis e configuração de serviços.

Author: DevOps Team
Version: 1.0
"""

import os
import json
import logging
import subprocess
import sys
from typing import Dict, Any, List

# Configura logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RailwayDeployment")

class RailwayDeploymentConfig:
    """Configuração de Railway Deployment"""
    
    def __init__(self):
        self.railway_token = "baab061ec-2bcf-436b-bbb2-1c6b8616046b"
        self.railway_url = "https://1crypten-hermes-agent-production.up.railway.app"
        self.project_name = "1crypten-hermes-guardian"
        self.environment = "production"
        
        # Variáveis de ambiente necessárias
        self.required_env_vars = {
            "RAILWAY_TOKEN": self.railway_token,
            "RAILWAY_URL": self.railway_url,
            "ADMIN_API_KEY": "1crypten-admin-key-2026-production",
            "TELEGRAM_BOT_TOKEN": "8656832302:AAHARDZZe-bltJte6QR-e-KcBiNkNDrvx7I",
            "TELEGRAM_CHAT_ID": "1249100206",
            "JWT_SECRET_KEY": "1crypten-jwt-secret-2026-production",
            "DATABASE_URL": "postgresql://user:password@localhost:5432/1crypten",
            "OKX_API_KEY_MASTER": "okx-api-key-master",
            "OKX_API_SECRET_MASTER": "okx-api-secret-master", 
            "OKX_PASSPHRASE_MASTER": "okx-passphrase-master",
            "OPENROUTER_API_KEY": "openrouter-api-key-production",
            "DEEPSEEK_API_KEY": "deepseek-api-key-production"
        }
        
        # Configuração do serviço Railway
        self.railway_service_config = {
            "service_name": "hermes-guardian",
            "command": "python -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload",
            "env_vars": self.required_env_vars,
            "build_command": "pip install -r requirements.txt",
            "start_command": "python main.py",
            "health_check": "/health",
            "memory_limit": "512MB",
            "cpu_limit": "100%",
            "regions": ["us-east-1", "eu-west-1"]
        }
    
    def validate_environment(self) -> Dict[str, Any]:
        """Valida o ambiente para deployment"""
        logger.info("🔍 Validando ambiente para Railway deployment...")
        
        validation_results = {
            "overall_status": "ready",
            "checks": {},
            "missing_vars": [],
            "warnings": []
        }
        
        # Verificar Railway CLI
        try:
            subprocess.run(["railway", "--version"], capture_output=True, check=True)
            validation_results["checks"]["railway_cli"] = {"status": "ok", "message": "Railway CLI disponível"}
        except (subprocess.CalledProcessError, FileNotFoundError):
            validation_results["checks"]["railway_cli"] = {"status": "error", "message": "Railway CLI não encontrado"}
            validation_results["overall_status"] = "incomplete"
            validation_results["warnings"].append("Instale Railway CLI: npm install -g @railway/cli")
        
        # Verificar Docker
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
            validation_results["checks"]["docker"] = {"status": "ok", "message": "Docker disponível"}
        except (subprocess.CalledProcessError, FileNotFoundError):
            validation_results["checks"]["docker"] = {"status": "warning", "message": "Docker não encontrado - deployment ainda possível"}
            validation_results["warnings"].append("Docker recomendado para builds otimizados")
        
        # Verificar Node.js (para Railway CLI)
        try:
            subprocess.run(["node", "--version"], capture_output=True, check=True)
            validation_results["checks"]["nodejs"] = {"status": "ok", "message": "Node.js disponível"}
        except (subprocess.CalledProcessError, FileNotFoundError):
            validation_results["checks"]["nodejs"] = {"status": "error", "message": "Node.js não encontrado"}
            validation_results["overall_status"] = "incomplete"
            validation_results["warnings"].append("Instale Node.js para Railway CLI")
        
        # Verificar variáveis de ambiente
        missing_vars = []
        for var_name, var_value in self.required_env_vars.items():
            if not var_value or var_value == f"{var_name}_placeholder":
                missing_vars.append(var_name)
        
        if missing_vars:
            validation_results["missing_vars"] = missing_vars
            validation_results["overall_status"] = "incomplete"
            validation_results["warnings"].append(f"Variáveis faltando: {', '.join(missing_vars)}")
        else:
            validation_results["checks"]["env_vars"] = {"status": "ok", "message": "Todas as variáveis configuradas"}
        
        return validation_results
    
    def generate_railway_config(self) -> Dict[str, Any]:
        """Gera configuração completa do Railway"""
        logger.info("🚂 Gerando configuração Railway...")
        
        railway_config = {
            "name": self.project_name,
            "environment": self.environment,
            "services": {
                "hermes-guardian": {
                    "command": self.railway_service_config["command"],
                    "envVars": self.railway_service_config["env_vars"],
                    "buildCommand": self.railway_service_config["build_command"],
                    "startCommand": self.railway_service_config["start_command"],
                    "healthCheck": self.railway_service_config["health_check"],
                    "runtime": "python",
                    "memoryLimit": self.railway_service_config["memory_limit"],
                    "cpuLimit": self.railway_service_config["cpu_limit"]
                }
            },
            "regions": self.railway_service_config["regions"],
            "settings": {
                "autoDeploy": True,
                "healthCheckInterval": 30,
                "healthCheckTimeout": 10,
                "healthCheckRetries": 3
            }
        }
        
        return railway_config
    
    def create_dockerfile(self) -> str:
        """Cria Dockerfile para Railway"""
        dockerfile_content = """# Dockerfile para Railway Deployment
FROM python:3.10-slim

WORKDIR /app

# Copiar requirements primeiro para aproveitar cache
COPY requirements.txt .

# Instalar dependências
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código do aplicativo
COPY . .

# Expor porta
EXPOSE 8080

# Comando de start
CMD ["python", "main.py"]
"""
        return dockerfile_content
    
    def create_railway_json(self) -> str:
        """Cria arquivo railway.json"""
        config = self.generate_railway_config()
        return json.dumps(config, indent=2, ensure_ascii=False)
    
    def create_procfile(self) -> str:
        """Cria Procfile para Railway"""
        return """web: python -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
worker: python worker.py
"""
    
    def setup_deployment_files(self) -> Dict[str, str]:
        """Cria arquivos necessários para deployment"""
        logger.info("📁 Criando arquivos de deployment...")
        
        files_created = {}
        
        # Dockerfile
        dockerfile_content = self.create_dockerfile()
        dockerfile_path = "Dockerfile"
        with open(dockerfile_path, 'w') as f:
            f.write(dockerfile_content)
        files_created[dockerfile_path] = "Dockerfile Railway"
        
        # railway.json
        railway_config = self.create_railway_json()
        railway_json_path = "railway.json"
        with open(railway_json_path, 'w') as f:
            f.write(railway_config)
        files_created[railway_json_path] = "Configuração Railway"
        
        # Procfile
        procfile_content = self.create_procfile()
        procfile_path = "Procfile"
        with open(procfile_path, 'w') as f:
            f.write(procfile_content)
        files_created[procfile_path] = "Procfile Railway"
        
        # .env.production
        env_production_path = ".env.production"
        env_content = "\n".join([f"{k}={v}" for k, v in self.required_env_vars.items()])
        with open(env_production_path, 'w') as f:
            f.write(env_content)
        files_created[env_production_path] = "Variáveis de ambiente de produção"
        
        return files_created
    
    def validate_deployment_readiness(self) -> Dict[str, Any]:
        """Valida se o deployment está pronto"""
        logger.info("🔍 Validando prontidão para deployment...")
        
        # Validar ambiente
        env_validation = self.validate_environment()
        
        # Validar arquivos necessários
        required_files = ["requirements.txt", "main.py", "backend/main.py"]
        missing_files = []
        
        for file_path in required_files:
            if not os.path.exists(file_path):
                missing_files.append(file_path)
        
        readiness = {
            "environment": env_validation,
            "files": {
                "required": required_files,
                "missing": missing_files,
                "present": [f for f in required_files if f not in missing_files]
            },
            "deployment_ready": env_validation["overall_status"] == "ready" and len(missing_files) == 0
        }
        
        if readiness["deployment_ready"]:
            logger.info("✅ Deployment pronto!")
        else:
            logger.warning("⚠️ Issues encontradas:")
            if env_validation["overall_status"] != "ready":
                logger.warning(f"   Ambiente: {env_validation['overall_status']}")
            if missing_files:
                logger.warning(f"   Arquivos faltando: {', '.join(missing_files)}")
        
        return readiness
    
    def generate_deployment_report(self) -> str:
        """Gera relatório de deployment"""
        logger.info("📋 Gerando relatório de deployment...")
        
        # Validar prontidão
        readiness = self.validate_deployment_readiness()
        
        # Gerar relatório
        report = {
            "timestamp": __import__('time').time(),
            "project": self.project_name,
            "environment": self.environment,
            "railway_url": self.railway_url,
            "deployment_readiness": readiness["deployment_ready"],
            "environment_status": readiness["environment"]["overall_status"],
            "files_status": {
                "total_required": len(readiness["files"]["required"]),
                "present": len(readiness["files"]["present"]),
                "missing": len(readiness["files"]["missing"])
            },
            "deployment_steps": [
                "1. Login no Railway: railway login",
                "2. Criar projeto: railway init",
                "3. Adicionar serviço: railway add hermes-guardian",
                "4. Configurar variáveis: railway variables set",
                "5. Deploy: railway up",
                "6. Monitorar: railway logs"
            ],
            "next_actions": [
                "🚀 Executar railway init",
                "🔧 Configurar variáveis ambiente",
                "🚀 Realizar primeiro deploy",
                "📊 Monitorar logs de deployment",
                "🔍 Validar endpoints de saúde"
            ]
        }
        
        # Salvar relatório
        report_path = "railway_deployment_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"📋 Relatório salvo em: {report_path}")
        return report_path
    
    def create_deployment_script(self) -> str:
        """Cria script de deployment automatizado"""
        script_content = """#!/bin/bash
# Script de Deployment Railway Automatizado

echo "🚂 Iniciando deployment do Hermes-Kanban-Telegram no Railway..."

# 1. Login no Railway
echo "🔐 Fazendo login no Railway..."
railway login

# 2. Inicializar projeto (se necessário)
if [ ! -f ".railway" ]; then
    echo "🆕 Inicializando projeto Railway..."
    railway init
fi

# 3. Adicionar serviço
echo "➕ Adicionando serviço hermes-guardian..."
railway add hermes-guardian

# 4. Configurar variáveis de ambiente
echo "🔧 Configurando variáveis ambiente..."
railway variables set RAILWAY_TOKEN=baab061ec-2bcf-436b-bbb2-1c6b8616046b
railway variables set ADMIN_API_KEY=1crypten-admin-key-2026-production
railway variables set TELEGRAM_BOT_TOKEN=8656832302:AAHARDZZe-bltJte6QR-e-KcBiNkNDrvx7I
railway variables set TELEGRAM_CHAT_ID=1249100206
railway variables set JWT_SECRET_KEY=1crypten-jwt-secret-2026-production

# 5. Realizar deployment
echo "🚀 Realizando deployment..."
railway up --detach

# 6. Monitorar logs
echo "📊 Verificando status do deployment..."
sleep 30
railway logs

# 7. Validar saúde
echo "🔍 Validando endpoints de saúde..."
curl -f https://1crypten-hermes-agent-production.up.railway.app/health

echo "✅ Deployment concluído!"
"""
        return script_content

def main():
    """Função principal"""
    logger.info("🚀 Iniciando configuração Railway Deployment...")
    
    deployment = RailwayDeploymentConfig()
    
    try:
        # Validar ambiente
        validation = deployment.validate_environment()
        print("\n🔍 VALIDAÇÃO DE AMBIENTE:")
        for check_name, check_result in validation["checks"].items():
            status_icon = "✅" if check_result["status"] == "ok" else "⚠️" if check_result["status"] == "warning" else "❌"
            print(f"   {status_icon} {check_name}: {check_result['message']}")
        
        if validation["warnings"]:
            print("\n⚠️ WARNINGS:")
            for warning in validation["warnings"]:
                print(f"   • {warning}")
        
        # Criar arquivos de deployment
        files_created = deployment.setup_deployment_files()
        print(f"\n📁 ARQUIVOS CRIADOS:")
        for file_path, file_desc in files_created.items():
            print(f"   ✅ {file_path}: {file_desc}")
        
        # Gerar relatório
        report_path = deployment.generate_deployment_report()
        
        # Criar script de deployment
        script_content = deployment.create_deployment_script()
        script_path = "deploy_railway.sh"
        with open(script_path, 'w') as f:
            f.write(script_content)
        os.chmod(script_path, 0o755)
        
        print(f"\n📋 RELATÓRIO: {report_path}")
        print(f"🚀 SCRIPT DEPLOYMENT: {script_path}")
        
        print("\n✅ CONFIGURAÇÃO RAILWAY COMPLETA!")
        print("🚀 Pronto para deployment!")
        
    except Exception as e:
        logger.error(f"❌ Erro na configuração: {e}")
        raise

if __name__ == "__main__":
    main()