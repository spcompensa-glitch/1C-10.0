#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teste específico da NVIDIA AI
"""

import os
import sys
import time

# Adicionar backend ao path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.append(backend_path)

from backend.config import settings
from backend.services.nvidia_service import nvidia_service

def test_nvidia_config():
    """Testar configuração NVIDIA"""
    print("🔧 Testing NVIDIA AI Configuration")
    print("=" * 40)
    
    # Verificar configuração
    print(f"NVAPI_KEY configured: {bool(settings.NVAPI_KEY)}")
    print(f"NVAPI_KEY length: {len(settings.NVAPI_KEY) if settings.NVAPI_KEY else 0}")
    
    if settings.NVAPI_KEY:
        # Mostrar parte da chave (para não expor tudo)
        masked_key = settings.NVAPI_KEY[:10] + "..." + settings.NVAPI_KEY[-10:]
        print(f"NVAPI_KEY: {masked_key}")
    
    # Testar inicialização
    print("\n🚀 Testing NVIDIA Service initialization...")
    try:
        result = nvidia_service.initialize()
        print(f"✅ NVIDIA Service initialized: {result}")
        print(f"✅ Service initialized: {nvidia_service._initialized}")
        
        if result:
            # Testar uma chamada simples
            print("\n🧪 Testing NVIDIA API call...")
            
            # Criar uma task para não bloquear
            import asyncio
            
            async def test_chat():
                try:
                    response = await nvidia_service.chat_completion(
                        user_message="Hello, test message",
                        system_instruction="You are a helpful assistant. Respond briefly.",
                        temperature=0.7,
                        max_tokens=100
                    )
                    print(f"✅ NVIDIA API Response: {response}")
                    return response
                except Exception as e:
                    print(f"❌ NVIDIA API Error: {e}")
                    return None
            
            # Rodar a async function
            try:
                response = asyncio.run(test_chat())
                if response:
                    print("✅ NVIDIA AI is working!")
                else:
                    print("❌ NVIDIA AI not responding")
            except Exception as e:
                print(f"❌ Async test failed: {e}")
        else:
            print("❌ NVIDIA Service failed to initialize")
            
    except Exception as e:
        print(f"❌ NVIDIA Service error: {e}")
        import traceback
        traceback.print_exc()

def test_env_variables():
    """Testar variáveis de ambiente"""
    print("\n🌍 Testing Environment Variables")
    print("=" * 40)
    
    env_vars = [
        "RAILWAY_TOKEN",
        "ADMIN_API_KEY", 
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "JWT_SECRET_KEY",
        "NVAPI_KEY",
        "ENVIRONMENT",
        "PORT"
    ]
    
    for var in env_vars:
        value = os.getenv(var)
        print(f"{var}: {'✅' if value else '❌'} ({len(value) if value else 0} chars)")

if __name__ == "__main__":
    test_env_variables()
    test_nvidia_config()