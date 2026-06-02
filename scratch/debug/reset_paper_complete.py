#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reset Completo do Sistema Paper Mode
==================================

Script para executar reset nuclear do sistema 1Crypten no modo paper.
Limpa todas as posições, moonbags, histórico de trades e reseta a banca para $100.

Author: Sistema 1Crypten
Version: 1.0
"""

import os
import sys
import requests
import json
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

def reset_paper_system():
    """Executa reset completo do sistema paper mode"""
    
    print("🧹 INICIANDO RESET NUCLEAR DO SISTEMA PAPER MODE")
    print("=" * 50)
    
    # Verificar se as credenciais estão disponíveis
    api_key = os.getenv("ADMIN_API_KEY")
    backend_url = "http://localhost:8000"
    
    if not api_key:
        print("❌ ERRO: API_KEY não encontrada no arquivo .env")
        return False
    
    # Endpoint de reset
    reset_url = f"{backend_url}/api/trading/nuke-paper"
    
    # Headers com autenticação
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        print(f"📡 Enviando requisição para: {reset_url}")
        
        # Executar o reset
        response = requests.post(reset_url, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Reset concluído com sucesso!")
            print(f"📋 Items limpos: {result.get('cleared', [])}")
            print(f"📊 Status: {result.get('status', 'unknown')}")
            return True
        else:
            print(f"❌ ERRO: Status {response.status_code}")
            print(f"📋 Resposta: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ ERRO: Não foi possível conectar ao backend")
        print("💡 Verifique se o servidor está rodando em: http://localhost:8000")
        return False
    except Exception as e:
        print(f"❌ ERRO: {str(e)}")
        return False

if __name__ == "__main__":
    # Executar o reset
    success = reset_paper_system()
    
    if success:
        print("\n🎉 Reset nuclear concluído com sucesso!")
        print("💰 Banca resetada para $100")
        print("🗑️  Posições, moonbags e histórico limpos")
        print("🚀 Sistema pronto para operar em paper mode")
    else:
        print("\n💥 Falha ao executar o reset")
        print("🔍 Verifique os logs e tente novamente")