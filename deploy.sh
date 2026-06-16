#!/bin/bash
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
railway variables set RAILWAY_TOKEN=da49f7fa-ccc6-405c-9b41-4af1429e93b7
railway variables set ADMIN_API_KEY=1crypten-admin-key-2026-production
railway variables set TELEGRAM_BOT_TOKEN=8656832302:AAHARDZZe-bltJte6QR-e-KcBiNkNDrvx7I
railway variables set TELEGRAM_CHAT_ID=1249100206
railway variables set JWT_SECRET_KEY=1crypten-jwt-secret-2026-production
railway variables set NVAPI_KEY=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
railway variables set ENVIRONMENT=production
railway variables set PORT=8085

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