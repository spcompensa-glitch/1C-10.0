#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script para verificar o main.py modificado
"""

import os
import sys
import time

# Adicionar backend ao path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.append(backend_path)

print(f"🔍 Backend path: {backend_path}")
print(f"📁 Backend exists: {os.path.exists(backend_path)}")

if os.path.exists(backend_path):
    services_path = os.path.join(backend_path, 'services')
    print(f"📂 Services path: {services_path}")
    print(f"📁 Services exists: {os.path.exists(services_path)}")
    
    if os.path.exists(services_path):
        nvidia_service_path = os.path.join(services_path, 'nvidia_service.py')
        print(f"🔧 NVIDIA service: {nvidia_service_path}")
        print(f"📁 NVIDIA service exists: {os.path.exists(nvidia_service_path)}")

print("🚀 Starting main.py...")

try:
    # Importar o main
    from main import app
    print("✅ main.py imported successfully")
    
    # Verificar se o app foi criado
    print(f"📱 FastAPI app created: {app is not None}")
    print(f"🌍 App title: {app.title}")
    print(f"📝 App description: {app.description}")
    
    # Listar rotas
    print("\n🛣️  Available routes:")
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            print(f"   {route.methods} {route.path}")
        elif hasattr(route, 'path'):
            print(f"   {route.__class__.__name__} {route.path}")
    
except Exception as e:
    print(f"❌ Error importing main.py: {e}")
    import traceback
    traceback.print_exc()