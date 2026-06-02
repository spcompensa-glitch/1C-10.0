#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor simples para testar as rotas
"""

import os
import sys
import uvicorn
from fastapi import FastAPI
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

# Criar app FastAPI
app = FastAPI(title="Simple Test Server")

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurar caminho do frontend
frontend_path = os.path.join(os.path.dirname(__file__), 'frontend')

# Rotas
@app.get("/", response_class=RedirectResponse)
async def redirect_root():
    return "/login"

@app.get("/login", response_class=FileResponse)
async def serve_login():
    login_path = os.path.join(frontend_path, "login.html")
    if os.path.exists(login_path):
        return login_path
    else:
        raise Exception(f"Login não encontrado: {login_path}")

@app.get("/cockpit", response_class=FileResponse)
async def serve_cockpit():
    cockpit_path = os.path.join(frontend_path, "cockpit.html")
    if os.path.exists(cockpit_path):
        return cockpit_path
    else:
        raise Exception(f"Cockpit não encontrado: {cockpit_path}")

if __name__ == "__main__":
    print("Frontend:", frontend_path)
    print("Servidor iniciado em http://localhost:8000")
    print("Teste as rotas:")
    print("   - http://localhost:8000/login")
    print("   - http://localhost:8000/cockpit")
    
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)