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