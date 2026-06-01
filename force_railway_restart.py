#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para forçar reinicialização do Railway Backend
==============================================

Script para enviar requisição de reinicialização do backend no Railway
após o reset absoluto do banco de dados.

Author: Sistema 1Crypten
Version: 1.0
"""

import os
import requests
import json

def restart_railway_service():
    """Força reinicialização do serviço Railway"""
    
    print("🔄 INICIANDO REINICIALIZAÇÃO DO SERVIÇO RAILWAY")
    print("=" * 50)
    
    # Carregar configurações
    railway_token = os.getenv("RAILWAY_TOKEN")
    railway_url = os.getenv("RAILWAY_URL", "https://1crypten-hermes-agent-production.up.railway.app")
    
    if not railway_token:
        print("❌ ERRO: RAILWAY_TOKEN não encontrada no arquivo .env")
        return False
    
    # Endpoint de reinicialização (se existir)
    restart_url = f"{railway_url}/api/system/restart"
    
    # Headers
    headers = {
        "Authorization": f"Bearer {railway_token}",
        "Content-Type": "application/json"
    }
    
    try:
        print(f"📡 Enviando requisição para reiniciar o serviço...")
        print(f"URL: {restart_url}")
        
        # Tenta enviar requisição de reinicialização
        response = requests.post(restart_url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Requisição de reinicialização enviada com sucesso!")
            print(f"📋 Resposta: {result}")
            return True
        else:
            print(f"⚠️  Serviço de reinicialização não disponível (status {response.status_code})")
            print("💡 Você precisará reiniciar manualmente no painel Railway")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ ERRO: Não foi possível conectar ao serviço Railway")
        print("💡 Você precisará reiniciar manualmente no painel Railway")
        return False
    except Exception as e:
        print(f"❌ ERRO: {str(e)}")
        print("💡 Você precisará reiniciar manualmente no painel Railway")
        return False

def check_service_status():
    """Verifica status do serviço"""
    
    print("\n🔍 VERIFICANDO STATUS DO SERVIÇO")
    print("=" * 30)
    
    railway_url = os.getenv("RAILWAY_URL", "https://1crypten-hermes-agent-production.up.railway.app")
    
    try:
        # Tenta acessar um endpoint simples
        response = requests.get(f"{railway_url}/api/health", timeout=10)
        
        if response.status_code == 200:
            print("✅ Serviço Railway está online")
            return True
        else:
            print(f"⚠️  Serviço retornou status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Serviço não está acessível: {str(e)}")
        return False

if __name__ == "__main__":
    print("🚀 Script de reinicialização do Railway")
    
    # Verificar status atual
    online = check_service_status()
    
    if online:
        print("💡 O serviço está online. Se o reset do banco não foi aplicado:")
        print("   1. Acesse o painel Railway")
        print("   2. Clique em 'Redeploy' no serviço backend")
        print("   3. Aguarde a reinicialização completa")
        print("   4. Verifique se os 4 slots aparecem e a banca está em $100")
    
    # Tentar reiniciar automaticamente
    restart_success = restart_railway_service()
    
    if restart_success:
        print("\n🎉 Reinicio automático enviado com sucesso!")
        print("🔄 Aguarde alguns minutos para o serviço voltar online")
    else:
        print("\n💥 Falha ao enviar reinicialização automática")
        print("🔧 Ação manual necessária no painel Railway")