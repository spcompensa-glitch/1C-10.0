#!/usr/bin/env python3
import os
import json
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SimpleRailwayConfig")

def create_railway_deployment():
    """Cria configuração simplificada para Railway"""
    
    logger.info("🚂 Criando configuração Railway para Hermes-Kanban-Telegram...")
    
    # Verificar Railway CLI
    railway_available = False
    try:
        import subprocess
        result = subprocess.run(["railway", "--version"], capture_output=True, timeout=10)
        if result.returncode == 0:
            railway_available = True
            logger.info("✅ Railway CLI disponível")
        else:
            logger.warning("⚠️ Railway CLI não encontrado")
    except:
        logger.warning("⚠️ Railway CLI não encontrado")
    
    # Criar railway.json
    railway_config = {
        "name": "1crypten-hermes-guardian",
        "environment": "production",
        "services": {
            "hermes-guardian": {
                "command": "python main.py",
                "envVars": {
                    "RAILWAY_TOKEN": "baab061ec-2bcf-436b-bbb2-1c6b8616046b",
                    "ADMIN_API_KEY": "1crypten-admin-key-2026-production",
                    "TELEGRAM_BOT_TOKEN": "8656832302:AAHARDZZe-bltJte6QR-e-KcBiNkNDrvx7I",
                    "TELEGRAM_CHAT_ID": "1249100206",
                    "JWT_SECRET_KEY": "1crypten-jwt-secret-2026-production",
                    "RAILWAY_URL": "https://1crypten-hermes-agent-production.up.railway.app",
                    "ENVIRONMENT": "production",
                    "PORT": "8085"
                },
                "runtime": "python",
                "memoryLimit": "512MB",
                "cpuLimit": "100%",
                "buildCommand": "pip install -r requirements.txt"
            }
        },
        "settings": {
            "autoDeploy": True,
            "healthCheckInterval": 30,
            "healthCheckTimeout": 10
        }
    }
    
    # Salvar railway.json
    with open('railway.json', 'w', encoding='utf-8') as f:
        json.dump(railway_config, f, indent=2, ensure_ascii=False)
    logger.info("✅ railway.json criado")
    
    # Criar Procfile
    procfile_content = """web: python main.py
worker: python worker.py
"""
    with open('Procfile', 'w') as f:
        f.write(procfile_content)
    logger.info("✅ Procfile criado")
    
    # Criar .env.production
    env_content = f"""RAILWAY_TOKEN=baab061ec-2bcf-436b-bbb2-1c6b8616046b
RAILWAY_URL=https://1crypten-hermes-agent-production.up.railway.app
ADMIN_API_KEY=1crypten-admin-key-2026-production
TELEGRAM_BOT_TOKEN=8656832302:AAHARDZZe-bltJte6QR-e-KcBiNkNDrvx7I
TELEGRAM_CHAT_ID=1249100206
JWT_SECRET_KEY=1crypten-jwt-secret-2026-production
ENVIRONMENT=production
PORT=8085
"""
    with open('.env.production', 'w') as f:
        f.write(env_content)
    logger.info("✅ .env.production criado")
    
    # Criar script de deploy
    deploy_script = """#!/bin/bash
echo "🚂 Hermes-Kanban-Telegram Railway Deployment"

# 1. Login Railway
if railway login; then
    echo "✅ Login Railway OK"
else
    echo "❌ Login Railway falhou"
    exit 1
fi

# 2. Inicializar projeto
if [ ! -f ".railway" ]; then
    railway init
    echo "✅ Projeto Railway inicializado"
fi

# 3. Configurar variáveis
echo "🔧 Configurando variáveis ambiente..."
railway variables set RAILWAY_TOKEN=baab061ec-2bcf-436b-bbb2-1c6b8616046b
railway variables set ADMIN_API_KEY=1crypten-admin-key-2026-production
railway variables set TELEGRAM_BOT_TOKEN=8656832302:AAHARDZZe-bltJte6QR-e-KcBiNkNDrvx7I
railway variables set TELEGRAM_CHAT_ID=1249100206
railway variables set JWT_SECRET_KEY=1crypten-jwt-secret-2026-production

# 4. Adicionar serviço
railway add hermes-guardian

# 5. Deploy
echo "🚀 Realizando deploy..."
railway up --detach

# 6. Verificar status
echo "📊 Verificando status..."
sleep 10
railway logs --tail=20

echo "✅ Deployment concluído!"
echo "🌐 URL: https://1crypten-hermes-agent-production.up.railway.app"
"""
    
    with open('deploy.sh', 'w') as f:
        f.write(deploy_script)
    os.chmod('deploy.sh', 0o755)
    logger.info("✅ deploy.sh criado")
    
    # Gerar relatório
    report = {
        "timestamp": __import__('time').time(),
        "project": "1crypten-hermes-guardian",
        "environment": "production",
        "railway_url": "https://1crypten-hermes-agent-production.up.railway.app",
        "railway_cli_available": railway_available,
        "files_created": [
            "railway.json",
            "Procfile", 
            ".env.production",
            "deploy.sh",
            "main.py"
        ],
        "endpoints": {
            "health": "https://1crypten-hermes-agent-production.up.railway.app/health",
            "status": "https://1crypten-hermes-agent-production.up.railway.app/status",
            "kanban": "https://1crypten-hermes-agent-production.up.railway.app/kanban",
            "telegram": "https://1crypten-hermes-agent-production.up.railway.app/telegram",
            "dashboard": "https://1crypten-hermes-agent-production.up.railway.app/dashboard"
        },
        "deployment_ready": True,
        "next_steps": [
            "1. Executar: ./deploy.sh",
            "2. Monitorar: railway logs",
            "3. Testar endpoints de saúde",
            "4. Validar integração Kanban"
        ]
    }
    
    # Salvar relatório
    with open('railway_deployment_report.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    logger.info("📋 Relatório salvo: railway_deployment_report.json")
    
    print("\n🎉 CONFIGURAÇÃO RAILWAY COMPLETA!")
    print(f"📁 Arquivos criados:")
    print("   ✅ railway.json")
    print("   ✅ Procfile") 
    print("   ✅ .env.production")
    print("   ✅ deploy.sh")
    print("   ✅ main.py")
    
    print(f"\n🌐 Endpoints disponíveis:")
    for endpoint_name, endpoint_url in report["endpoints"].items():
        print(f"   📍 {endpoint_name}: {endpoint_url}")
    
    print(f"\n🚀 Próximos passos:")
    for step in report["next_steps"]:
        print(f"   • {step}")
    
    if railway_available:
        print(f"\n✅ Railway CLI disponível - Pode executar: ./deploy.sh")
    else:
        print(f"\n⚠️ Railway CLI não disponível - Instale com: npm install -g @railway/cli")
    
    return report

if __name__ == "__main__":
    create_railway_deployment()